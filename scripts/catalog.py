"""Offline, reproducible screening and classification of PaperVault JSONL."""
from __future__ import annotations

import argparse
import collections
import csv
import datetime as dt
import gzip
import hashlib
import html
import json
from pathlib import Path
import re
import sys
import unicodedata
from urllib.parse import urlsplit, urlunsplit, unquote

from taxonomy import TAXONOMY, TAG_RULES

ROOT = Path(__file__).resolve().parents[1]
MARKER = re.compile(r'\b(survey|review|overview|tutorial|taxonomy|perspective|meta-analysis|state.of.the.art)\b', re.I)
REVIEW_EVIDENCE = re.compile(
    r'(?:(?:this|our|the present)\s+(?:paper|article|work|study|survey|review)|we)\s+'
    r'(?:(?:aims? to|provides?|presents?|offers?|conducts?|performs?|systematically|comprehensively|critically|extensively|a|an|the|first|comprehensive|systematic|in.depth|up.to.date|critical|scoping|mapping|detailed|literature|broad|thorough)\s+){0,7}'
    r'(?:surveys?|reviews?|overviews?|synthesi[sz](?:es?|ing)|summari[sz](?:es?|ing))\b|'
    r'\b(?:systematic|comprehensive|scoping|literature|mapping|critical|extensive)\s+(?:literature\s+)?(?:review|survey)\b|'
    r'\bsurvey(?:s|ing)?\s+(?:the\s+)?(?:literature|existing|recent|state.of.the.art)|'
    r'\breview(?:s|ing)?\s+(?:the\s+)?(?:literature|existing|recent|state.of.the.art)', re.I)
EMPIRICAL_SURVEY = re.compile(
    r'\b(?:survey(?:ed|ing)?\s+(?:of\s+)?\d+|survey study|user survey|online survey|'
    r'survey responses|survey simulation|survey experiment|survey participants|survey respondents|'
    r'questionnaire|nationally representative|cross.sectional survey|survey data|survey instrument|'
    r'uav survey|lidar survey|sky survey|galaxy survey|galactic survey|redshift survey)\b', re.I)
NON_REVIEW = re.compile(
    r'\b(?:peer.review|code review|review generation|review summarization|review summarisation|'
    r'review helpfulness|review reading|review response|review recommendation|review sentiment|'
    r'review manipulation|review bombing|review detection|review prediction|review rating|'
    r'review based|review.based|review.driven|product review|customer review|online review|'
    r'book review|literature review generation|survey generation|survey simulation|survey talk)\b', re.I)
AI_SCOPE = re.compile(
    r'\b(?:artificial intelligence|machine learning|deep learning|neural|language models?|llms?|'
    r'natural language|computer vision|reinforcement learning|representation learning|'
    r'generative model|diffusion model|knowledge graph|knowledge representation|'
    r'information retrieval|recommender|recommendation system|data mining|'
    r'causal inference|causal discovery|causal learning|fuzzy|swarm intelligence|'
    r'evolutionary computation|genetic algorithm|automated reasoning|theorem proving|'
    r'neuro.symbolic|neurosymbolic|robot learning|robotic learning|embodied intelligence|'
    r'multi.agent system|multiagent system|intelligent agent|graph learning|'
    r'self.supervised|transfer learning|federated learning|learning.based)\b', re.I)
AI_VENUES = {'ACL', 'EMNLP', 'NAACL', 'EACL', 'COLING', 'CVPR', 'ICCV', 'ECCV', 'WACV',
             'BMVC', 'NIPS', 'NEURIPS', 'ICML', 'ICLR', 'AAAI', 'IJCAI', 'AISTATS', 'COLT',
             'UAI', 'JMLR', 'MLJ', 'AI', 'TPAMI', 'IJCV', 'TNNLS', 'TASLP', 'RECSYS', 'SIGIR'}
CAT_BY_ID = {c['id']: c for c in TAXONOMY}


def normalized_title(text):
    text = html.unescape(unicodedata.normalize('NFKC', text)).casefold()
    text = re.sub(r'\b(?:abstract reprint|extended abstract)\b', '', text)
    return ''.join(c for c in text if c.isalnum())


