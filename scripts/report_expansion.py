"""Publish source coverage, catalog changes, and a browsable external review queue."""
from __future__ import annotations
import argparse
import collections
import gzip
import hashlib
import json
from pathlib import Path

from catalog import deduplicate, write_json
from render import cell, link

ROOT = Path(__file__).resolve().parents[1]
EXTERNAL = {'techrxiv-2026':'TechRxiv','preprints-2026':'Preprints.org','huggingface-daily-2026':'HF Daily Papers'}
PAGE_SIZE = 80


def rows(path):
    with path.open(encoding='utf-8') as file:
        return [json.loads(line) for line in file if line.strip()]


def save(path, text):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(text.rstrip()+'\n',encoding='utf-8',newline='\n')


def build_index(audit):
    by_line={(r['source'],r['line']):r for r in audit}
    manifest={}
    names={'techrxiv-2026':'techrxiv','preprints-2026':'preprints','huggingface-daily-2026':'huggingface'}
    for source,stem in names.items():
        path=ROOT/'.cache/external-2026/inputs'/(stem+'-2026.jsonl.gz')
        if not path.exists():
            raise ValueError('Harvest source input before building the public index: '+stem)
        parts=[]
        batch=[]
        decisions=collections.Counter()
        missing_abstract=0
        def flush():
            target=ROOT/'data/discovery-index'/(source+'-'+str(len(parts)+1).zfill(3)+'.jsonl')
            save(target,'\n'.join(json.dumps(r,ensure_ascii=False,separators=(',',':')) for r in batch))
            parts.append({'path':target.relative_to(ROOT).as_posix(),'records':len(batch),'sha256':hashlib.sha256(target.read_bytes()).hexdigest()})
            batch.clear()
        with gzip.open(path,'rt',encoding='utf-8') as file:
            count=0
            for line_number,line in enumerate(file,1):
                row=json.loads(line)
                entry=by_line.get((source,line_number))
                status=entry['status'] if entry else 'not-discovered-as-review'
                decisions[status]+=1
                missing_abstract+=not bool(row.get('paper_abstract'))
                batch.append({'source':source,'line':line_number,'record_id':row['source_record_id'],
                              'title':row['paper_name'],'paper_url':row['paper_url'],
                              'source_date':row.get('arxiv_first_submitted_at_utc') or row.get('source_first_submitted_at'),
                              'has_abstract':bool(row.get('paper_abstract')),'screening_status':status,
                              'catalog_id':entry.get('catalog_id') if entry else None})
                count+=1
                if len(batch)==1000:
                    flush()
            if batch:
                flush()
        manifest[source]={'records':count,'records_without_abstract':missing_abstract,'status_counts':dict(decisions),'parts':parts}
    write_json(ROOT/'data/discovery-index/manifest.json',manifest)
    return manifest


