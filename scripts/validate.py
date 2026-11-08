"""Validate catalog invariants, local Markdown links, and generated tables."""
from __future__ import annotations
import collections
import csv
import datetime as dt
import hashlib
import json
from pathlib import Path
import re
from urllib.parse import unquote, urlsplit
from render import ordered, PAGE_SIZE

ROOT = Path(__file__).resolve().parents[1]


def main():
    with (ROOT/'data/surveys.jsonl').open(encoding='utf-8') as f:
        rows = [json.loads(line) for line in f if line.strip()]
    manifest = json.loads((ROOT/'data/manifest.json').read_text(encoding='utf-8'))
    taxonomy = json.loads((ROOT/'data/taxonomy.json').read_text(encoding='utf-8'))
    vocab = json.loads((ROOT/'data/tag-vocabulary.json').read_text(encoding='utf-8'))
    metrics_path = ROOT/'data/metrics.json'
    metrics = json.loads(metrics_path.read_text(encoding='utf-8')) if metrics_path.exists() else None
    allowed = {c['id']: {t['id'] for t in c['topics']} for c in taxonomy}
    errors = []
    ids = set()
    for row in rows:
        if row['id'] in ids: errors.append('Duplicate work ID: ' + row['id'])
        ids.add(row['id'])
        if row['primary_topic'] not in allowed.get(row['primary_category'], set()):
            errors.append('Invalid category/topic: ' + row['id'])
        for field in ('paper_url', 'code_url'):
            value = row[field]
            if value is None and field == 'code_url': continue
            p = urlsplit(value or '')
            if p.scheme not in {'http','https'} or not p.netloc: errors.append('Invalid URL: ' + row['id'])
        if not row['sources']: errors.append('Missing provenance: ' + row['id'])
        if not row['versions']: errors.append('Missing version: ' + row['id'])
        if row['classification_needs_review']: errors.append('Unresolved included classification: ' + row['id'])
        for dim, tags in row['tags'].items():
            if not set(tags) <= set(vocab.get(dim, [])): errors.append('Unknown tag: ' + row['id'])
        if row['peer_review_status'] != 'not-independently-verified': errors.append('Unverified publication claim: ' + row['id'])
    if len(rows) != manifest['unique_surveys']: errors.append('Manifest work count mismatch')
    harvest_path=ROOT/'data/harvest-2026.json'
    if harvest_path.exists():
        harvest=json.loads(harvest_path.read_text(encoding='utf-8'))
        expansion=json.loads((ROOT/'data/expansion-2026.json').read_text(encoding='utf-8'))
        external=[json.loads(line) for line in (ROOT/'data/external-review-audit.jsonl').read_text(encoding='utf-8').splitlines() if line.strip()]
        source_map={'techrxiv':'techrxiv-2026','preprints':'preprints-2026','huggingface':'huggingface-daily-2026'}
        input_manifest={s['id']:s for s in manifest['sources']}
        if set(harvest['sources'])!=set(source_map): errors.append('External source audit is incomplete')
        for key,source in source_map.items():
            audit_source=harvest['sources'][key]
            supplied=input_manifest.get(source,{})
            if audit_source['records']!=supplied.get('counts',{}).get('records'): errors.append('Harvest/input record count mismatch: '+source)
            if audit_source['input_sha256']!=supplied.get('sha256'): errors.append('Harvest/input checksum mismatch: '+source)
            if key=='huggingface':
                days=(dt.date.fromisoformat(harvest['through'])-dt.date.fromisoformat(harvest['from'])).days+1
                if len(audit_source['partitions'])!=days or len({p['value'] for p in audit_source['partitions']})!=days:
                    errors.append('Missing or duplicate HF daily partitions')
                if audit_source['complete_within_api_scope'] and not all(p['complete'] and p['sets_agree'] for p in audit_source['monthly_crosschecks']):
                    errors.append('HF crosscheck claim inconsistent with evidence')
            elif audit_source['complete_within_api_scope']:
                if not all(p['complete'] and p['unique_records']==p['expected_records'] for p in audit_source['partitions']):
                    errors.append('Crossref partition completion claim inconsistent: '+source)
                check=audit_source['publication_date_crosscheck']
                if check['errors'] or check['unique_dois']!=check['expected_records']:
                    errors.append('Crossref date-axis crosscheck inconsistent: '+source)
        by_source_line={(r['source'],r['line']):r for r in external}
        provenance={(s['dataset'],s['line']):p['id'] for p in rows for s in p['sources']}
        for item in external:
            if item['status']=='included':
                if item['catalog_id'] not in ids or provenance.get((item['source'],item['line']))!=item['catalog_id']:
                    errors.append('External included record lacks canonical provenance')
            elif item['catalog_id'] is not None:
                errors.append('Unapproved external record has a catalog ID')
        index_manifest=json.loads((ROOT/'data/discovery-index/manifest.json').read_text(encoding='utf-8'))
        indexed=0
        for source,source_index in index_manifest.items():
            seen_records=set()
            source_total=0
            for part in source_index['parts']:
                path=ROOT/part['path']
                raw=path.read_bytes()
                if hashlib.sha256(raw).hexdigest()!=part['sha256']: errors.append('Discovery index checksum mismatch: '+part['path'])
                records=[json.loads(line) for line in raw.decode('utf-8').splitlines() if line.strip()]
                if len(records)!=part['records']: errors.append('Discovery index shard count mismatch')
                for item in records:
                    if item['record_id'] in seen_records: errors.append('Duplicate discovery ID in '+source)
                    seen_records.add(item['record_id'])
                    linked=by_source_line.get((source,item['line']))
                    if linked and (linked['source_record_id']!=item['record_id'] or linked['status']!=item['screening_status']):
                        errors.append('Discovery/candidate identity mismatch')
                source_total+=len(records)
            if source_total!=source_index['records'] or source_total!=input_manifest[source]['counts']['records']:
                errors.append('Discovery/source total mismatch: '+source)
            indexed+=source_total
        baseline=set(expansion['baseline_ids'])
        if set(expansion['added_ids'])!=ids-baseline or set(expansion['removed_ids'])!=baseline-ids:
            errors.append('Expansion added/removed identity mismatch')
        if expansion['current_surveys']!=len(ids) or expansion['net_added']!=len(ids)-len(baseline):
            errors.append('Expansion headline count mismatch')
        if expansion['pending_source_records']!=sum(x['status']=='pending' for x in external): errors.append('Pending external count mismatch')
        pending_index=(ROOT/'docs/EXTERNAL_PENDING_2026.md').read_text(encoding='utf-8')
        listed_pages=set(re.findall(r'pending/(external-2026-\d{3}\.md)',pending_index))
        actual_pages={p.name for p in (ROOT/'docs/pending').glob('external-2026-*.md')}
        if listed_pages!=actual_pages: errors.append('Missing or stale external pending pages')
        pending_groups=sum(max(0,sum(line.startswith('| ') for line in (ROOT/'docs/pending'/name).read_text(encoding='utf-8').splitlines())-2)
                           for name in actual_pages)
        if pending_groups!=expansion['pending_unique_candidates']: errors.append('Browsable pending group count mismatch')
        if expansion['full_discovery_index_records']!=indexed: errors.append('Full discovery-index total mismatch')
        if expansion['platform_exhaustiveness_guaranteed'] is not False: errors.append('Unsupported platform-completeness guarantee')
    counts = dict(collections.Counter(p['primary_category'] for p in rows))
    if counts != manifest['category_counts']: errors.append('Manifest category counts mismatch')
    if sum(bool(p['code_url']) for p in rows) != manifest['with_code_links']: errors.append('Code count mismatch')
    if metrics:
        values = metrics['paper_metrics']
        if set(values) != ids: errors.append('Metrics identities differ from catalog')
        for work_id, item in values.items():
            count = item.get('citation_count')
            stars = item.get('github_stars')
            if count is not None and (type(count) is not int or count < 0): errors.append('Invalid citation count: ' + work_id)
            if stars is not None and (type(stars) is not int or stars < 0): errors.append('Invalid stars: ' + work_id)
            if count is not None and not item.get('citation_source_url'): errors.append('Citation lacks provenance: ' + work_id)
        if sum(m.get('citation_count') is not None for m in values.values()) != metrics['citation_counts_available']:
            errors.append('Citation availability count mismatch')
        if sum(m.get('github_stars') is not None for m in values.values()) != metrics['github_stars_available']:
            errors.append('GitHub star availability count mismatch')
        with (ROOT/'data/surveys-with-metrics.csv').open(encoding='utf-8', newline='') as f:
            enriched = list(csv.DictReader(f))
        if len(enriched) != len(rows) or {p['id'] for p in enriched} != ids:
            errors.append('Enriched CSV work identity mismatch')
        for item in enriched:
            expected_metrics = values.get(item['id'], {})
            for key in ('citation_count', 'github_stars'):
                expected_value = expected_metrics.get(key)
                if item[key] != (str(expected_value) if expected_value is not None else ''):
                    errors.append('Enriched CSV metric mismatch: ' + item['id'])
    with (ROOT/'data/surveys.csv').open(encoding='utf-8', newline='') as f:
        exported = list(csv.DictReader(f))
    if {p['id'] for p in exported} != ids: errors.append('CSV work identity mismatch')
    markdown_files = list(ROOT.glob('README*.md')) + list((ROOT/'docs').rglob('*.md')) + [ROOT/'CONTRIBUTING.md']
    # Generated Markdown uses simple local paths or angle-bracket-wrapped URLs.
    for path in markdown_files:
        raw = path.read_text(encoding='utf-8')
        is_browsing = path.name.startswith('README') or path.parent.name in {'categories','papers','tags','years'} or path.stem.replace('.by-time','') in {'CATEGORIES','TAGS','YEARS'}
        if is_browsing and ('按引用' not in raw or '按时间' not in raw):
            errors.append('Missing sort selector: ' + str(path))
        if raw.count('<details') != raw.count('</details>'): errors.append('Unbalanced details: ' + str(path))
        if path.stat().st_size > 450000: errors.append('Markdown too large for reliable browsing: ' + str(path))
        for target in re.findall(r'\]\(([^\n]*?)\)', raw):
            target = target.strip().strip('<>')
            if not target or target.startswith(('http://','https://','mailto:')): continue
            relative, _, anchor = target.partition('#')
            destination = path.parent/unquote(relative) if relative else path
            if not destination.exists(): errors.append('Broken local link: ' + str(path.relative_to(ROOT)) + ' -> ' + target)
            if anchor and destination.exists() and destination.suffix == '.md' and 'id="'+anchor+'"' not in destination.read_text(encoding='utf-8'):
                errors.append('Missing explicit anchor: ' + target)
        for line in raw.splitlines():
            if line.startswith('| 📅 Year') and not line.endswith('| 💻 Code | 引用 |'):
                errors.append('Citations must immediately follow Code: ' + str(path))
            if line.startswith('| ') and line.endswith(' |') and path.parent.name in {'papers','tags','years'}:
                if len(line.split('|')) != 8: errors.append('Malformed six-column table: ' + str(path))
    # Every work appears exactly once in the full primary-topic lists.
    expected = collections.Counter(p['paper_url'] for p in rows)
    for time_view in (False, True):
        actual = collections.Counter()
        for path in (ROOT/'docs/papers').glob('*.md'):
            if ('.by-time.' in path.name) != time_view: continue
            actual.update(re.findall(r'\[paper\]\(<([^>]+)>\)', path.read_text(encoding='utf-8')))
        if expected != actual: errors.append('Primary-topic views do not match catalog: time=' + str(time_view))
    groups = collections.defaultdict(list)
    for row in rows:
        row['_metrics'] = (metrics or {}).get('paper_metrics', {}).get(row['id'], {})
        groups[(row['primary_category'], row['primary_topic'])].append(row)
    for (category, topic), papers in groups.items():
        for mode in ('citations','time'):
            actual_urls = []
            for page in range((len(papers)+PAGE_SIZE-1)//PAGE_SIZE):
                stem = category+'-'+topic + ('-'+str(page+1) if page else '')
                path = ROOT/'docs/papers'/(stem+('.by-time' if mode=='time' else '')+'.md')
                if path.exists():
                    actual_urls.extend(re.findall(r'\[paper\]\(<([^>]+)>\)', path.read_text(encoding='utf-8')))
            if actual_urls != [p['paper_url'] for p in ordered(papers,mode)]:
                errors.append('Incorrect sorted pagination: '+category+'/'+topic+' '+mode)
    if not (ROOT/'LICENSE').is_file(): errors.append('Missing license')
    if errors:
        for error in errors[:60]: print('ERROR', error)
        raise SystemExit(str(len(errors)) + ' validation errors')
    print('PASS:',len(rows),'unique surveys;',len(markdown_files),'Markdown files; local links, tables, CSV and metadata invariants checked.')


if __name__ == '__main__':
    main()