def normalize_url(value):
    if not isinstance(value, str):
        return None
    value = html.unescape(value.strip()).rstrip('.,;')
    if not value or value in {'#', 'N/A', 'None', 'null'}:
        return None
    try:
        p = urlsplit(value)
        if p.scheme not in {'http', 'https'} or not p.netloc or p.username or p.password:
            return None
        if re.search(r'\s|[<>"\x00-\x1f]', value):
            return None
        return urlunsplit(('https', p.netloc.lower(), p.path.rstrip('/'), p.query, ''))
    except ValueError:
        return None


def arxiv_id(url):
    m = re.search(r'(?:arxiv\.org/(?:abs|pdf)/)(\d{4}\.\d{4,5})(?:v\d+)?', url or '', re.I)
    return m.group(1) if m else None


def author_keys(authors):
    return {''.join(sorted(re.findall(r'[a-z]+', unicodedata.normalize('NFKD', a).casefold())))
            for a in authors if isinstance(a, str) and len(a.strip()) > 3}


def venue_year(record):
    m = re.fullmatch(r'(.*?)(19\d{2}|20\d{2})', record.get('conf', ''))
    return (m.group(1), int(m.group(2))) if m else (record.get('conf', 'Unknown'), None)


def screen(record):
    """Return include / review / exclude, with a precise metadata-based reason."""
    title = record.get('paper_name', '').strip()
    abstract = record.get('paper_abstract') or ''
    if not MARKER.search(title):
        return 'exclude', 'No review-type discovery marker in title'
    venue, _ = venue_year(record)
    topical_title = re.search(r'\b(?:AI|NLP|LLMs?|GNNs?|deep learning|machine learning|neural|learning.based|generative|vision|image|speech|audio|music|robot|robotic|embodied|agentic|agents?|knowledge|recommender|recommendation|retrieval|causal|fuzzy|evolutionary|hyperspectral|point cloud|segmentation|time.series|forecasting)\b', title, re.I)
    ai_categories = {'cs.AI', 'cs.LG', 'cs.CV', 'cs.CL', 'cs.IR', 'cs.RO', 'cs.MA', 'cs.NE', 'stat.ML'}
    primary_categories = record.get('arxiv_categories', [])[:1]
    if not (AI_SCOPE.search(title) or topical_title or venue.upper() in AI_VENUES or
            (set(primary_categories) & ai_categories and AI_SCOPE.search(abstract))):
        return 'exclude', 'No explicit AI/ML relevance in available metadata'
    evidence = REVIEW_EVIDENCE.search(abstract)
    if re.search(r'\b(?:review analysis|performing (?:scientific )?literature review|automating (?:scientific )?literature review)\b', title, re.I) and not re.search(r':\s*(?:a\s+)?(?:survey|review)\b', title, re.I):
        return 'exclude', 'Analysis or automation of reviews, not a review article'
    is_survey = bool(re.search(r'\bsurvey\b', title, re.I))
    is_review = bool(re.search(r'\breview\b|\bmeta.analysis\b', title, re.I))
    strong = bool(re.search(r'\b(?:systematic|comprehensive|scoping|literature|critical|mapping)\s+(?:literature\s+)?(?:review|survey)\b|\bmeta.analysis\b', title, re.I))
    if re.search(r'\b(?:review generation|survey generation|survey instrument|community survey|global survey approach|survey simulation|multi.survey|workflow for the review|framework for.*review)\b', title, re.I) and not re.search(r':\s*(?:a\s+)?(?:comprehensive\s+|systematic\s+)?(?:survey|review)\b', title, re.I):
        return 'exclude', 'Review/survey production or empirical survey rather than a literature synthesis'
    if re.search(r'\b(?:case study|benchmark|framework|corpus|tool)\b', title, re.I) and not re.search(r'\b(?:scoping|systematic|literature|comprehensive|critical|narrative)\s+(?:literature\s+)?(?:review|survey)\b|:\s*(?:a\s+)?(?:survey|review)\b|^a (?:survey|review)\b', title, re.I):
        return 'review', 'Possible hybrid method/benchmark paper; requires editorial confirmation'
    title_lit = bool(re.search(r'\b(?:a|an|the|comprehensive|systematic|literature|critical|scoping)\s+(?:\w+[ -]){0,3}(?:survey|review)\b|\b(?:survey|review)\s+(?:of|on|for|and|:)|:\s*(?:a\s+)?(?:survey|review)\b', title, re.I))
    empirical = EMPIRICAL_SURVEY.search(title + ' ' + abstract)
    if re.search(r'\b(?:survey talk|tutorial proposal|tutorial report|keynote|panel discussion)\b', title, re.I):
        return 'exclude', 'Talk, proposal or event record rather than a review article'
    if re.search(r'\b(?:overview of|overview)\b', title, re.I) and re.search(r'\b(?:challenge|shared task|industry track|task \d|mission|instrument|campaign)\b', title, re.I) and not evidence:
        return 'exclude', 'Task, challenge or instrument overview without literature-review evidence'
    if re.search(r'\b(?:survey instrument|survey simulation|survey responses|survey participants|survey respondents|survey data|FIRST survey|sky survey|redshift survey|galaxy survey|case study|expert review|human review|review support|review table generation)\b', title, re.I) and not strong:
        return 'exclude', 'Research instrument, case study or review task rather than a literature synthesis'
    if NON_REVIEW.search(title) and not (strong or (title_lit and evidence)):
        return 'exclude', 'Review/survey is the research task or data, not the article type'
    if empirical and not (strong or evidence):
        return 'exclude', 'Empirical questionnaire or observational survey without literature-review evidence'
    if (is_survey and (title_lit or strong or evidence)) or (is_review and (title_lit or strong)):
        if empirical and not strong and not evidence:
            return 'review', 'Survey wording is ambiguous with empirical research'
        return 'include', 'Explicit review-type title' + (' and abstract synthesis evidence' if evidence else '; abstract evidence unavailable or inconclusive')
    if evidence and re.search(r'\boverview\b|state.of.the.art|\btaxonomy\b', title, re.I) and not re.search(r'\b(?:benchmark|framework|tool|system|dataset|challenge|shared task)\b', title, re.I):
        return 'include', 'Overview/taxonomy title supported by abstract synthesis evidence'
    if re.search(r'\btutorial\b', title, re.I):
        return 'review', 'Tutorial requires editorial confirmation as a self-contained review article'
    return 'review', 'Possible review; insufficient unambiguous synthesis evidence'


