"""Build Survey Radar from the committed catalog. No network or raw datasets required."""
from __future__ import annotations

import argparse
from collections import Counter
import datetime as dt
import html
import json
from pathlib import Path
import re
import shutil
from urllib.parse import urlsplit
from xml.sax.saxutils import escape as xml_escape

ROOT = Path(__file__).resolve().parents[1]
REPO = 'https://github.com/23whguo/Awesome-AI-Surveys'
DEFAULT_URL = 'https://23whguo.github.io/Awesome-AI-Surveys'
ROUTES = {'': ('总览', 'Overview', '◉'), 'library': ('综述库', 'Library', '▤'),
          'compare': ('对比', 'Compare', '⇄'), 'trends': ('趋势', 'Trends', '↗'),
          'coverage': ('文献覆盖', 'Coverage', '◷'), 'landscape': ('主题地图', 'Landscape', '▦'),
          'updates': ('更新', 'Updates', '↻'), 'about': ('关于', 'About', 'ⓘ')}


def read_json(path):
    return json.loads((ROOT / path).read_text(encoding='utf-8'))


def safe_url(value):
    if not isinstance(value, str):
        return None
    parsed = urlsplit(value)
    return value if parsed.scheme in ('https', 'http') and parsed.netloc and not parsed.username else None


def source_date(paper):
    dates = []
    for version in paper.get('versions', []):
        value = version.get('source_first_submitted_at')
        try:
            date = dt.date.fromisoformat(value[:10])
        except (ValueError, TypeError):
            continue
        if date.year == paper.get('year') and version.get('year') == paper.get('year'):
            dates.append(date.isoformat())
    return min(dates) if dates else None


def compact(paper, metric):
    """Only searchable metadata; provenance lives in per-record shards."""
    return {key: value for key, value in {
        'id': paper['id'], 'title': paper['title'], 'authors': paper.get('authors', []),
        'year': paper.get('year'), 'date': source_date(paper), 'venue': paper.get('venue'),
        'category': paper['primary_category'], 'topic': paper.get('primary_topic'),
        'tags': paper.get('tags', {}), 'review_type': paper.get('review_type'),
        'paper_url': safe_url(paper.get('paper_url')), 'code_url': safe_url(paper.get('code_url')),
        'citations': metric.get('citation_count'), 'stars': metric.get('github_stars'),
        'coverage': paper.get('literature_coverage_until'),
        'sources': sorted({s.get('dataset', 'unknown') for s in paper.get('sources', [])}),
    }.items()}


