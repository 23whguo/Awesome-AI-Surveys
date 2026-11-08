"""Generate GitHub-native tables, category pages and multidimensional tag views."""
from __future__ import annotations
import collections
import csv
import datetime as dt
import html
import json
from pathlib import Path
import re
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[1]
PAGE_SIZE = 200
SORT_MODE = 'citations'
METRICS = {}
METRICS_UPDATED = None


def is_sortable(path):
    relative = path.relative_to(ROOT)
    return (relative.parent == Path('.') and relative.name in {'README.md', 'README.zh-CN.md'} or
            relative.parent == Path('docs') and relative.name in {'CATEGORIES.md', 'TAGS.md', 'YEARS.md'} or
            relative.parent.as_posix() in {'docs/categories', 'docs/papers', 'docs/tags', 'docs/years'})


def variant(path, mode):
    return path.with_stem(path.stem + '.by-time') if mode == 'time' else path


def read_jsonl(path):
    with path.open(encoding='utf-8') as f:
        return [json.loads(line) for line in f if line.strip()]


def save(path, text):
    if is_sortable(path):
        if SORT_MODE == 'time':
            def rewrite(match):
                target = match.group(1)
                if target.startswith(('https://', 'http://', '<https://', '<http://', '#', 'mailto:')):
                    return match.group(0)
                name, sep, fragment = target.partition('#')
                destination = (path.parent/name).resolve()
                if destination.suffix == '.md' and destination.is_relative_to(ROOT) and is_sortable(destination):
                    name = str(Path(name).with_stem(Path(name).stem + '.by-time')).replace('\\', '/')
                return '](' + name + (sep + fragment if sep else '') + ')'
            text = re.sub(r'\]\(([^()\n]+)\)', rewrite, text)
        citation_page = path.name
        time_page = variant(path, 'time').name
        selector = ('**排序 / Sort：** ' +
                    ('**按引用 ↓**' if SORT_MODE == 'citations' else '[按引用 ↓](' + citation_page + ')') +
                    ' · ' +
                    ('**按时间 ↓**' if SORT_MODE == 'time' else '[按时间 ↓](' + time_page + ')'))
        notes = ('引用：OpenAlex；括号内 ⭐：Code 链接对应 GitHub 仓库的 Stars。N/A 表示未匹配或获取失败，不等于 0。'
                 '统计快照：' + (METRICS_UPDATED[:10] if METRICS_UPDATED else '尚未获取') + '。')
        position = text.find('</h1>') + len('</h1>') if '</h1>' in text else text.find('\n')
        text = text[:position] + '\n\n' + selector + '\n\n' + notes + '\n' + text[position:]
        path = variant(path, SORT_MODE)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.rstrip() + '\n', encoding='utf-8', newline='\n')


def cell(text):
    return html.escape(re.sub(r'\s+', ' ', str(text or '')).strip(), quote=False).replace('|', '&#124;').replace('[', '&#91;').replace(']', '&#93;')


def link(label, url):
    if not url:
        return 'N/A'
    return '[' + label + '](<' + url.replace('>', '%3E').replace('<', '%3C') + '>)'


def ordered(papers, mode=None):
    mode = mode or SORT_MODE
    def key(p):
        count = p.get('_metrics', {}).get('citation_count')
        citations = (count is None, -(count or 0))
        date = source_date(p)
        chronology = (-(p['year'] or 0), date is None, -date.toordinal() if date else 0)
        return (chronology + citations if mode == 'time' else citations + chronology) + (p['title'].casefold(), p['id'])
    return sorted(papers, key=key)


def source_date(paper):
    """Use supplied submission dates within the displayed year, without inventing dates."""
    dates = []
    for version in paper.get('versions', []):
        value = version.get('source_first_submitted_at')
        if not value:
            continue
        try:
            date = dt.date.fromisoformat(value[:10])
        except (ValueError, TypeError):
            continue
        if date.year == paper.get('year') and version.get('year') == paper.get('year'):
            dates.append(date)
    return min(dates) if dates else None


def citation_cell(p):
    metrics = p.get('_metrics', {})
    count = metrics.get('citation_count')
    result = link(format(count, ','), metrics.get('citation_source_url')) if count is not None else 'N/A'
    if metrics.get('github_repository'):
        stars = metrics.get('github_stars')
        label = '⭐ ' + (format(stars, ',') if stars is not None else 'N/A')
        result += ' (' + link(label, metrics.get('github_stars_url')) + ')'
    return result