def classify(title, abstract='', arxiv_categories=()):
    focus = title
    if ':' in title:
        before, after = title.split(':', 1)
        if MARKER.search(before) or re.match(r'\s*(?:a |an |the |comprehensive |systematic )*(?:survey|review|overview)\b', after, re.I):
            focus = before
    scored = []
    for c in TAXONOMY:
        for topic in c['topics']:
            title_matches = list(re.finditer(topic['pattern'], focus, re.I))
            score = (24 if title_matches else 0) + min(12, len(title_matches) * 4)
            if title_matches:
                # Broad objects lose to a specific task, constraint or application in the title.
                if c['id'] == '17-applications': score += 26
                if c['id'] == '16-systems': score += 24
                if c['id'] == '15-trustworthy': score += 25
                if c['id'] == '14-embodied': score += 9
                if c['id'] == '13-agents': score += 8
                if c['id'] in {'03-data', '09-knowledge', '10-retrieval', '11-temporal', '12-decision'}: score += 5
                if topic['id'] in {'llm', 'general', 'other', 'foundation'}: score -= 7
                if c['id'] == '05-language' and topic['id'] != 'llm': score += 3
                if c['id'] == '12-decision' and topic['id'] == 'marl': score += 12
                if c['id'] == '14-embodied' and topic['id'] == 'vla': score += 5
                if c['id'] == '08-multimodal': score += 6
                if c['id'] == '06-vision': score += 4
                if c['id'] == '07-audio': score += 12
                if c['id'] == '08-multimodal' and re.search(r'multimodal|multi.modal', focus, re.I): score += 8
            scored.append((score, c['id'], topic['id'], [m.group(0) for m in title_matches[:3]]))
    scored.sort(key=lambda x: (-x[0], x[1], x[2]))
    best = scored[0]
    if best[0] < 9:
        return '01-general-ai', 'general', 'Broad or unresolved scope; metadata classification needs refinement', True
    return best[1], best[2], 'Title cues: ' + ', '.join(best[3]) if best[3] else 'Abstract-based topical cues', not bool(best[3])


