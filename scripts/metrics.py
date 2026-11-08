"""Refresh citation counts (OpenAlex) and stars (GitHub) with resumable caches."""
from __future__ import annotations

import argparse
import collections
import concurrent.futures
import datetime as dt
import difflib
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / '.cache/metrics'
SELECT = 'id,doi,title,publication_year,cited_by_count,ids,locations,authorships'


def stamp():
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds')


def read_json(path, default):
    return json.loads(path.read_text(encoding='utf-8')) if path.exists() else default


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + '.tmp')
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8', newline='\n')
    temp.replace(path)


def title_key(text):
    return ''.join(c for c in unicodedata.normalize('NFKC', text or '').casefold() if c.isalnum())


def repo_name(url):
    try:
        p = urllib.parse.urlsplit(url or '')
        parts = p.path.strip('/').split('/')
        if p.hostname not in {'github.com', 'www.github.com'} or len(parts) < 2:
            return None
        owner, repo = parts[0], parts[1].removesuffix('.git')
        if not re.fullmatch(r'[A-Za-z0-9_.-]+', owner) or not re.fullmatch(r'[A-Za-z0-9_.-]+', repo):
            return None
        return (owner + '/' + repo).lower()
    except ValueError:
        return None


def github_token():
    token = os.environ.get('GH_TOKEN') or os.environ.get('GITHUB_TOKEN')
    if token:
        return token
    env = dict(os.environ, GIT_TERMINAL_PROMPT='0', GCM_INTERACTIVE='never')
    try:
        result = subprocess.run(['git', '-c', 'credential.interactive=false', 'credential', 'fill'],
                                input='protocol=https\nhost=github.com\n\n',
                                capture_output=True, text=True, env=env, timeout=20)
        return dict(line.split('=', 1) for line in result.stdout.splitlines() if '=' in line).get('password')
    except (OSError, subprocess.TimeoutExpired):
        return None


def get_json(url, headers=None, attempts=3):
    for attempt in range(attempts):
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Awesome-AI-Surveys-metrics/1.0', **(headers or {})})
            with urllib.request.urlopen(req, timeout=35) as response:
                return json.load(response), None
        except urllib.error.HTTPError as error:
            # Missing records stay unknown; never turn a lookup failure into zero.
            if error.code in {400, 401, 402, 403, 404, 410, 422, 429}:
                return None, 'http-' + str(error.code)
            if attempt == attempts - 1:
                return None, 'http-' + str(error.code)
        except (OSError, ValueError, TimeoutError):
            if attempt == attempts - 1:
                return None, 'network-error'
        time.sleep(min(2 ** attempt, 4))
    return None, 'network-error'


def source_ids(work):
    values = {str(work.get('doi') or '').lower()}
    for location in work.get('locations') or []:
        values.update(str(location.get(k) or '').lower() for k in ('landing_page_url', 'pdf_url'))
    dois, arxiv = set(), set()
    for value in values:
        m = re.search(r'doi\.org/(.+)', value)
        if m:
            dois.add(urllib.parse.unquote(m.group(1)).rstrip('/'))
        m = re.search(r'(?:arxiv[.:/]|arxiv\.org/(?:abs|pdf)/)(\d{4}\.\d{4,5})', value)
        if m:
            arxiv.add(m.group(1))
    return dois, arxiv


def authors_overlap(paper, work):
    names = {title_key(a) for a in paper.get('authors', []) if isinstance(a, str)}
    names |= {title_key(' '.join(reversed(a.split(', ')))) for a in paper.get('authors', []) if isinstance(a, str)}
    others = {title_key(a.get('author', {}).get('display_name')) for a in work.get('authorships', [])}
    return bool((names - {''}) & (others - {''}))


