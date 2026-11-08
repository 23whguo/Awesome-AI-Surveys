# 2026 source expansion · 2026 年补漏调查与覆盖报告

[Home](../README.md) · [中文](../README.zh-CN.md) · [Pending candidates](EXTERNAL_PENDING_2026.md)

**Cutoff / 截止日期：2026-11-08。2026 年尚未结束，本报告不包含截止日之后的新论文。**

本次目标是穷尽指定公开 API 在时间窗口内返回的记录和分页，**不承诺所有平台、所有 AI 综述一篇不漏**。API 完整分页、论文类型识别和平台真实全量是不同的覆盖层次。

## Catalog changes · 目录变化

| Metric | Count |
| --- | ---: |
| Baseline included surveys | 3918 |
| Current included surveys | 4726 |
| Newly included identities | 808 |
| Newly included identities with displayed year 2026 | 808 |
| Added identities supported by the three new sources | 808 |
| Existing identities enriched with new-source provenance | 34 |
| Removed baseline identities | 0 |
| Pending source records | 715 |
| Pending unique candidate groups | 695 |

Source contributions overlap and must not be added together. New versions and matching cross-posts enrich one canonical work rather than inflate the total. Some HF selections and updated preprints originate in earlier years; selection/version date is not first-ever publication date.

## Acquisition coverage · 抓取覆盖

| Source | Records returned | API scope fully enumerated | Catalog works with this provenance |
| --- | ---: | --- | ---: |
| TechRxiv | 1520 | Yes | 171 |
| Preprints.org | 26848 | Yes | 629 |
| HF Daily Papers | 8341 | Yes | 50 |

- **TechRxiv / Preprints.org:** enumerate every Crossref record for DOI prefixes 10.36227 / 10.20944 in monthly posted-date windows; independently enumerate the publication-date DOI set, compare identities, and fetch any additional records. DataCite prefix/year queries provide an additional registration-agency check.
- **HF Daily Papers:** enumerate every calendar date from 2026-01-01 through the cutoff, including empty days, and continue pagination beyond the first 100 entries. Independently enumerate each month and compare paper-ID sets.
- **Discovery:** inspect title markers, explicit abstract synthesis statements, bibliometric/scientometric mapping and systematic mapping. Strong AI relevance is required; biological neural mechanisms and incidental use of AI do not establish an AI-review focus.
- **Review and identity:** retain ambiguous entries in the linked queue; use identifier, compatible title and author evidence to merge versions. A shared title or a high-level keyword alone is insufficient.

## Coverage limits and observed gaps · 已知限制

Website/sitemap checks: techrxiv HTTP 403, preprints HTTP 403. The websites were not bypassed or independently fully crawled. A DOI-registry harvest therefore cannot certify complete platform coverage; unregistered, delayed, removed or incorrectly dated records remain possible gaps.

TechRxiv registry queries returned zero records in 2026-04, 2026-05, 2026-06, 2026-07, 2026-08, 2026-09, 2026-10, 2026-11. This is a **coverage warning**, not evidence that no surveys were published in those months. The machine-readable report preserves each zero-count query.

HF Daily Papers indexes selected arXiv papers. It is useful for recovering omissions in a local arXiv snapshot, but is not an independent preprint publication host or a comprehensive index of all arXiv papers. Its 2026 feed can select papers originally published in earlier years.

Screening remains metadata-based. Ambiguous AI relevance, review protocols, hybrid method papers, withdrawn records and missing metadata require further review. The pending queue is intentionally visible and is not counted as confirmed surveys.

## Audit files · 可追查记录

- [Every API partition, count and crosscheck](../data/harvest-2026.json)
- [Every external review candidate and screening decision](../data/external-review-audit.jsonl)
- [Full discovered-record index, including records not recognized as reviews](../data/discovery-index/manifest.json)
- [Baseline, added identities and contribution counts](../data/expansion-2026.json)
- [Browsable pending candidates](EXTERNAL_PENDING_2026.md)

## Primary references · 官方依据

- [Crossref REST API documentation](https://github.com/CrossRef/rest-api-doc): date filters, cursor pagination and DOI-prefix routes.
- [DataCite public REST API](https://support.datacite.org/docs/api): independent registration-agency check.
- [Hugging Face official OpenAPI schema](https://huggingface.co/.well-known/openapi.json): /api/daily_papers date/month parameters, p pagination and limit up to 100.
- [Hugging Face Paper Pages documentation](https://huggingface.co/docs/hub/paper-pages): paper pages currently use arXiv identifiers.

## Reproduce · 复现

The harvester uses Python standard-library APIs, resumable local response caches, bounded concurrency and retry/backoff. Raw response/abstract caches stay untracked. Run:

~~~powershell
python scripts/harvest.py --as-of 2026-11-08
python scripts/catalog.py --data-root /path/to/PaperVaultData --as-of 2026-11-08 --input techrxiv-2026=.cache/external-2026/inputs/techrxiv-2026.jsonl.gz --input preprints-2026=.cache/external-2026/inputs/preprints-2026.jsonl.gz --input huggingface-daily-2026=.cache/external-2026/inputs/huggingface-2026.jsonl.gz
python scripts/report_expansion.py --build-index
python scripts/metrics.py --new-only --skip-title-search
python scripts/render.py
python -m unittest discover -s tests -v
python scripts/validate.py
~~~

Replace the local dataset path as needed. Use harvest.py --refresh for a fresh sweep, including delayed registrations and changed historic feed entries; a cached rebuild reproduces the saved responses rather than certifying the current live platform state. The saved baseline IDs allow the report to regenerate without the initial private working file. Citation lookups may be quota-limited; an unavailable count stays N/A and never removes the paper from the catalog.
