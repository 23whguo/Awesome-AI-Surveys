"""Audit and harvest public 2026 preprint metadata without keyword-only searching."""
from __future__ import annotations

import argparse
import calendar
import collections
import concurrent.futures
import datetime as dt
import gzip
import hashlib
import html
import io
import json
from pathlib import Path
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT/'.cache/external-2026'
USER_AGENT = 'Awesome-AI-Surveys/1.0 (+https://github.com/23whguo/Awesome-AI-Surveys; public metadata audit)'
CROSSREF_FIELDS = 'DOI,title,author,abstract,posted,published,type,group-title,resource,relation,URL,created,update-to'
PREFIXES = {'techrxiv': '10.36227', 'preprints': '10.20944'}


def timestamp():
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds')


def dump(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix+'.tmp')
    temporary.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8',newline='\n')
    temporary.replace(path)


def request(url, refresh=False):
    key = hashlib.sha256(url.encode()).hexdigest()
    path = CACHE/'responses'/(key+'.json.gz')
    if path.exists() and not refresh:
        with gzip.open(path,'rt',encoding='utf-8') as file:
            return json.load(file)
    last_error = None
    for attempt in range(4):
        try:
            req = urllib.request.Request(url,headers={'User-Agent':USER_AGENT,'Accept':'application/json'})
            with urllib.request.urlopen(req,timeout=70) as response:
                data = json.load(response)
                result = {'url':url,'retrieved_at':timestamp(),'data':data,'error':None}
            path.parent.mkdir(parents=True,exist_ok=True)
            temp = path.with_suffix('.tmp')
            with gzip.open(temp,'wt',encoding='utf-8') as file:
                json.dump(result,file,ensure_ascii=False,separators=(',',':'))
            temp.replace(path)
            return result
        except urllib.error.HTTPError as error:
            last_error = 'http-'+str(error.code)
            if error.code not in {408,429,500,502,503,504}:
                break
            try:
                delay = min(45,max(2,float(error.headers.get('Retry-After',2**(attempt+1)))))
            except (TypeError,ValueError):
                delay = 2**(attempt+1)
        except (OSError,ValueError,TimeoutError):
            last_error = 'network-or-json-error'
            delay = 2**(attempt+1)
        if attempt<3:
            time.sleep(delay)
    return {'url':url,'retrieved_at':timestamp(),'data':None,'error':last_error}


def months(start, end):
    for month in range(1,end.month+1):
        first = dt.date(end.year,month,1)
        last = min(end,dt.date(end.year,month,calendar.monthrange(end.year,month)[1]))
        if last>=start:
            yield max(start,first),last


def plain(value):
    value = value or ''
    for _ in range(2):
        value = re.sub(r'<[^>]+>',' ',html.unescape(value))
    return re.sub(r'\s+',' ',value).strip()


def crossref_date(work):
    for field in ('posted','published','created'):
        parts = work.get(field,{}).get('date-parts',[[]])[0]
        if len(parts)>=3:
            try:
                return dt.date(*parts[:3]).isoformat(),field
            except ValueError:
                continue
    return None,None


def crossref_record(work, source, fetched_at):
    doi = str(work.get('DOI') or '').lower()
    date,basis = crossref_date(work)
    return {'paper_name':plain(' '.join(work.get('title') or [])),
            'paper_abstract':plain(work.get('abstract')),
            'paper_authors':[' '.join(x for x in (a.get('given'),a.get('family')) if x).strip()
                             or a.get('name','') for a in work.get('author',[])],
            'paper_url':'https://doi.org/'+doi,'paper_code':'#',
            'conf':('TechRxiv' if source=='techrxiv' else 'Preprints.org')+'2026',
            'source_record_id':doi,'source_first_submitted_at':date,
            'source_date_basis':'Crossref.'+str(basis),
            'source_platform_url':work.get('resource',{}).get('primary',{}).get('URL'),
            'source_retrieved_at':fetched_at,'source_metadata_provider':'Crossref',
            'source_external':source,'source_relation':work.get('relation',{}),
            'source_update_to':work.get('update-to',[]),
            'source_group':work.get('group-title')}