def accepts(paper, work):
    """Identifier matches still require compatible title; title-only matches require author evidence."""
    a, b = title_key(paper['title']), title_key(work.get('title'))
    if not a or not b:
        return False, None
    doi, aids = source_ids(work)
    ids_match = bool(set(x.lower() for x in paper['dois']) & doi or set(paper['arxiv_ids']) & aids)
    similarity = difflib.SequenceMatcher(None, a, b).ratio()
    year = work.get('publication_year')
    if year and paper.get('year') and abs(year - paper['year']) > 4:
        return False, None
    if ids_match and (a == b or similarity >= 0.92):
        return True, 'identifier+title'
    if a == b and len(a) >= 22 and authors_overlap(paper, work):
        return True, 'exact-title+author+year'
    return False, None


def openalex_request(params, refresh=False):
    # Only public query parameters are hashed and cached. API keys never enter cache filenames.
    key = hashlib.sha256(json.dumps(params, sort_keys=True).encode()).hexdigest()
    path = CACHE / 'openalex' / (key + '.json')
    if path.exists() and not refresh:
        return read_json(path, {})
    query = dict(params)
    if os.environ.get('OPENALEX_API_KEY'):
        query['api_key'] = os.environ['OPENALEX_API_KEY']
    data, error = get_json('https://api.openalex.org/works?' + urllib.parse.urlencode(query))
    result = {'fetched_at': stamp(), 'error': error, 'results': (data or {}).get('results', []),
              'count': (data or {}).get('meta', {}).get('count'),
              'cost_usd': (data or {}).get('meta', {}).get('cost_usd')}
    if data is not None:
        write_json(path, result)
    return result


def refresh_citations(papers, refresh=False, skip_title_search=False):
    found = {}
    lookup_errors = collections.Counter()
    by_doi, by_arxiv, by_title = collections.defaultdict(list), collections.defaultdict(list), collections.defaultdict(list)
    for p in papers:
        for value in p['dois']:
            by_doi[value.lower()].append(p)
        for value in p['arxiv_ids']:
            by_arxiv[value].append(p)
        by_title[title_key(p['title'])].append(p)

    def consume(response):
        if response.get('error'):
            lookup_errors[response['error']] += 1
        for work in response['results']:
            doi, aids = source_ids(work)
            possible = {p['id']: p for p in by_title[title_key(work.get('title'))]}
            for value in doi:
                for p in by_doi[value]: possible[p['id']] = p
            for value in aids:
                for p in by_arxiv[value]: possible[p['id']] = p
            for paper in possible.values():
                ok, basis = accepts(paper, work)
                if ok and isinstance(work.get('cited_by_count'), int):
                    found.setdefault(paper['id'], []).append({
                        'citation_count': work['cited_by_count'], 'citation_source': 'OpenAlex',
                        'citation_source_url': work['id'], 'citation_matched_title': work['title'],
                        'citation_match_basis': basis, 'citation_fetched_at': response['fetched_at'],
                    })

    ids = sorted(set('https://doi.org/' + x for p in papers for x in p['dois']) |
                 set('https://doi.org/10.48550/arXiv.' + x for p in papers for x in p['arxiv_ids']))
    batches = [ids[i:i+80] for i in range(0, len(ids), 80)]
    def fetch_batch(batch):
        return openalex_request({'filter': 'doi:' + '|'.join(batch), 'select': SELECT, 'per_page': 100}, refresh)
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
        for i, response in enumerate(executor.map(fetch_batch, batches), 1):
            consume(response)
            if i % 10 == 0 or i == len(batches):
                print('Citation identifier batches', i, '/', len(batches), 'matched', len(found), 'last_error', response['error'], flush=True)
    missing = [p for p in papers if not found.get(p['id'])] if not skip_title_search else []
    title_batches = [missing[i:i+15] for i in range(0, len(missing), 15)]
    def fetch_titles(batch):
        terms = ['"' + re.sub(r'["\\|]', ' ', p['title']) + '"' for p in batch]
        return openalex_request({'filter': 'title.search:' + ' OR '.join(terms), 'select': SELECT, 'per_page': 200}, refresh)
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        for i, response in enumerate(executor.map(fetch_titles, title_batches), 1):
            consume(response)
            if i % 10 == 0 or i == len(title_batches):
                print('Citation title batches', i, '/', len(title_batches), 'matched', len(found), 'last_error', response['error'], flush=True)
    metrics = {}
    for paper in papers:
        values = {m['citation_source_url']: m for m in found.get(paper['id'], [])}
        if values:
            # Different indexed editions are not added together (overlapping citations).
            best = max(values.values(), key=lambda x: (x['citation_match_basis'] == 'identifier+title', x['citation_count']))
            metrics[paper['id']] = {**best, 'citation_lookup_status': 'matched',
                                     'citation_alternative_work_ids': sorted(set(values) - {best['citation_source_url']})}
        else:
            metrics[paper['id']] = {'citation_count': None, 'citation_source': 'OpenAlex',
                                     'citation_source_url': None, 'citation_lookup_status': 'unavailable-or-unmatched',
                                     'citation_checked_at': stamp(), 'citation_lookup_errors':dict(lookup_errors)}
    print('Citation matches', len(found), '/', len(papers), 'batch errors', dict(lookup_errors), flush=True)
    return metrics


