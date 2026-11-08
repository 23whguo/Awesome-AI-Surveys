"""Validate catalog invariants, local Markdown links, and generated tables."""
from __future__ import annotations
import collections
import csv
import json
from pathlib import Path
import re
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]


def main():
    with (ROOT/'data/surveys.jsonl').open(encoding='utf-8') as f:
        rows = [json.loads(line) for line in f if line.strip()]
    manifest = json.loads((ROOT/'data/manifest.json').read_text(encoding='utf-8'))
    taxonomy = json.loads((ROOT/'data/taxonomy.json').read_text(encoding='utf-8'))
    vocab = json.loads((ROOT/'data/tag-vocabulary.json').read_text(encoding='utf-8'))
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
    counts = dict(collections.Counter(p['primary_category'] for p in rows))
    if counts != manifest['category_counts']: errors.append('Manifest category counts mismatch')
    if sum(bool(p['code_url']) for p in rows) != manifest['with_code_links']: errors.append('Code count mismatch')
    with (ROOT/'data/surveys.csv').open(encoding='utf-8', newline='') as f:
        exported = list(csv.DictReader(f))
    if {p['id'] for p in exported} != ids: errors.append('CSV work identity mismatch')
    markdown_files = list(ROOT.glob('README*.md')) + list((ROOT/'docs').rglob('*.md')) + [ROOT/'CONTRIBUTING.md']
    # Generated Markdown uses simple local paths or angle-bracket-wrapped URLs.
    for path in markdown_files:
        raw = path.read_text(encoding='utf-8')
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
            if line.startswith('| ') and line.endswith(' |') and path.parent.name in {'papers','tags','years'}:
                if len(line.split('|')) != 7: errors.append('Malformed five-column table: ' + str(path))
    # Every work appears exactly once in the full primary-topic lists.
    expected = collections.Counter(p['paper_url'] for p in rows)
    actual = collections.Counter()
    for path in (ROOT/'docs/papers').glob('*.md'):
        actual.update(re.findall(r'\[paper\]\(<([^>]+)>\)', path.read_text(encoding='utf-8')))
    if expected != actual: errors.append('Primary-topic views do not match the complete catalog')
    if not (ROOT/'LICENSE').is_file(): errors.append('Missing license')
    if errors:
        for error in errors[:60]: print('ERROR', error)
        raise SystemExit(str(len(errors)) + ' validation errors')
    print('PASS:',len(rows),'unique surveys;',len(markdown_files),'Markdown files; local links, tables, CSV and metadata invariants checked.')


if __name__ == '__main__':
    main()