def harvest_crossref(source, start, end, refresh=False):
    prefix = PREFIXES[source]
    records = {}
    partitions = []
    for first,last in months(start,end):
        cursor = '*'
        page = 0
        seen = set()
        totals = []
        errors = []
        queries = []
        truncated = False
        while True:
            params = {'filter':f'from-posted-date:{first},until-posted-date:{last}',
                      'rows':1000,'cursor':cursor,'select':CROSSREF_FIELDS}
            url = 'https://api.crossref.org/prefixes/'+prefix+'/works?'+urllib.parse.urlencode(params)
            response = request(url,refresh)
            queries.append({'url':url,'retrieved_at':response['retrieved_at'],'error':response['error']})
            if response['error']:
                errors.append(response['error'])
                break
            message = response['data']['message']
            totals.append(message['total-results'])
            items = message.get('items',[])
            page+=1
            before = len(seen)
            for work in items:
                doi = str(work.get('DOI') or '').lower()
                if not doi:
                    errors.append('missing-doi')
                    continue
                if doi in seen:
                    errors.append('duplicate-doi-in-partition:'+doi)
                seen.add(doi)
                records[doi] = crossref_record(work,source,response['retrieved_at'])
            if len(items)<1000:
                break
            next_cursor = message.get('next-cursor')
            if not next_cursor or next_cursor==cursor or len(seen)==before:
                truncated = True
                errors.append('pagination-stalled')
                break
            cursor = next_cursor
            time.sleep(0.3)
        expected = totals[0] if totals else None
        complete = not errors and not truncated and expected==len(seen) and len(set(totals))==1
        partitions.append({'from':str(first),'through':str(last),'expected_records':expected,
                           'unique_records':len(seen),'pages':page,'complete':complete,
                           'reported_totals':sorted(set(totals)),'errors':errors,'queries':queries})
        print(source,str(first)[:7],'records',len(seen),'/',expected,'complete',complete,flush=True)
    # Independent full-window count detects missing month partitions and date-filter discrepancies.
    count_url = 'https://api.crossref.org/prefixes/'+prefix+'/works?'+urllib.parse.urlencode(
        {'filter':f'from-posted-date:{start},until-posted-date:{end}','rows':0})
    count_response = request(count_url,refresh)
    expected_total = (count_response.get('data') or {}).get('message',{}).get('total-results')
    # Check a second date axis by DOI only. Equal totals alone do not prove equal sets.
    publication_ids = set()
    publication_queries = []
    publication_errors = []
    publication_totals = []
    cursor = '*'
    for page in range(500):
        url = 'https://api.crossref.org/prefixes/'+prefix+'/works?'+urllib.parse.urlencode(
            {'filter':f'from-pub-date:{start},until-pub-date:{end}','rows':1000,'cursor':cursor,'select':'DOI'})
        response = request(url,refresh)
        publication_queries.append({'url':url,'retrieved_at':response['retrieved_at'],'error':response['error']})
        if response['error']:
            publication_errors.append(response['error'])
            break
        message = response['data']['message']
        publication_totals.append(message['total-results'])
        items = message.get('items',[])
        before = len(publication_ids)
        publication_ids.update(str(x['DOI']).lower() for x in items)
        if len(items)<1000:
            break
        next_cursor = message.get('next-cursor')
        if not next_cursor or next_cursor==cursor or before==len(publication_ids):
            publication_errors.append('pagination-stalled')
            break
        cursor = next_cursor
        time.sleep(0.3)
    else:
        publication_errors.append('pagination-safety-limit')
    if not publication_totals or len(set(publication_totals))!=1 or publication_totals[0]!=len(publication_ids):
        publication_errors.append('publication-date-count-mismatch')
    publication_only = sorted(publication_ids-records.keys())
    for doi in publication_only:
        response = request('https://api.crossref.org/works/'+urllib.parse.quote(doi,safe=''),refresh)
        if response['error']:
            publication_errors.append('missing-record:'+doi+':'+response['error'])
        else:
            records[doi] = crossref_record(response['data']['message'],source,response['retrieved_at'])
    posted_count = sum(p['unique_records'] for p in partitions)
    datacite_url = 'https://api.datacite.org/dois?'+urllib.parse.urlencode(
        {'query':f'prefix:{prefix} AND publicationYear:2026','page[size]':1})
    datacite = request(datacite_url,refresh)
    datacite_total = (datacite.get('data') or {}).get('meta',{}).get('total')
    print(source,'date-axis crosscheck','publication IDs',len(publication_ids),'additional',len(publication_only),'DataCite',datacite_total,flush=True)
    return list(records.values()),{'source':source,'provider':'Crossref REST API','doi_prefix':prefix,
        'from':str(start),'through':str(end),'scope':'Union of posted-date and publication-date DOI queries; all subjects and article titles. DataCite prefix/year crosscheck.',
        'records':len(records),'expected_posted_records':expected_total,'posted_records':posted_count,'count_query':count_url,
        'publication_date_crosscheck':{'unique_dois':len(publication_ids),'expected_records':publication_totals[0] if publication_totals else None,'additional_dois':publication_only,'errors':publication_errors,'queries':publication_queries},
        'datacite_crosscheck':{'url':datacite_url,'records':datacite_total,'error':datacite['error'],'retrieved_at':datacite['retrieved_at']},
        'complete_within_api_scope':all(p['complete'] for p in partitions) and expected_total==posted_count and not publication_errors and datacite_total==0,
        'partitions':partitions,'count_query_error':count_response['error'],
        'limitations':['A complete DOI-registry query is not proof of complete platform coverage.',
                       'Unregistered, delayed, removed, withdrawn or incorrectly dated records may be absent.']}


