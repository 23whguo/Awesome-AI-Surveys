# Survey Radar

Website: https://23whguo.github.io/Awesome-AI-Surveys/

The static website follows Benchmark Radar's visual structure and reuses its AGPL frontend styles and BM25F/CJK search. The adapter and interface are specific to survey metadata. Attribution and corresponding source are in [site/UPSTREAM.md](../site/UPSTREAM.md).

## Local build

Requires Python 3.11+; Node 22+ is used for JavaScript tests. No npm packages, API keys or raw PaperVault files are needed.

```powershell
python -m unittest discover -s tests -v
node --test tests/site.test.mjs
python scripts/build_site.py --output .cache/site-build --site-url http://localhost:8000
python -m http.server 8000 --directory .cache/site-build
```

Open http://localhost:8000/. For Pages, the default build URL includes `/Awesome-AI-Surveys/`; every route, asset and data request honors this base path. All included works get independent HTML details and JSON shards. Sitemap, RSS, category feeds, downloads and 404 pages are generated. Build output is ignored and uploaded as a Pages artifact by `.github/workflows/pages.yml`.

Optional browser QA (requires Playwright and a Chromium browser):

```powershell
pip install playwright
playwright install chromium
python scripts/check_site_browser.py --url http://localhost:8000
```

Use `--browser` to point to an existing Edge/Chrome executable. The check exercises search, facets, sorting, storage persistence, browser history, full-set CSV export, comparison deep links, all navigation routes, detail pages, bilingual switching, mobile overflow, network failure recovery and RSS. Initial validation passed 59 Python tests, 4 JavaScript tests and this browser check against all 4,726 records on 2026-11-10.

## Features and data contract

- Search titles, authors, bilingual categories/subtopics and title-derived tags. Search includes full and partial token matches and prioritizes full matches when sorted by relevance.
- Filter by category, subtopic, year, venue, source, review type, tag and Code availability; sort by citations, time, Stars or relevance. Unknown metrics stay distinct from zero. In time order, year-only entries follow dated entries in the same year.
- URL parameters preserve filters and comparison links. Browser back/forward restores state. Favorites, followed categories and a four-paper comparison list use localStorage; unavailable storage degrades to session state. No account or tracking script is required.
- CSV exports include the entire filtered set, not only visible rows. Paper details include original provenance, versions and metric sources. Comparison uses factual metadata without a quality score.
- Trends count publication metadata in the included catalog. Coverage dates remain unverified when absent. Metric growth is not inferred from a single snapshot. RSS reports catalog snapshot events, not invented daily discoveries. These views do not promise complete platform coverage.
- EN/ZH navigation and interface switching is available. Paper titles and source metadata retain their original language. Static details include bilingual field labels.

## Refresh

Follow the existing collection/review procedure in CONTRIBUTING.md, update the committed catalog/metrics and their actual snapshot dates, run validation and regenerate Markdown with `python scripts/render.py`. The Pages workflow rebuilds on source or data changes. A website rebuild alone does not collect papers, refresh citations or change a snapshot date. Source data edits should remove stale records from the catalog; CI always builds in a fresh output directory.

## Deployment

Enable GitHub Pages with the GitHub Actions build type. Pushes to main trigger tests, data validation, static build and deployment. The existing catalog validation workflow remains independent. The deployed frontend offers its complete modified source under AGPL-3.0; original project/catalog licenses and attribution remain in the repository NOTICE.