def tags_for(title, abstract=''):
    # Only title-explicit tags are published. Abstract mentions can be incidental.
    return {dimension: sorted(tag for tag, pattern in rules.items() if re.search(pattern, title, re.I))
            for dimension, rules in TAG_RULES.items()}


def review_type(title):
    for kind, pattern in [('meta-analysis', r'meta.analysis'), ('scoping-review', r'scoping review'),
                          ('systematic-review', r'systematic.*review'), ('systematic-survey', r'systematic.*survey'),
                          ('survey', r'\bsurvey\b'), ('review', r'\breview\b'), ('overview', r'overview'),
                          ('tutorial', r'tutorial'), ('taxonomy', r'taxonomy')]:
        if re.search(pattern, title, re.I): return kind
    return 'overview'


def record_key(d):
    return normalized_title(d.get('paper_name', ''))


def compatible(a, b):
    if record_key(a) != record_key(b): return False
    va, ya = venue_year(a); vb, yb = venue_year(b)
    if ya is None or yb is None or abs(ya - yb) > 3: return False
    ak = author_keys(a.get('paper_authors', [])); bk = author_keys(b.get('paper_authors', []))
    return bool(ak & bk) or (not ak and not bk and ya == yb)


def deduplicate(records):
    groups = []
    by_title = collections.defaultdict(list)
    by_url = collections.defaultdict(list)
    for row in records:
        key = record_key(row)
        url = normalize_url(row.get('paper_url'))
        identity = arxiv_id(url) or url
        matches = set()
        for idx in by_title[key] + by_url[identity]:
            if groups[idx] and any(compatible(row, prev) for prev in groups[idx]): matches.add(idx)
        if matches:
            target = min(matches)
            groups[target].append(row)
            for idx in sorted(matches - {target}):
                groups[target].extend(groups[idx]); groups[idx] = []
                for old in groups[target]:
                    by_title[record_key(old)].append(target)
                    u = normalize_url(old.get('paper_url'))
                    by_url[arxiv_id(u) or u].append(target)
        else:
            target = len(groups); groups.append([row])
        by_title[key].append(target); by_url[identity].append(target)
    return [g for g in groups if g]


def make_paper(group, overrides):
    # Prefer an archival venue record; never infer peer review from a venue label.
    group.sort(key=lambda r: (venue_year(r)[0].upper() == 'ARXIV',
                             not bool(normalize_url(r.get('paper_url'))),
                             venue_year(r)[1] or 9999, -len(r.get('paper_abstract') or '')))
    primary = group[0]; title = primary['paper_name'].strip()
    abstract_record = max(group, key=lambda x: len(x.get('paper_abstract') or ''))
    abstract = abstract_record.get('paper_abstract') or ''
    cid, topic, reason, uncertain = classify(title, abstract)
    override = overrides.get(normalized_title(title), {})
    if override:
        if not override.get('reason'): raise ValueError('Override requires reason: ' + title)
        cid = override.get('primary_category', cid); topic = override.get('primary_topic', topic)
        reason = override['reason']; uncertain = False
    venue, year = venue_year(primary)
    versions = []; seen = set(); aids = set(); dois = set(); sources = []
    code_links = []
    for r in group:
        url = normalize_url(r.get('paper_url')); v, y = venue_year(r)
        if arxiv_id(url): aids.add(arxiv_id(url))
        if url and 'doi.org/' in url: dois.add(unquote(url.split('doi.org/', 1)[1]).lower())
        if (url, v, y) not in seen:
            seen.add((url, v, y)); versions.append({'venue': 'arXiv' if v.upper() == 'ARXIV' else ('NeurIPS' if v.upper() == 'NIPS' else v), 'year': y, 'url': url,
                'source_first_submitted_at': r.get('arxiv_first_submitted_at_utc')})
        sources.append({'dataset': r['_source'], 'line': r['_line'], 'venue_label': r.get('conf')})
        code = normalize_url(r.get('paper_code'))
        if code and code not in code_links: code_links.append(code)
        for match in re.finditer(r'https?://github\.com/([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+)', r.get('paper_abstract') or ''):
            candidate = normalize_url(match.group(0).rstrip('.'))
            if candidate and candidate not in code_links: code_links.append(candidate)
    evidence = REVIEW_EVIDENCE.search(abstract)
    excerpt = abstract[max(0, evidence.start()-30):evidence.end()+150] if evidence else None
    return {
        'id': 'survey-' + hashlib.sha256(normalized_title(title).encode()).hexdigest()[:16],
        'title': title, 'authors': primary.get('paper_authors') or [], 'year': year,
        'venue': 'arXiv' if venue.upper() == 'ARXIV' else ('NeurIPS' if venue.upper() == 'NIPS' else venue),
        'paper_url': normalize_url(primary.get('paper_url')), 'code_url': code_links[0] if code_links else None,
        'code_links': code_links, 'code_link_basis': 'source metadata / abstract; not independently verified' if code_links else None,
        'arxiv_ids': sorted(aids), 'dois': sorted(dois), 'versions': versions,
        'primary_category': cid, 'primary_topic': topic, 'tags': tags_for(title),
        'review_type': review_type(title), 'classification_basis': reason,
        'classification_needs_review': uncertain,
        'screening_status': 'metadata-screened', 'screening_evidence': excerpt,
        'peer_review_status': 'not-independently-verified', 'literature_coverage_until': None,
        'arxiv_categories': sorted({v for r in group for v in r.get('arxiv_categories', [])}),
        'sources': sources,
    }


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8', newline='\n')