def hf_record(entry, selected_day, fetched_at):
    paper = entry.get('paper',{})
    aid = paper.get('id','')
    return {'paper_name':paper.get('title') or entry.get('title',''),
            'paper_abstract':paper.get('summary') or entry.get('summary',''),
            'paper_authors':[a.get('name','') for a in paper.get('authors',[])],
            'paper_url':'https://arxiv.org/abs/'+aid,
            'paper_code':paper.get('githubRepo') or '#','conf':'ARXIV'+('20'+aid[:2] if re.fullmatch(r'\d{4}\.\d{4,5}',aid) else '2026'),
            'arxiv_id':aid,'arxiv_first_submitted_at_utc':paper.get('publishedAt') or entry.get('publishedAt'),
            'source_record_id':aid,'source_platform_url':'https://huggingface.co/papers/'+aid,
            'source_selected_on':selected_day,'source_selected_at':paper.get('submittedOnDailyAt'),
            'source_retrieved_at':fetched_at,'source_metadata_provider':'Hugging Face Daily Papers API',
            'source_external':'huggingface','source_withdrawn_at':paper.get('withdrawnAt')}


def hf_partition(kind, value, refresh=False):
    records = []
    pages = []
    seen = set()
    errors = []
    for page in range(500):
        url = 'https://huggingface.co/api/daily_papers?'+urllib.parse.urlencode({kind:value,'limit':100,'p':page,'sort':'publishedAt'})
        response = request(url,refresh)
        pages.append({'url':url,'retrieved_at':response['retrieved_at'],'error':response['error']})
        if response['error']:
            errors.append(response['error'])
            break
        items = response['data']
        if not isinstance(items,list):
            errors.append('unexpected-response-type')
            break
        previous = len(seen)
        for entry in items:
            aid = entry.get('paper',{}).get('id')
            if not aid or aid in seen:
                errors.append('duplicate-or-missing-paper-id')
            if aid:
                seen.add(aid)
            records.append(hf_record(entry,value,response['retrieved_at']))
        if len(items)<100:
            break
        if len(seen)==previous:
            errors.append('pagination-stalled')
            break
        time.sleep(0.2)
    else:
        errors.append('pagination-safety-limit')
    return records,{'kind':kind,'value':value,'records':len(seen),'pages':len(pages),
                    'complete':not errors,'errors':errors,'queries':pages}


def harvest_hf(start, end, refresh=False, crosscheck=True):
    days = [(start+dt.timedelta(days=i)).isoformat() for i in range((end-start).days+1)]
    records = {}
    partitions = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
        for index,(items,report) in enumerate(executor.map(lambda day:hf_partition('date',day,refresh),days),1):
            partitions.append(report)
            for row in items:
                aid = row['source_record_id']
                if aid in records:
                    records[aid]['source_selected_days'].append(row['source_selected_on'])
                else:
                    row['source_selected_days'] = [row['source_selected_on']]
                    records[aid] = row
            if index%20==0 or index==len(days):
                print('Hugging Face days',index,'/',len(days),'unique papers',len(records),flush=True)
    monthly = []
    recovered = set()
    if crosscheck:
        for first,last in months(start,end):
            month = str(first)[:7]
            items,report = hf_partition('month',month,refresh)
            original_daily_ids = {row['source_record_id'] for row in records.values()
                                  if any(day.startswith(month) for day in row.get('source_selected_days',[]))}
            month_ids = set()
            for row in items:
                selected = row.get('source_selected_at') or ''
                if selected[:10] and str(start)<=selected[:10]<=str(end):
                    aid = row['source_record_id']
                    month_ids.add(aid)
                    if aid not in records:
                        row['source_selected_days'] = [selected[:10]]
                        records[aid] = row
                        recovered.add(aid)
            daily_ids = {row['source_record_id'] for row in records.values()
                         if any(day.startswith(month) for day in row.get('source_selected_days',[]))}
            report['in_window_records'] = len(month_ids)
            report['monthly_only_ids'] = sorted(month_ids-original_daily_ids)
            report['daily_only_ids'] = sorted(original_daily_ids-month_ids)
            report['sets_agree'] = month_ids==original_daily_ids
            monthly.append(report)
            print('Hugging Face month crosscheck',month,'records',len(month_ids),'agree',report['sets_agree'],flush=True)
    return list(records.values()),{'source':'huggingface','provider':'Hugging Face Daily Papers API',
        'from':str(start),'through':str(end),'scope':'Every calendar day, including empty weekends; all pages. Independent month pagination crosscheck.',
        'expected_days':len(days),'checked_days':len(partitions),'records':len(records),
        'complete_within_api_scope':all(p['complete'] for p in partitions) and (not crosscheck or all(p['complete'] and p['sets_agree'] for p in monthly)),
        'partitions':partitions,'monthly_crosschecks':monthly,'monthly_recovered_ids':sorted(recovered),
        'limitations':['Daily Papers is a selection/index of arXiv papers, not an independent preprint host.',
                       'Papers not selected on the feed and removed/unavailable feed entries are outside this source.',
                       'Daily selection date is not the publication date. Older selected papers retain their original year.']}