def table(papers):
    lines = ['| 📅 Year | 📝 Title | 🏛️ Venue | 📄 Paper | 💻 Code | 引用 |',
             '| ---: | --- | --- | :---: | :---: | ---: |']
    for p in ordered(papers):
        lines.append('| ' + ' | '.join([str(p['year'] or 'N/A'), cell(p['title']), cell(p['venue']),
                                          link('paper', p['paper_url']), link('code', p['code_url']), citation_cell(p)]) + ' |')
    return '\n'.join(lines)


def paginate(path, title, papers, intro=''):
    pages = [ordered(papers)[i:i+PAGE_SIZE] for i in range(0, len(papers), PAGE_SIZE)] or [[]]
    for i, rows in enumerate(pages):
        target = path if i == 0 else path.with_stem(path.stem + '-' + str(i+1))
        nav = []
        for j in range(len(pages)):
            filename = path.name if j == 0 else path.stem + '-' + str(j+1) + '.md'
            nav.append(str(j+1) if i == j else '[' + str(j+1) + '](' + filename + ')')
        text = '# ' + title + '\n\n[Home](../../README.md) · [分类目录](../CATEGORIES.md) · [Tags](../TAGS.md)\n\n'
        text += intro + '\n\n**' + str(len(papers)) + ' surveys · Page ' + str(i+1) + '/' + str(len(pages)) + '**\n\n'
        if len(pages) > 1: text += 'Pages: ' + ' · '.join(nav) + '\n\n'
        text += table(rows) + '\n\n'
        if len(pages) > 1: text += 'Pages: ' + ' · '.join(nav)
        save(target, text)