def write_jsonl(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', encoding='utf-8', newline='\n') as out:
        for row in rows: out.write(json.dumps(row, ensure_ascii=False, separators=(',', ':')) + '\n')


def build(inputs, as_of):
    overrides = json.loads((ROOT / 'data/overrides.json').read_text(encoding='utf-8'))['papers']
    selected = []; pending = []; stats = collections.Counter(); source_stats = []
    for name, path in inputs:
        sha = hashlib.sha256()
        with path.open('rb') as f:
            for chunk in iter(lambda: f.read(1024*1024), b''): sha.update(chunk)
        counts = collections.Counter(); years = collections.Counter()
        with gzip.open(path, 'rt', encoding='utf-8') as f:
            for line_no, line in enumerate(f, 1):
                row = json.loads(line); counts['records'] += 1
                _, year = venue_year(row); years[str(year)] += 1
                title = row.get('paper_name', '')
                if not MARKER.search(title): continue
                counts['title_candidates'] += 1
                row['_source'] = name; row['_line'] = line_no
                aid = row.get('arxiv_id') or arxiv_id(row.get('paper_url'))
                if aid:
                    month = int(aid[2:4]); aid_year = 2000 + int(aid[:2])
                    if (aid_year, month) > (as_of.year, as_of.month):
                        counts['excluded_future_identifier_month'] += 1; continue
                date = row.get('arxiv_first_submitted_at_utc')
                if date:
                    try:
                        if dt.date.fromisoformat(date[:10]) > as_of:
                            counts['excluded_future_source_date'] += 1; continue
                        if aid and (int(date[:4]), int(date[5:7])) != (2000 + int(aid[:2]), int(aid[2:4])):
                            counts['candidate_date_month_mismatch'] += 1
                    except ValueError: counts['invalid_source_date'] += 1
                decision, reason = screen(row)
                ov = overrides.get(normalized_title(title), {})
                if 'decision' in ov:
                    if not ov.get('reason'): raise ValueError('Override requires a reason')
                    decision = ov['decision']; reason = ov['reason']
                if decision == 'include' and not normalize_url(row.get('paper_url')):
                    decision = 'review'; reason = 'Missing or malformed paper URL'
                counts[decision] += 1; stats[decision] += 1
                if decision == 'include': selected.append(row)
                elif decision == 'review':
                    pending.append({'title': title, 'year': year, 'venue_label': row.get('conf'),
                                    'paper_url': normalize_url(row.get('paper_url')), 'reason': reason,
                                    'source': {'dataset': name, 'line': line_no}})
        source_stats.append({'id': name, 'file': path.name, 'bytes': path.stat().st_size,
                             'sha256': sha.hexdigest(), 'counts': dict(counts), 'years': dict(sorted(years.items()))})
        print(name, dict(counts), flush=True)
    groups = deduplicate(selected)
    papers = [make_paper(g, overrides) for g in groups]
    resolved = []
    for paper in papers:
        if paper['classification_needs_review']:
            pending.append({'title': paper['title'], 'year': paper['year'], 'venue_label': paper['venue'],
                            'paper_url': paper['paper_url'], 'reason': 'Review type passed; primary subject needs editorial classification',
                            'source': paper['sources'][0]})
        else:
            resolved.append(paper)
    papers = resolved
    # Same-title different-author works keep separate IDs, rather than silently collapsing.
    ids = collections.Counter()
    for p in papers:
        ids[p['id']] += 1
        if ids[p['id']] > 1:
            p['id'] += '-' + hashlib.sha256((str(p['year']) + '|'.join(p['authors'])).encode()).hexdigest()[:8]
    papers.sort(key=lambda p: (p['primary_category'], p['primary_topic'], -(p['year'] or 0), p['title'].casefold()))
    write_jsonl(ROOT/'data/surveys.jsonl', papers)
    write_jsonl(ROOT/'data/review_queue.jsonl', pending)
    with (ROOT/'data/surveys.csv').open('w', encoding='utf-8', newline='') as f:
        fields = ['id', 'year', 'title', 'venue', 'paper_url', 'code_url', 'primary_category', 'primary_topic', 'review_type', 'tags']
        out = csv.DictWriter(f, fieldnames=fields); out.writeheader()
        for p in papers:
            row = {k: p[k] for k in fields}; row['tags'] = json.dumps(row['tags'], ensure_ascii=False)
            out.writerow(row)
    write_json(ROOT/'data/taxonomy.json', TAXONOMY)
    write_json(ROOT/'data/tag-vocabulary.json', {d: sorted(rules) for d, rules in TAG_RULES.items()})
    manifest = {
        'schema_version': 1, 'as_of': as_of.isoformat(), 'sources': source_stats,
        'source_records': sum(s['counts']['records'] for s in source_stats),
        'screened_in_source_records': len(selected), 'unique_surveys': len(papers),
        'merged_duplicate_records': len(selected)-len(groups), 'review_queue_records': len(pending),
        'unresolved_classification_works': len(groups)-len(papers),
        'with_code_links': sum(bool(p['code_url']) for p in papers),
        'cross_source_works': sum(len({x['dataset'] for x in p['sources']}) > 1 for p in papers),
        'classification_needs_review': sum(p['classification_needs_review'] for p in papers),
        'category_counts': dict(collections.Counter(p['primary_category'] for p in papers)),
        'year_counts': dict(sorted(collections.Counter(str(p['year']) for p in papers).items())),
        'notes': ['Metadata-screened collection; not a systematic review or an independently verified publication index.',
                  'ArXiv year follows identifier year. Source submission dates are preserved without correction.',
                  'DOIs, venues, code links and peer-review status are not inferred or fabricated.',
                  'Identifiers in future months and source submission dates after as_of are excluded.',
                  'Original source files, full abstracts and machine-local paths are not redistributed.'],
    }
    write_json(ROOT/'data/manifest.json', manifest)
    print('RESULT', json.dumps({k:v for k,v in manifest.items() if k not in {'sources','notes'}}, ensure_ascii=False), flush=True)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--data-root', type=Path, help='Directory containing official/ and arxiv/ PaperVault-format files')
    p.add_argument('--input', action='append', default=[], help='Additional input as source-id=path.jsonl.gz')
    p.add_argument('--as-of', default=dt.datetime.now(dt.timezone(dt.timedelta(hours=8))).date().isoformat())
    args = p.parse_args(); inputs = []
    if args.data_root:
        inputs.append(('papervault-official', args.data_root/'official/cache.jsonl.gz'))
        inputs.extend(('arxiv-'+str(y), args.data_root/f'arxiv/arxiv_{y}.jsonl.gz') for y in (2024,2025,2026))
    for spec in args.input:
        name, path = spec.split('=',1); inputs.append((name, Path(path)))
    if not inputs: p.error('Supply --data-root or --input')
    for _, path in inputs:
        if not path.is_file(): p.error('Input does not exist: ' + str(path))
    build(inputs, dt.date.fromisoformat(args.as_of))


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    main()