def refresh_stars(papers, token, refresh=False):
    repos = sorted({repo_name(p.get('code_url')) for p in papers} - {None})
    headers = {'Accept': 'application/vnd.github+json'}
    if token:
        headers['Authorization'] = 'Bearer ' + token
    cache = read_json(CACHE/'github.json', {})

    def fetch(repo):
        if repo in cache and not refresh:
            return repo, cache[repo]
        data, error = get_json('https://api.github.com/repos/' + repo, headers)
        result = {'github_repository': repo, 'github_stars': (data or {}).get('stargazers_count'),
                  'github_stars_url': (data or {}).get('html_url', 'https://github.com/' + repo),
                  'github_stars_fetched_at': stamp(), 'github_lookup_status': 'matched' if data else error}
        return repo, result

    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as executor:
        for i, (repo, result) in enumerate(executor.map(fetch, repos), 1):
            cache[repo] = result
            if i % 40 == 0 or i == len(repos):
                write_json(CACHE/'github.json', cache)
                print('GitHub repositories', i, '/', len(repos), flush=True)
    return cache


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--refresh', action='store_true', help='Refresh successful cached API responses')
    parser.add_argument('--new-only', action='store_true', help='Preserve previous per-paper citation records; fetch new catalog identities and new Code repository metrics')
    parser.add_argument('--skip-title-search', action='store_true', help='Use identifier batches only, avoiding expensive fallback title searches')
    args = parser.parse_args()
    with (ROOT/'data/surveys.jsonl').open(encoding='utf-8') as f:
        papers = [json.loads(line) for line in f if line.strip()]
    token = github_token()
    previous = read_json(ROOT/'data/metrics.json', {}).get('paper_metrics', {}) if args.new_only else {}
    new_papers = [p for p in papers if p['id'] not in previous]
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        citations = executor.submit(refresh_citations, new_papers, args.refresh, args.skip_title_search)
        stars = executor.submit(refresh_stars, papers, token, args.refresh)
        citation_values = citations.result()
        star_values = stars.result()
    records = {}
    for paper in papers:
        metrics = dict(citation_values.get(paper['id'], previous.get(paper['id'], {})))
        for key in list(metrics):
            if key.startswith('github_'):
                del metrics[key]
        repo = repo_name(paper.get('code_url'))
        if repo:
            metrics.update(star_values[repo])
        records[paper['id']] = metrics
    out = {'schema_version': 1, 'updated_at': stamp(),
           'citation_provider': 'OpenAlex', 'github_provider': 'GitHub REST API',
           'citation_counts_available': sum(m['citation_count'] is not None for m in records.values()),
           'github_stars_available': sum(m.get('github_stars') is not None for m in records.values()),
           'paper_metrics': records}
    write_json(ROOT/'data/metrics.json', out)
    print('METRICS', {k: v for k, v in out.items() if k != 'paper_metrics'}, flush=True)


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    main()