def render():
    papers = read_jsonl(ROOT/'data/surveys.jsonl')
    for paper in papers:
        paper['_metrics'] = METRICS.get(paper['id'], {})
    if SORT_MODE == 'citations':
        fields = ['id', 'year', 'title', 'venue', 'paper_url', 'code_url', 'citation_count',
                  'citation_source', 'citation_source_url', 'citation_fetched_at',
                  'github_stars', 'github_stars_url', 'github_stars_fetched_at']
        with (ROOT/'data/surveys-with-metrics.csv').open('w', encoding='utf-8', newline='') as f:
            out = csv.DictWriter(f, fieldnames=fields, lineterminator='\n')
            out.writeheader()
            for paper in ordered(papers):
                values = {**paper, **paper['_metrics']}
                out.writerow({field: values.get(field) for field in fields})
    manifest = json.loads((ROOT/'data/manifest.json').read_text(encoding='utf-8'))
    expansion_path = ROOT/'data/expansion-2026.json'
    expansion = json.loads(expansion_path.read_text(encoding='utf-8')) if expansion_path.exists() else None
    harvest_path = ROOT/'data/harvest-2026.json'
    harvest = json.loads(harvest_path.read_text(encoding='utf-8')) if harvest_path.exists() else {}
    zero_tech_months = [p['from'][:7] for p in harvest.get('sources',{}).get('techrxiv',{}).get('partitions',[])
                        if p.get('expected_records') == 0]
    taxonomy = json.loads((ROOT/'data/taxonomy.json').read_text(encoding='utf-8'))
    by_category = collections.defaultdict(list)
    for p in papers: by_category[p['primary_category']].append(p)
    category_index = ['# Categories · 主分类', '', '[Home](../README.md) · [中文](../README.zh-CN.md) · [Tags](TAGS.md)', '',
                      'One primary category per work. Cross-cutting access is provided by tag views. 每篇论文只有一个主分类，多标签提供交叉入口。', '',
                      '| Category | 中文分类 | Surveys |', '| --- | --- | ---: |']
    for cat in taxonomy:
        cid = cat['id']; rows = by_category[cid]
        category_index.append('| [' + cat['name'] + '](categories/' + cid + '.md) | ' + cat['name_zh'] + ' | ' + str(len(rows)) + ' |')
        parts = ['# ' + cat['name'], '', cat['name_zh'], '',
                 '[Home](../../README.md) · [All categories](../CATEGORIES.md) · [Tags](../TAGS.md)', '',
                 '**' + str(len(rows)) + ' surveys.** Topic previews below; each full list contains every included work and is paginated for GitHub rendering.', '']
        for idx, topic in enumerate(cat['topics'], 1):
            topic_rows = [p for p in rows if p['primary_topic'] == topic['id']]
            slug = cid + '-' + topic['id']
            paginate(ROOT/'docs/papers'/ (slug+'.md'), topic['name'] + ' · ' + topic['name_zh'], topic_rows,
                     '[' + cat['name'] + '](../categories/' + cid + '.md)')
            parts += ['<details open>', '<summary><b>' + cid[:2] + '.' + str(idx) + ' ' + topic['name'] + ' · ' + topic['name_zh'] + ' (' + str(len(topic_rows)) + ')</b></summary>', '',
                      '[Browse all ' + str(len(topic_rows)) + ' surveys →](../papers/' + slug + '.md)', '']
            if topic_rows: parts += [table(ordered(topic_rows)[:6]), '']
            else: parts += ['No classified records in this snapshot. 当前快照暂无已归类记录。', '']
            parts += ['</details>', '']
        save(ROOT/'docs/categories'/ (cid+'.md'), '\n'.join(parts))
    save(ROOT/'docs/CATEGORIES.md', '\n'.join(category_index))
    # Tag pages refer to the same canonical works; they never inflate headline totals.
    tag_groups = collections.defaultdict(lambda: collections.defaultdict(list))
    for p in papers:
        for dimension, tags in p['tags'].items():
            for tag in tags: tag_groups[dimension][tag].append(p)
        tag_groups['review_type'][p['review_type']].append(p)
    tag_index = ['# Tags · 多维标签', '', '[Home](../README.md) · [Categories](CATEGORIES.md)', '',
                 'Tags use explicit title evidence. Missing tags do not establish absence; no incidental abstract mentions are promoted to tags.', '',
                 '标签依据标题中的明确表述生成，缺少标签不代表论文未涉及该主题。交叉专题中的重复展示不计入论文总数。', '']
    for dimension, tags in tag_groups.items():
        tag_index += ['## ' + dimension, '', '| Tag | Surveys |', '| --- | ---: |']
        for tag, rows in sorted(tags.items()):
            slug = dimension+'-'+tag
            tag_index.append('| ['+tag+'](tags/'+slug+'.md) | '+str(len(rows))+' |')
            paginate(ROOT/'docs/tags'/(slug+'.md'), dimension + ': ' + tag, rows)
        tag_index.append('')
    save(ROOT/'docs/TAGS.md', '\n'.join(tag_index))
    # Year views retain the selected source year; version-specific dates remain in JSONL.
    year_index = ['# By year · 按年份', '', '[Home](../README.md) · [Categories](CATEGORIES.md)', '', '| Year | Surveys |', '| ---: | ---: |']
    for year in sorted({p['year'] for p in papers}, reverse=True):
        rows = [p for p in papers if p['year'] == year]
        year_index.append('| ['+str(year)+'](years/'+str(year)+'.md) | '+str(len(rows))+' |')
        paginate(ROOT/'docs/years'/(str(year)+'.md'), str(year), rows)
    save(ROOT/'docs/YEARS.md', '\n'.join(year_index))
    for zh in (False, True):
        title = 'Awesome AI Surveys' if not zh else 'Awesome AI Surveys · AI 综述集合'
        lines = ['<h1 align="center">'+title+'</h1>', '', '<p align="center"><strong>' +
                 ('A navigable collection of AI surveys, reviews and research overviews' if not zh else '按研究问题分类、支持多标签查找的 AI 综述与文献回顾集合') + '</strong></p>', '',
                 '<p align="center"><a href="https://awesome.re"><img src="https://awesome.re/badge.svg" alt="Awesome"></a> <img src="https://img.shields.io/badge/surveys-'+str(len(papers))+'-2563eb" alt="Survey count"> <img src="https://img.shields.io/badge/categories-17-0f766e" alt="17 categories"> <a href="LICENSE"><img src="https://img.shields.io/badge/license-GPL--3.0-blue" alt="GPL-3.0"></a></p>', '',
                 '[English](README.md) · [简体中文](README.zh-CN.md)', '']
        if zh:
            lines += ['**'+format(len(papers), ',')+' 篇综述 · 17 个主分类 · '+format(manifest['with_code_links'], ',')+' 篇含源数据或摘要提供的仓库链接。**', '',
                      '基于 PaperVault 会议期刊记录与本地 2024—2026 年 arXiv 快照构建。截至 '+manifest['as_of']+'，扫描 '+format(manifest['source_records'], ',')+' 条源记录。每篇作品只设一个主分类，多标签提供跨主题浏览。', '',
                      '条目通过元数据规则筛选，尚未逐篇进行全文及链接核验。发表渠道和年份沿用源记录；arXiv 记录不据此推断已通过同行评审。暂无法确认类型或主分类的记录保留在 [待复核队列](data/review_queue.jsonl)。', '',
                      '**浏览完整集合：** [分类目录](docs/CATEGORIES.md) · [多维标签](docs/TAGS.md) · [按年份](docs/YEARS.md) · [JSONL](data/surveys.jsonl) · [CSV](data/surveys.csv)', '',
                      '下面每个分类按当前所选排序展示 6 篇条目；点击完整列表可查看该分类全部综述及二级主题。表格列为 Year / Title / Venue / Paper / Code / 引用。每个页面顶部均可切换引用数或时间排序；时间采用展示年份内的源提交日期，缺少日期时排在该年已知日期之后。未获取到的引用数排在引用榜末尾。', '']
        else:
            lines += ['**'+format(len(papers), ',')+' surveys · 17 primary categories · '+format(manifest['with_code_links'], ',')+' with repository links supplied by source metadata or abstracts.**', '',
                      'Built from PaperVault venue records and local 2024–2026 arXiv snapshots. '+format(manifest['source_records'], ',')+' source records scanned; snapshot date: **'+manifest['as_of']+'**. Each work has one primary category and multiple orthogonal tags.', '',
                      'Entries are screened from metadata, not independently audited full-text reviews. Venue labels and years follow the source records; arXiv entries do not imply peer review. Ambiguous article types and unresolved subjects remain in the [review queue](data/review_queue.jsonl).', '',
                      '**Browse every included work:** [Categories](docs/CATEGORIES.md) · [Tags](docs/TAGS.md) · [Years](docs/YEARS.md) · [JSONL](data/surveys.jsonl) · [CSV](data/surveys.csv)', '',
                      'Each category previews six papers in the selected order. Switch between citations (high to low) and time (newest source date first) at the top of any page. Time uses supplied submission dates within the displayed year; year-only records follow dated records in that year. Unknown counts sort last in citation views. Tables use Year / Title / Venue / Paper / Code / 引用; parenthesized stars refer to the linked GitHub repository.', '']
        cited = sum(m.get('citation_count') is not None for m in METRICS.values())
        starred = sum(m.get('github_stars') is not None for m in METRICS.values())
        lines += [('**统计覆盖：** ' + format(cited, ',') + ' / ' + format(len(papers), ',') + ' 篇取得引用数；' +
                   str(starred) + ' 篇取得 GitHub Stars。[下载含统计的 CSV](data/surveys-with-metrics.csv)。' if zh else
                   '**Metric coverage:** citation counts for ' + format(cited, ',') + ' / ' + format(len(papers), ',') +
                   ' papers; GitHub Stars for ' + str(starred) + ' papers. [CSV with metrics](data/surveys-with-metrics.csv).'), '']
        if expansion:
            lines += [('**2026 年补漏：** 本轮新增 ' + str(expansion['net_added']) + ' 篇；接入 TechRxiv、Preprints.org 和 HF Daily Papers。'
                       '[调查与覆盖报告](docs/EXPANSION_2026.md) · [完整发现索引](data/discovery-index/manifest.json) · [' +
                       str(expansion['pending_unique_candidates']) + ' 组待复核候选](docs/EXTERNAL_PENDING_2026.md)。公开接口遍历完成不构成平台全量保证。' if zh else
                       '**2026 expansion:** ' + str(expansion['net_added']) + ' added surveys from TechRxiv, Preprints.org and HF Daily Papers. '
                       '[Coverage report](docs/EXPANSION_2026.md) · [Full discovery index](data/discovery-index/manifest.json) · [' +
                       str(expansion['pending_unique_candidates']) + ' pending candidate groups](docs/EXTERNAL_PENDING_2026.md). API enumeration does not establish exhaustive platform coverage.'), '']
            if zero_tech_months:
                lines += [('**覆盖提示：** TechRxiv 登记查询在 '+ '、'.join(zero_tech_months) +
                           ' 返回零条，不能据此认定这些月份没有论文。HF Daily Papers 是 arXiv 精选索引。' if zh else
                           '**Coverage warning:** TechRxiv registry queries returned zero records for '+', '.join(zero_tech_months)+
                           '; this does not establish that no papers were published. HF Daily Papers is a selected arXiv index.'), '']
        lines += ['## '+('分类导航' if zh else 'Contents'), '']
        for cat in taxonomy:
            label = cat['name_zh'] if zh else cat['name']
            lines.append('- ['+cat['id'][:2]+'. '+label+'](#'+cat['id']+') ('+str(len(by_category[cat['id']]))+')')
        lines += ['', '## '+('综述目录' if zh else 'Survey collection'), '']
        for cat in taxonomy:
            cid = cat['id']; rows = by_category[cid]
            label = cat['name_zh'] if zh else cat['name']
            lines += ['<a id="'+cid+'"></a>', '', '<details open>', '<summary><b>'+cid[:2]+'. '+label+' ('+str(len(rows))+')</b></summary>', '',
                      '['+('查看完整分类与二级主题' if zh else 'Browse the complete category and subtopics')+' →](docs/categories/'+cid+'.md)', '']
            lines += [table(ordered(rows)[:6]) if rows else 'No records in this snapshot.', '', '</details>', '']
        lines += ['## '+('数据来源与方法' if zh else 'Sources & methodology'), '',
                  '- [PaperVault](https://github.com/youngfish42/PaperVault) / [Hugging Face dataset](https://huggingface.co/datasets/youngfish42/PaperVault): conference and journal metadata.',
                  '- Local arXiv 2024 / 2025 / 2026 CSV-derived snapshots: identifiers, titles, abstracts and category metadata used for screening; original raw files are not uploaded.',
                  '- 2026 external metadata: TechRxiv / Preprints.org via Crossref with a DataCite check; Hugging Face Daily Papers via its official date/month API. [Coverage, limitations and audit files](docs/EXPANSION_2026.md).',
                  '- [Methodology, limitations and arXiv policy](docs/METHODOLOGY.md) · [Source manifest and checksums](data/manifest.json) · [Data schema](docs/DATA_SCHEMA.md).', '',
                  '## '+('维护与贡献' if zh else 'Maintenance & contributions'), '',
                  'See [CONTRIBUTING.md](CONTRIBUTING.md) for additions, corrections, screening overrides and offline rebuild commands. Generated views share one canonical JSONL catalog; edit source data or editorial overrides, then regenerate.', '',
                  '## '+('致谢与许可' if zh else 'Acknowledgements & license'), '',
                  'Table and collapsible-section layout inspired by [Awesome Self-Improving Agents](https://github.com/selfimproving-agent/Awesome-Self-Improving-Agents). Broad survey-index inspiration: [Awesome AI Survey Papers](https://github.com/kaikatsumata/awesome-ai-survey-papers). Their paper lists and illustrations are not copied.', '',
                  'Project code and derived catalog: [GPL-3.0](LICENSE), preserving attribution to the GPL-3.0 PaperVault source. Papers and linked repositories retain their respective authors’ and publishers’ rights. A repository link is a resource pointer, not an independently verified author-code endorsement.']
        save(ROOT/('README.zh-CN.md' if zh else 'README.md'), '\n'.join(lines))
    report = ['# Screening report · 筛选报告', '', 'Snapshot: '+manifest['as_of'], '',
              '| Metric | Count |', '| --- | ---: |']
    for key in ['source_records','screened_in_source_records','merged_duplicate_records','unresolved_classification_works','unique_surveys','cross_source_works','review_queue_records','with_code_links']:
        report.append('| '+key+' | '+str(manifest[key])+' |')
    report += ['', '## Sources', '', '| Source | Records | Review candidates | Included source records | Pending type review | Excluded |', '| --- | ---: | ---: | ---: | ---: | ---: |']
    for s in manifest['sources']:
        c=s['counts']; report.append('| '+s['id']+' | '+' | '.join(str(c.get(k,0)) for k in ['records','title_candidates','include','review','exclude'])+' |')
    report += ['', 'Counts of source records and counts of unique works differ. Cross-source duplicates are collapsed only when normalized titles, author evidence and compatible years agree. Pending rows are not counted as included surveys.', '',
               'ArXiv source dates occasionally disagree with identifier months. Both source facts are preserved; the dataset is not represented as an independently verified chronology. See the manifest for per-source mismatch counts.']
    save(ROOT/'docs/SCREENING_REPORT.md', '\n'.join(report))
    print('Rendered', len(papers), 'surveys;', sum(1 for _ in (ROOT/'docs').rglob('*.md')), 'Markdown views')


if __name__ == '__main__':
    snapshot = ROOT/'data/metrics.json'
    if snapshot.exists():
        data = json.loads(snapshot.read_text(encoding='utf-8'))
        METRICS = data['paper_metrics']
        METRICS_UPDATED = data['updated_at']
    for mode in ('citations', 'time'):
        SORT_MODE = mode
        render()
