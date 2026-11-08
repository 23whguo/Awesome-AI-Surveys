# Methodology · 数据来源与整理方法

[Home](../README.md) · [中文](../README.zh-CN.md) · [Screening report](SCREENING_REPORT.md)

This is an offline, metadata-screened starting collection with one primary category per research work and title-evidenced multidimensional tags. It does not claim exhaustive AI coverage or full manual verification.

本集合使用本地已有数据建立第一版，筛选、合并与分类可重复运行；未逐篇核验全文、作者身份、正式发表状态或资源链接。类型或主题不明确的记录进入待复核队列，不计入目录总数。

## Input snapshots

1. PaperVault official metadata, distributed at [youngfish42/PaperVault](https://huggingface.co/datasets/youngfish42/PaperVault), contains venue records from many years. All available historical years are eligible.
2. Local arXiv snapshots contain identifier-year groups for 2024, 2025 and 2026. These CSV-derived snapshots were previously converted into PaperVault-format JSON Lines. Their acquisition provenance beyond the supplied conversion reports has not been independently established.
3. Only the four source files are read: the official file and three arXiv files. The combined cache is not read again. Original input files and the source project remain unchanged.

See [manifest.json](../data/manifest.json) for source sizes, SHA-256 hashes, counts and year distributions. Machine paths, credentials, raw archives and full abstract corpora are not published.

## Discovery and type screening

Titles containing survey, review, overview, taxonomy, tutorial, perspective, meta-analysis or state-of-the-art are candidates. AI relevance is checked using explicit title terms, AI venues, or AI-primary arXiv categories together with abstract evidence. This favors precision and can miss reviews without discovery markers.

Explicit review titles are distinguished from empirical questionnaires, product reviews, code-review tasks, peer-review systems, astronomical surveys, mission overviews, challenge reports and talk records. Overview and taxonomy entries require abstract evidence of literature synthesis. Tutorials and ambiguous hybrids require editorial review. Named review types reflect title wording, not independent certification of review methodology.

Rules do not substitute for reading the paper. Broad titles, misleading descriptions and unusual terminology can still be mishandled. Corrections use auditable editorial overrides and regression cases.

## Identity and versions

- Candidate duplicates require matching normalized titles, compatible source years (at most three years apart), and overlapping normalized author names. A limited same-year fallback applies when both author lists are absent.
- Matching URLs or arXiv identifiers provide lookup evidence but never override conflicting titles/authors.
- Same-title works with different authors remain separate. Title changes can leave duplicates; fuzzy matching does not silently merge papers.
- A venue record is preferred for display when matched to an arXiv record. Every matched source and version remains in JSONL.
- Display year belongs to the selected version. arXiv-only years follow identifier years; raw submission dates remain per version. Some supplied dates disagree with identifier months; these are counted rather than corrected.
- Future identifier months and explicit source dates after the snapshot date are excluded. Missing dates, DOI, literature cutoffs and peer-review outcomes are not invented.

## Classification and tags

The [17-category taxonomy](CATEGORIES.md) follows research questions: learning, data, architectures, language, vision, audio, multimodality, knowledge, retrieval, temporal modeling, decisions, agents, embodiment, trustworthiness, efficiency, applications and general AI overviews.

Classification uses transparent title-pattern rules. Abstracts support review-type screening; unresolved subject assignments are held in the review queue. Specific constraints and application terms generally take precedence over broad model names. This is an initial metadata classification; community review can refine boundaries.

Tags occupy separate fields: subjects, methods, modalities, tasks, domains and settings. Explicit title cues generate published tags, reducing incidental abstract tagging. A work can appear in multiple tag views but is counted once.

## Paper, venue and code links

Paper URLs are preserved from the input after basic normalization. Venue labels are not independent proof of acceptance. All records retain peer_review_status: not-independently-verified.

The Code column displays a supplied repository/resource URL or a GitHub URL extracted from an abstract. It can refer to a companion bibliography, toolkit or implementation; it does not guarantee official author code or a live link. N/A means no usable source link was found. Links are not guessed from titles.

## arXiv CS review moderation

The [official announcement of 2025-10-31](https://blog.arxiv.org/2025/10/31/attention-authors-updated-practice-for-review-articles-and-position-papers-in-arxiv-cs-category/) requires CS review/survey and position papers to be accepted at a peer-reviewed venue and accompanied by documentation for consideration. It is not an arXiv-wide ban beginning in 2026. These snapshots cannot establish completeness of recent reviews.

TechRxiv, Preprints.org, Zenodo, institutional repositories and publishers are possible future inputs. They are not represented as harvested sources in this release.

## Citations, stars and display order

The 引用 column follows Code and displays the OpenAlex citation count, followed by the displayed Code repository's GitHub Stars in parentheses when a GitHub repository can be identified. Each successful statistic links to its source. Missing/unmatched statistics remain N/A; a recorded zero remains 0.

Citation lookup first batches source DOIs and arXiv DOI identifiers through the OpenAlex works API. A compatible title is required even when an identifier matches. Fallback title matching requires exact normalized titles, author evidence and compatible publication years. Where multiple compatible indexed editions are returned, the strongest identity match and then highest count are selected; counts are never summed because cited-by sets can overlap. Citation metrics come exclusively from OpenAlex.

GitHub Stars are retrieved from the official repository API, using owner/repository parsed from the displayed Code URL. Subdirectory links refer to the containing repository; inaccessible repositories remain N/A. Repository ownership is not newly inferred from paper titles.

GitHub Markdown does not execute sorting scripts, so every browsing page links between two generated views: citations descending (the default) and time descending. Chronology uses the displayed source year and, when available, the earliest supplied submission date among matched versions in that year. Records without a date follow dated records within their year; dates from other years are not substituted. Citation ties use chronology, title and ID; time ties use citations, title and ID. Unknown citation counts come last in citation views. Both views contain exactly the same catalog.

Metrics have source URLs and per-response timestamps in data/metrics.json. Cached queries permit interrupted refreshes to resume. Run python scripts/metrics.py --refresh to update cached statistics before generating views. Network calls are not part of ordinary rendering or CI.

## Reproduction

Python 3.10+ and its standard library are sufficient. No model API or network access is needed for generation.

~~~powershell
python scripts/catalog.py --data-root D:/PaperVaultData --as-of 2026-11-08
python scripts/render.py
python -m unittest discover -s tests -v
python scripts/validate.py
~~~

Additional inputs use --input source-name=path/to/papers.jsonl.gz and the same PaperVault core fields. Original snapshots are not required to regenerate Markdown from the published catalog.

## Licensing and attribution

PaperVault code and its dataset card declare GPL-3.0. This project uses GPL-3.0 for its own code and derived collection, with source attribution retained in [NOTICE](../NOTICE). Papers and repositories retain their respective rights. No PDF corpus or copied reference-project artwork is distributed.