def build(output, site_url=DEFAULT_URL):
    parsed = urlsplit(site_url.rstrip('/'))
    if parsed.scheme not in ('https', 'http') or not parsed.netloc or parsed.query or parsed.fragment:
        raise ValueError('site-url must be an absolute HTTP(S) URL without query or fragment')
    site_url = site_url.rstrip('/')
    base = parsed.path.rstrip('/') + '/'
    output = Path(output).resolve()
    # Copy/overwrite owned files only. Never recursively delete an arbitrary output path.
    if output == ROOT or output in ROOT.parents or any(output == ROOT / name or (ROOT / name) in output.parents for name in ('data', 'site', 'scripts', 'tests', '.github')):
        raise ValueError('Choose a separate build directory')
    output.mkdir(parents=True, exist_ok=True)
    taxonomy = read_json('data/taxonomy.json')
    metrics = read_json('data/metrics.json')
    manifest = read_json('data/manifest.json')
    expansion = read_json('data/expansion-2026.json')
    papers = [json.loads(line) for line in (ROOT / 'data/surveys.jsonl').read_text(encoding='utf-8').splitlines() if line]
    if len({p['id'] for p in papers}) != len(papers):
        raise ValueError('Duplicate paper IDs')
    if any(not re.fullmatch(r'survey-[a-f0-9]+', p['id']) for p in papers):
        raise ValueError('Unsafe paper ID')
    records = [compact(p, metrics['paper_metrics'].get(p['id'], {})) for p in papers]
    summary = {'as_of': manifest['as_of'], 'metrics_updated_at': metrics['updated_at'],
               'total': len(records), 'categories': len(taxonomy),
               'citations_available': sum(p['citations'] is not None for p in records),
               'stars_available': sum(p['stars'] is not None for p in records),
               'code_available': sum(bool(p['code_url']) for p in records),
               'coverage_available': sum(bool(p['coverage']) for p in records),
               'pending': expansion['pending_unique_candidates'], 'added': expansion['net_added'],
               'discovered': expansion['full_discovery_index_records']}

    def write(path, value):
        target = output / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(value, encoding='utf-8', newline='\n')

    def dump(path, value):
        write(path, json.dumps(value, ensure_ascii=False, separators=(',', ':')) + '\n')

    for source in (ROOT / 'site/assets').rglob('*'):
        if source.is_file():
            target = output / source.relative_to(ROOT / 'site')
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
    for filename in ('LICENSE', 'UPSTREAM.md'):
        shutil.copyfile(ROOT / 'site' / filename, output / filename)
    write('.nojekyll', '')
    dump('data/catalog.json', {'records': records, 'taxonomy': taxonomy, 'summary': summary})
    for filename in ('surveys.jsonl', 'metrics.json', 'taxonomy.json', 'manifest.json', 'expansion-2026.json'):
        shutil.copyfile(ROOT / 'data' / filename, output / 'data' / filename)

    e = lambda value: html.escape(str(value or ''), quote=True)

    def anchor(url, label):
        return f'<a href="{e(url)}" rel="noopener noreferrer">{e(label)}</a>' if safe_url(url) else 'N/A'

    def shell(route, title, content, description=None, paper_id=None):
        canonical = site_url + ('/' + route.strip('/') + '/' if route else '/')
        nav = ''.join(f'<a href="{base}{slug + "/" if slug else ""}" class="{"active" if slug == route else ""}"><span aria-hidden="true">{icon}</span> <span data-zh="{zh}" data-en="{en}">{zh}</span></a>' for slug, (zh, en, icon) in ROUTES.items())
        config = json.dumps({'base': base, 'route': route, 'paperId': paper_id, 'repo': REPO}, ensure_ascii=True).replace('<', '\\u003c')
        desc = description or '按主分类与多标签发现 AI 综述。搜索、筛选、引用排序、收藏、对比与可追溯的数据来源。'
        return f'''<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{e(title)} · Survey Radar</title><meta name="description" content="{e(desc)}"><meta name="theme-color" content="#165a66">
<link rel="canonical" href="{e(canonical)}"><meta property="og:title" content="{e(title)} · Survey Radar"><meta property="og:description" content="{e(desc)}"><meta property="og:type" content="website"><meta property="og:url" content="{e(canonical)}">
<link rel="icon" href="{base}assets/radar.svg" type="image/svg+xml"><link rel="alternate" type="application/rss+xml" title="Survey Radar updates" href="{base}feed.xml">
<link rel="stylesheet" href="{base}assets/upstream/design-system.css"><link rel="stylesheet" href="{base}assets/upstream/styles.css"><link rel="stylesheet" href="{base}assets/survey.css">
<script id="site-config" type="application/json">{config}</script><script type="module" src="{base}assets/app.js"></script></head>
<body><a class="skip-link" href="#main">跳至内容 / Skip to content</a><header class="radar-header"><div class="header-top"><a class="radar-brand" href="{base}"><img src="{base}assets/radar.svg" width="42" height="42" alt=""><strong>Survey Radar<span class="brand-sub">AI SURVEYS, IN VIEW</span></strong></a><div class="header-actions"><button id="language" aria-label="Switch language">EN</button><a href="{base}feed.xml" aria-label="RSS updates">RSS</a><a href="{REPO}" aria-label="GitHub repository">GitHub ↗</a></div></div><nav class="radar-nav" aria-label="主导航 / Main navigation">{nav}</nav></header>
<div class="snapshot-bar"><span data-zh="数据快照" data-en="Data snapshot">数据快照</span> {manifest['as_of']} <span class="snapshot-sep">·</span> {len(records):,} <span data-zh="篇综述 · 元数据筛选" data-en="surveys · metadata screened">篇综述 · 元数据筛选</span><a href="{base}about/" data-zh="来源与覆盖说明 ↗" data-en="Sources & limitations ↗">来源与覆盖说明 ↗</a></div>
<main id="main" class="radar-main" tabindex="-1">{content}</main>
<footer class="radar-footer"><span>Survey Radar · <a href="{REPO}">Awesome AI Surveys</a></span><span><a href="{base}about/" data-zh="方法与来源" data-en="Method & sources">方法与来源</a> · <a href="{base}LICENSE">AGPL-3.0</a> · <a href="{base}UPSTREAM.md">Benchmark Radar attribution</a></span></footer><div id="toast" role="status" aria-live="polite"></div></body></html>'''

    fallback = '<section class="intro"><p class="eyebrow">AWESOME AI SURVEYS</p><h1>让研究全景，触手可及。</h1><p>一个主分类，多维标签。发现、比较和追踪 AI 领域的综述。</p></section>'
    fallback += '<p class="loading" role="status">正在加载综述库 / Loading the survey library…</p><noscript><p>交互搜索需要 JavaScript。以下目录及每篇详情可直接浏览。</p></noscript>'
    fallback += '<div class="fallback-categories">' + ''.join(f'<a href="{base}library/?category={c["id"]}">{e(c["name_zh"])} / {e(c["name"])}</a>' for c in taxonomy) + '</div>'
    for route, (zh, en, _) in ROUTES.items():
        write((route + '/' if route else '') + 'index.html', shell(route, zh + ' / ' + en, '<div id="app">' + fallback + '</div>'))
    cats = {c['id']: c for c in taxonomy}
    sitemap = [site_url + ('/' + route + '/' if route else '/') for route in ROUTES]
    for paper, record in zip(papers, records):
        pid = paper['id']
        metric = metrics['paper_metrics'].get(pid, {})
        dump(f'data/papers/{pid}.json', {'paper': paper, 'metrics': metric})
        category = cats[paper['primary_category']]
        cite = record['citations'] if record['citations'] is not None else 'N/A'
        stars = f' (★ {record["stars"] if record["stars"] is not None else "N/A"})' if record['code_url'] else ''
        fields = [('作者 / Authors', ', '.join(paper.get('authors', []))), ('年份 / Year', paper.get('year')),
                  ('渠道 / Venue', paper.get('venue')), ('源提交日期 / Source submission date', record['date'] or '未提供 / Not supplied'),
                  ('文献覆盖截止 / Literature coverage through', paper.get('literature_coverage_until') or '未核验 / Not verified'),
                  ('筛选状态 / Screening', paper.get('screening_status')), ('同行评审状态 / Peer review', paper.get('peer_review_status'))]
        content = f'<article class="detail"><a class="back-link" href="{base}library/">← 综述库 / Library</a><p class="eyebrow">{e(category["name"])}</p><h1>{e(paper["title"])}</h1><p class="detail-authors">{e(", ".join(paper.get("authors", [])))}</p><div id="detail-actions"></div><div class="paper-links">{anchor(record["paper_url"], "Paper ↗")} {anchor(record["code_url"], "Code ↗")} <span>引用 / Citations: {cite}{stars}</span></div><p class="quiet">统计快照 / Metrics snapshot: {e(metrics["updated_at"][:10])} · N/A = 未匹配或未获取，不等于零 / unavailable, not zero.</p><h2>条目信息 / Record</h2><dl class="fact-list">'
        content += ''.join(f'<div><dt>{e(label)}</dt><dd>{e(value)}</dd></div>' for label, value in fields) + '</dl>'
        content += f'<h2>分类与标签 / Classification</h2><p><a href="{base}library/?category={e(record["category"])}">{e(category["name_zh"])} / {e(category["name"])}</a></p><p>{e(record["topic"])} · {e(record["review_type"])}</p><div class="chips">'
        content += ''.join(f'<a class="chip" href="{base}library/?tag={e(tag)}">{e(dimension)}: {e(tag)}</a>' for dimension, tags in paper.get('tags', {}).items() for tag in tags) + '</div>'
        content += '<p class="quiet">分类及标签源自标题线索；不是全文内容评估。当前数据不含完整摘要。 / Classification and tags use title cues; full abstracts are not included.</p>'
        content += '<h2>版本与来源 / Versions & provenance</h2><ul class="versions">' + ''.join(f'<li>{e(v.get("year"))} · {e(v.get("venue"))} · {anchor(v.get("url"), "Paper ↗")}</li>' for v in paper.get('versions', [])) + '</ul>'
        content += '<div class="provenance">' + ''.join(f'<p>{e(json.dumps(s, ensure_ascii=False))}</p>' for s in paper.get('sources', [])) + '</div>'
        content += f'<p>{anchor(metric.get("citation_source_url"), "OpenAlex source ↗")} · {anchor(metric.get("github_stars_url"), "GitHub stars source ↗")}</p><p class="quiet">Citation fetched: {e(metric.get("citation_fetched_at") or metric.get("citation_checked_at"))}; Stars fetched: {e(metric.get("github_stars_fetched_at"))}</p><details><summary>完整元数据 / Full metadata</summary><pre>{e(json.dumps({"paper": paper, "metrics": metric}, ensure_ascii=False, indent=2))}</pre></details><section id="related"></section></article>'
        route = 'papers/' + pid
        write(route + '/index.html', shell(route, paper['title'], content, paper['title'] + ' — ' + category['name'], pid))
        sitemap.append(site_url + '/' + route + '/')
    write('sitemap.xml', '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">' + ''.join('<url><loc>' + xml_escape(url) + '</loc></url>' for url in sitemap) + '</urlset>')
    write('robots.txt', 'User-agent: *\nAllow: /\nSitemap: ' + site_url + '/sitemap.xml\n')
    # An actual catalog snapshot event, not invented per-paper discovery dates.
    def feed(category=None):
        suffix = ' — ' + category['name'] if category else ''
        count = sum(p['category'] == category['id'] for p in records) if category else len(records)
        link = site_url + '/library/' + ('?category=' + category['id'] if category else '')
        description = f'{count} surveys in the {manifest["as_of"]} catalog snapshot. This is an import event, not a claim that all papers were published today.'
        date = dt.datetime.fromisoformat(manifest['as_of']).strftime('%a, %d %b %Y 00:00:00 GMT')
        return '<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel><title>' + xml_escape('Survey Radar' + suffix) + '</title><link>' + xml_escape(link) + '</link><description>Catalog snapshot updates</description><language>en</language><item><title>' + xml_escape('Catalog snapshot: ' + manifest['as_of'] + suffix) + '</title><link>' + xml_escape(link) + '</link><guid isPermaLink="false">' + xml_escape('snapshot:' + manifest['as_of'] + ':' + (category['id'] if category else 'all')) + '</guid><pubDate>' + date + '</pubDate><description>' + xml_escape(description) + '</description></item></channel></rss>'
    write('feed.xml', feed())
    for category in taxonomy:
        write('feeds/' + category['id'] + '.xml', feed(category))
    write('404.html', shell('404', '页面未找到 / Page not found', '<section class="intro"><h1>404</h1><p>页面不存在 / Page not found.</p><a href="' + base + 'library/">浏览综述库 / Browse the library →</a></section>'))
    print(json.dumps({'output': str(output), 'records': len(records), 'routes': len(sitemap), 'base': base, 'summary': summary}, ensure_ascii=True))
    return summary


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / '.cache/site-build')
    parser.add_argument('--site-url', default=DEFAULT_URL)
    args = parser.parse_args()
    build(args.output, args.site_url)
