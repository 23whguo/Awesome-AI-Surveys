# Data schema

[Home](../README.md) · [Methodology](METHODOLOGY.md)

data/surveys.jsonl contains one object per included research work. data/surveys.csv provides common browsing fields, with tags serialized as JSON in a CSV cell.

| Field | Meaning |
| --- | --- |
| id | Normalized-title hash; author/year suffix separates same-title works |
| title, authors | Selected source title and supplied author list |
| year, venue | Selected version's year and venue label |
| paper_url | Source paper page; syntactically checked, not independently verified |
| code_url, code_links | Supplied or abstract-extracted resource links; nullable |
| code_link_basis | How resource links were obtained |
| arxiv_ids, dois | Identifiers explicitly present in source URLs |
| versions | Matched source versions, including preserved submission dates |
| primary_category, primary_topic | Exactly one controlled category/topic pair |
| tags | subjects, methods, modalities, tasks, domains and settings |
| review_type | Type named in title, not certified methodology |
| classification_basis | Matched title cues or editorial rationale |
| classification_needs_review | False for included records; unresolved works go to queue |
| screening_status | metadata-screened; does not claim full-text review |
| screening_evidence | Short abstract synthesis excerpt, when available |
| peer_review_status | not-independently-verified |
| literature_coverage_until | Null unless documented; not inferred from year |
| arxiv_categories | Original supplied arXiv categories |
| sources | Dataset name, source line and source venue label |

data/review_queue.jsonl is an unapproved queue of candidate titles, links, reasons and source pointers. It is not an additional included survey list. Source-level duplicate candidates may remain for traceability.

data/manifest.json records the snapshot, checksums, source counts and included category/year statistics. taxonomy.json and tag-vocabulary.json publish controlled vocabularies.
