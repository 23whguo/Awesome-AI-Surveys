import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('build_site', ROOT / 'scripts/build_site.py')
site = importlib.util.module_from_spec(spec)
spec.loader.exec_module(site)


class SiteTests(unittest.TestCase):
    def test_safe_links(self):
        for value in ('javascript:alert(1)', '//evil.example', 'https://user@evil.example', None):
            self.assertIsNone(site.safe_url(value))
        self.assertEqual(site.safe_url('https://arxiv.org/abs/1'), 'https://arxiv.org/abs/1')

    def test_dates_do_not_invent_precision(self):
        p = {'year': 2025, 'versions': [{'year': 2024, 'source_first_submitted_at': '2024-12-20'}]}
        self.assertIsNone(site.source_date(p))
        p['versions'] += [{'year': 2025, 'source_first_submitted_at': '2025-02-01T00:00:00Z'}]
        self.assertEqual(site.source_date(p), '2025-02-01')

    def test_build_all_records_and_subpath(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            summary = site.build(out, 'https://example.org/custom/prefix')
            payload = json.loads((out / 'data/catalog.json').read_text(encoding='utf-8'))
            original = [json.loads(line) for line in (ROOT/'data/surveys.jsonl').read_text(encoding='utf-8').splitlines()]
            self.assertEqual({p['id'] for p in original}, {p['id'] for p in payload['records']})
            self.assertEqual(len(list((out/'papers').glob('*/index.html'))), len(original))
            self.assertEqual(summary['coverage_available'], sum(bool(p.get('literature_coverage_until')) for p in original))
            for route in ('index.html', 'library/index.html', 'papers/'+original[0]['id']+'/index.html'):
                html = (out/route).read_text(encoding='utf-8')
                self.assertIn('href="/custom/prefix/assets/survey.css"', html)
                self.assertIn('src="/custom/prefix/assets/app.js"', html)
                self.assertNotIn('href="/assets/', html)
            ET.parse(out/'sitemap.xml')
            ET.parse(out/'feed.xml')
            self.assertEqual(len(list((out/'feeds').glob('*.xml'))), len(payload['taxonomy']))

    def test_compact_metrics_keep_null_and_zero(self):
        p = {'id': 'survey-a', 'title': '<script>', 'primary_category': 'cat'}
        self.assertIsNone(site.compact(p, {})['citations'])
        self.assertEqual(site.compact(p, {'citation_count': 0})['citations'], 0)


if __name__ == '__main__':
    unittest.main()
