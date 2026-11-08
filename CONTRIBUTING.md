# Contributing

Corrections, missing reviews and classification improvements are welcome. 请提供可核验的论文链接、分类依据以及配套仓库来源。

## Inclusion

- Include AI literature surveys, reviews, systematic/scoping reviews and genuine research overviews.
- Keep original method papers, empirical questionnaires, product/peer/code review tasks, event summaries and talk records out of the survey catalog.
- Do not invent DOI, venue, publication date, code repository, literature cutoff or peer-review outcome.
- Keep one canonical work record while preserving source/version provenance.

## Correct the snapshot

Update data/surveys.jsonl or add a candidate to data/review_queue.jsonl with supporting sources. When input snapshots are available, prefer an editorial override in data/overrides.json keyed by normalized_title(title) from scripts/catalog.py. Every override requires a reason.

~~~json
{
  "primary_category": "16-systems",
  "primary_topic": "compression",
  "reason": "The review compares model quantization and deployment costs."
}
~~~

Use decision: include, review or exclude to correct screening on source rebuild. An include override still requires a usable paper URL and resolved category. Do not put factual publication claims in a classification override.

Rules and taxonomy live in scripts/catalog.py and scripts/taxonomy.py. Add a meaningful regression case when changing screening, identity or classification.

## Generate and validate

~~~bash
python scripts/render.py
python -m unittest discover -s tests -v
python scripts/validate.py
~~~

Rebuild from the four local source snapshots:

~~~bash
python scripts/catalog.py --data-root /path/to/PaperVaultData --as-of 2026-11-08
python scripts/render.py
~~~

Use the actual snapshot date for a new release. Original sources are read-only inputs. Do not commit tokens, local databases, source caches or PDF corpora.

README files and category, paper, tag and year views are generated. Preserve Year / Title / Venue / Paper / Code tables. Previews link to complete paginated lists to keep GitHub rendering reliable.