def report(baseline=None, build_full_index=False):
    current = rows(ROOT/'data/surveys.jsonl')
    by_id = {p['id']:p for p in current}
    manifest = json.loads((ROOT/'data/manifest.json').read_text(encoding='utf-8'))
    harvest = json.loads((ROOT/'data/harvest-2026.json').read_text(encoding='utf-8'))
    audit = rows(ROOT/'data/external-review-audit.jsonl')
    if build_full_index:
        index_manifest=build_index(audit)
    elif (ROOT/'data/discovery-index/manifest.json').exists():
        index_manifest=json.loads((ROOT/'data/discovery-index/manifest.json').read_text(encoding='utf-8'))
    else:
        index_manifest={}
    if baseline:
        baseline_ids = {p['id'] for p in rows(baseline)}
    elif (ROOT/'data/expansion-2026.json').exists():
        baseline_ids = set(json.loads((ROOT/'data/expansion-2026.json').read_text(encoding='utf-8'))['baseline_ids'])
    else:
        raise ValueError('Supply --baseline for the first expansion report')
    added = set(by_id)-baseline_ids
    removed = baseline_ids-set(by_id)
    source_ids = {source:{p['id'] for p in current if any(s['dataset']==source for s in p['sources'])} for source in EXTERNAL}
    supported = set().union(*source_ids.values())
    pending = [p for p in audit if p['status']=='pending']
    pending_rows = []
    for item in pending:
        pending_rows.append({'paper_name':item['title'],'paper_authors':item['authors'],'paper_url':item['paper_url'],
                             'conf':EXTERNAL[item['source']]+str(item['year']),'_source':item['source'],'_line':item['line'],'audit':item})
    pending_groups = sorted(deduplicate(pending_rows),key=lambda g:g[0]['paper_name'].casefold())
    result = {'schema_version':1,'as_of':manifest['as_of'],'baseline_commit':'2ddd240948746e8a3139508ef7775fb979ffcd3f',
              'baseline_ids':sorted(baseline_ids),'baseline_surveys':len(baseline_ids),'current_surveys':len(current),
              'added_ids':sorted(added),'removed_ids':sorted(removed),'net_added':len(current)-len(baseline_ids),
              'added_2026':sum(by_id[i]['year']==2026 for i in added),'added_year_counts':dict(sorted(collections.Counter(str(by_id[i]['year']) for i in added).items())),
              'new_source_supported_added':len(added&supported),'existing_enriched_by_new_sources':len(baseline_ids&supported),
              'source_unique_catalog_works':{source:len(ids) for source,ids in source_ids.items()},
              'pending_source_records':len(pending),'pending_unique_candidates':len(pending_groups),
              'screening_audit_records':len(audit),'status_record_counts':dict(collections.Counter(x['status'] for x in audit)),
              'full_discovery_index_records':sum(x['records'] for x in index_manifest.values()),
              'pending_reasons':dict(collections.Counter(x['reason'] for x in pending)),
              'all_api_partitions_complete':all(s['complete_within_api_scope'] for s in harvest['sources'].values()),
              'platform_exhaustiveness_guaranteed':False}
    write_json(ROOT/'data/expansion-2026.json',result)
    pages = [pending_groups[i:i+PAGE_SIZE] for i in range(0,len(pending_groups),PAGE_SIZE)] or [[]]
    expected_pages = {f'external-2026-{page:03d}.md' for page in range(1,len(pages)+1)}
    for stale in (ROOT/'docs/pending').glob('external-2026-*.md'):
        if stale.name not in expected_pages:
            stale.unlink()
    index = ['# 2026 external review candidates · 外部来源待复核','',
             '[Home](../README.md) · [Coverage and additions](EXPANSION_2026.md)','',
             f'{len(pending_groups)} unique candidate groups from {len(pending)} source records. These are **not confirmed included reviews** and are not counted in the catalog total.',
             '这些是类型或 AI 相关性仍需确认的候选，包含综述计划、混合方法论文与元数据不足的记录。保留候选不等于认定它是综述；同一候选的多个来源和版本合并展示。','',
             '| Page | Candidate groups |','| --- | ---: |']
    for page,groups in enumerate(pages,1):
        filename=f'external-2026-{page:03d}.md'
        index.append(f'| [{page}](pending/{filename}) | {len(groups)} |')
        navigation=' · '.join(str(i) if i==page else f'[{i}](external-2026-{i:03d}.md)' for i in range(1,len(pages)+1))
        lines=[f'# External candidates · 2026 · {page}/{len(pages)}','',
               '[Home](../../README.md) · [Candidate index](../EXTERNAL_PENDING_2026.md) · [Coverage report](../EXPANSION_2026.md)','',
               '**Pending candidates, not included catalog entries. 待复核候选，不计入已收录综述。**','',navigation,'',
               '| Source | Year | Title | Paper | Reason for review |','| --- | ---: | --- | --- | --- |']
        for group in groups:
            first=group[0]['audit']
            sources=sorted({EXTERNAL[r['_source']] for r in group})
            urls=sorted({r['paper_url'] for r in group if r.get('paper_url')})
            reasons=sorted({r['audit']['reason'] for r in group})
            lines.append('| '+' | '.join([cell(', '.join(sources)),str(first['year']),cell(first['title']),
                                         ' · '.join(link('paper '+str(i),url) for i,url in enumerate(urls,1)),cell('; '.join(reasons))])+' |')
        lines+=['',navigation]
        save(ROOT/'docs/pending'/filename,'\n'.join(lines))
    save(ROOT/'docs/EXTERNAL_PENDING_2026.md','\n'.join(index))
    lines=['# 2026 source expansion · 2026 年补漏调查与覆盖报告','',
           '[Home](../README.md) · [中文](../README.zh-CN.md) · [Pending candidates](EXTERNAL_PENDING_2026.md)','',
           '**Cutoff / 截止日期：'+manifest['as_of']+'。2026 年尚未结束，本报告不包含截止日之后的新论文。**','',
           '本次目标是穷尽指定公开 API 在时间窗口内返回的记录和分页，**不承诺所有平台、所有 AI 综述一篇不漏**。API 完整分页、论文类型识别和平台真实全量是不同的覆盖层次。','',
           '## Catalog changes · 目录变化','',
           '| Metric | Count |','| --- | ---: |',
           f'| Baseline included surveys | {len(baseline_ids)} |',f'| Current included surveys | {len(current)} |',
           f'| Newly included identities | {len(added)} |',f'| Newly included identities with displayed year 2026 | {result["added_2026"]} |',
           f'| Added identities supported by the three new sources | {result["new_source_supported_added"]} |',
           f'| Existing identities enriched with new-source provenance | {result["existing_enriched_by_new_sources"]} |',
           f'| Removed baseline identities | {len(removed)} |',f'| Pending source records | {len(pending)} |',
           f'| Pending unique candidate groups | {len(pending_groups)} |','',
           'Source contributions overlap and must not be added together. New versions and matching cross-posts enrich one canonical work rather than inflate the total. Some HF selections and updated preprints originate in earlier years; selection/version date is not first-ever publication date.','',
           '## Acquisition coverage · 抓取覆盖','',
           '| Source | Records returned | API scope fully enumerated | Catalog works with this provenance |','| --- | ---: | --- | ---: |']
    for source,label in EXTERNAL.items():
        key={'techrxiv-2026':'techrxiv','preprints-2026':'preprints','huggingface-daily-2026':'huggingface'}[source]
        s=harvest['sources'][key]
        lines.append('| '+label+' | '+str(s['records'])+' | '+('Yes' if s['complete_within_api_scope'] else '**No; inspect errors**')+' | '+str(len(source_ids[source]))+' |')
    access=harvest.get('website_access_checks',[])
    access_note='Website/sitemap checks: '+', '.join(x['source']+' HTTP '+str(x['http_status']) for x in access)+'.' if access else 'Direct website/sitemap completeness has not been established.'
    zero_months=[p['from'][:7] for p in harvest['sources']['techrxiv']['partitions'] if p['unique_records']==0]
    zero_note=('TechRxiv registry queries returned zero records in '+', '.join(zero_months)+'. This is a **coverage warning**, not evidence that no surveys were published in those months. The machine-readable report preserves each zero-count query.' if zero_months else
               'Every TechRxiv monthly registry partition returned records; this still does not prove that all platform articles were registered or indexed.')
    lines+=['',
            '- **TechRxiv / Preprints.org:** enumerate every Crossref record for DOI prefixes 10.36227 / 10.20944 in monthly posted-date windows; independently enumerate the publication-date DOI set, compare identities, and fetch any additional records. DataCite prefix/year queries provide an additional registration-agency check.',
            '- **HF Daily Papers:** enumerate every calendar date from 2026-01-01 through the cutoff, including empty days, and continue pagination beyond the first 100 entries. Independently enumerate each month and compare paper-ID sets.',
            '- **Discovery:** inspect title markers, explicit abstract synthesis statements, bibliometric/scientometric mapping and systematic mapping. Strong AI relevance is required; biological neural mechanisms and incidental use of AI do not establish an AI-review focus.',
            '- **Review and identity:** retain ambiguous entries in the linked queue; use identifier, compatible title and author evidence to merge versions. A shared title or a high-level keyword alone is insufficient.',
            '',
            '## Coverage limits and observed gaps · 已知限制','',
            access_note+' The websites were not bypassed or independently fully crawled. A DOI-registry harvest therefore cannot certify complete platform coverage; unregistered, delayed, removed or incorrectly dated records remain possible gaps.',
            '',
            zero_note,
            '',
            'HF Daily Papers indexes selected arXiv papers. It is useful for recovering omissions in a local arXiv snapshot, but is not an independent preprint publication host or a comprehensive index of all arXiv papers. Its 2026 feed can select papers originally published in earlier years.',
            '',
            'Screening remains metadata-based. Ambiguous AI relevance, review protocols, hybrid method papers, withdrawn records and missing metadata require further review. The pending queue is intentionally visible and is not counted as confirmed surveys.',
            '',
            '## Audit files · 可追查记录','',
            '- [Every API partition, count and crosscheck](../data/harvest-2026.json)',
            '- [Every external review candidate and screening decision](../data/external-review-audit.jsonl)',
            '- [Full discovered-record index, including records not recognized as reviews](../data/discovery-index/manifest.json)',
            '- [Baseline, added identities and contribution counts](../data/expansion-2026.json)',
            '- [Browsable pending candidates](EXTERNAL_PENDING_2026.md)',
            '',
            '## Primary references · 官方依据','',
            '- [Crossref REST API documentation](https://github.com/CrossRef/rest-api-doc): date filters, cursor pagination and DOI-prefix routes.',
            '- [DataCite public REST API](https://support.datacite.org/docs/api): independent registration-agency check.',
            '- [Hugging Face official OpenAPI schema](https://huggingface.co/.well-known/openapi.json): /api/daily_papers date/month parameters, p pagination and limit up to 100.',
            '- [Hugging Face Paper Pages documentation](https://huggingface.co/docs/hub/paper-pages): paper pages currently use arXiv identifiers.',
            '',
            '## Reproduce · 复现','',
            'The harvester uses Python standard-library APIs, resumable local response caches, bounded concurrency and retry/backoff. Raw response/abstract caches stay untracked. Run:',
            '',
            '~~~powershell',
            'python scripts/harvest.py --as-of 2026-11-08',
            'python scripts/catalog.py --data-root /path/to/PaperVaultData --as-of 2026-11-08 --input techrxiv-2026=.cache/external-2026/inputs/techrxiv-2026.jsonl.gz --input preprints-2026=.cache/external-2026/inputs/preprints-2026.jsonl.gz --input huggingface-daily-2026=.cache/external-2026/inputs/huggingface-2026.jsonl.gz',
            'python scripts/report_expansion.py --build-index',
            'python scripts/metrics.py --new-only --skip-title-search',
            'python scripts/render.py',
            'python -m unittest discover -s tests -v',
            'python scripts/validate.py',
            '~~~','',
            'Replace the local dataset path as needed. Use harvest.py --refresh for a fresh sweep, including delayed registrations and changed historic feed entries; a cached rebuild reproduces the saved responses rather than certifying the current live platform state. The saved baseline IDs allow the report to regenerate without the initial private working file. Citation lookups may be quota-limited; an unavailable count stays N/A and never removes the paper from the catalog.']
    save(ROOT/'docs/EXPANSION_2026.md','\n'.join(lines))
    print('EXPANSION',json.dumps({k:v for k,v in result.items() if not k.endswith('_ids') and k not in {'pending_reasons','baseline_ids'}}),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline',type=Path)
    parser.add_argument('--build-index',action='store_true',help='Publish minimal metadata for every discovered record, without full abstracts')
    args=parser.parse_args()
    report(args.baseline,args.build_index)