def write_input(source, records):
    path = CACHE/'inputs'/(source+'-2026.jsonl.gz')
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('wb') as raw:
        with gzip.GzipFile(filename='',fileobj=raw,mode='wb',mtime=0) as compressed:
            with io.TextIOWrapper(compressed,encoding='utf-8',newline='\n') as output:
                for record in sorted(records,key=lambda r:r['source_record_id']):
                    output.write(json.dumps(record,ensure_ascii=False,separators=(',',':'))+'\n')
    return path


def check_site_access():
    checks = []
    for source,url in [('techrxiv','https://www.techrxiv.org/sitemap-index-1.xml'),('preprints','https://www.preprints.org/')]:
        status = None
        error = None
        try:
            with urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':USER_AGENT}),timeout=40) as response:
                status = response.status
                response.read(1024)
        except urllib.error.HTTPError as exception:
            status = exception.code
        except (OSError,TimeoutError) as exception:
            error = type(exception).__name__
        checks.append({'source':source,'url':url,'http_status':status,'error':error,'checked_at':timestamp()})
    dump(CACHE/'site-access.json',checks)
    return checks


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--as-of',default='2026-11-08')
    parser.add_argument('--sources',nargs='+',choices=['techrxiv','preprints','huggingface'],default=['techrxiv','preprints','huggingface'])
    parser.add_argument('--refresh',action='store_true')
    parser.add_argument('--no-month-crosscheck',action='store_true')
    parser.add_argument('--report-only',action='store_true',help='Assemble the three saved source audits without network calls')
    parser.add_argument('--check-sites',action='store_true',help='Also check public website/sitemap access once; never bypass a denial')
    args = parser.parse_args()
    end = dt.date.fromisoformat(args.as_of)
    if end.year!=2026:
        parser.error('This audit is scoped to 2026')
    start = dt.date(2026,1,1)
    reports = {}
    def run(source):
        if source=='huggingface':
            rows,report = harvest_hf(start,end,args.refresh,not args.no_month_crosscheck)
        else:
            rows,report = harvest_crossref(source,start,end,args.refresh)
        path = write_input(source,rows)
        report['input_file'] = path.name
        report['input_sha256'] = hashlib.sha256(path.read_bytes()).hexdigest()
        dump(CACHE/(source+'-audit.json'),report)
        return source,report
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
        for source,report in executor.map(run,[] if args.report_only else args.sources):
            reports[source] = report
    for source in ('techrxiv','preprints','huggingface'):
        path = CACHE/(source+'-audit.json')
        if source not in reports and path.exists():
            reports[source] = json.loads(path.read_text(encoding='utf-8'))
            if reports[source]['through']!=str(end):
                parser.error('Cached source audit has a different cutoff: '+source)
    audit = {'schema_version':1,'updated_at':timestamp(),'from':str(start),'through':str(end),
             'claim':'Complete only within each explicitly audited public API scope; not a guarantee of all AI surveys.',
             'sources':reports}
    if args.check_sites:
        audit['website_access_checks'] = check_site_access()
    elif (CACHE/'site-access.json').exists():
        audit['website_access_checks'] = json.loads((CACHE/'site-access.json').read_text(encoding='utf-8'))
    dump(ROOT/'data/harvest-2026.json',audit)
    print('HARVEST',json.dumps({k:{'records':v['records'],'complete_within_api_scope':v['complete_within_api_scope']} for k,v in reports.items()}),flush=True)


if __name__=='__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    main()
