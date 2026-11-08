import sys
from pathlib import Path
import unittest
from unittest.mock import patch
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from catalog import screen, classify, deduplicate, make_paper
from render import table, ordered, citation_cell, source_date
from metrics import accepts, repo_name
import render


def record(title, abstract='', url='https://arxiv.org/abs/2501.00001', authors=None, conf='ARXIV2025'):
    return dict(paper_name=title, paper_abstract=abstract, paper_url=url,
                paper_authors=authors if authors is not None else ['Ada Lovelace'],
                paper_code='#', conf=conf, _source='fixture', _line=1)


class ScreeningTests(unittest.TestCase):
    def test_explicit_survey(self):
        self.assertEqual(screen(record('A Survey on Large Language Models'))[0], 'include')

    def test_empirical_questionnaire(self):
        self.assertEqual(screen(record('A Survey of AI Adoption', 'We surveyed 300 participants using an online questionnaire.'))[0], 'exclude')

    def test_product_review_method(self):
        self.assertEqual(screen(record('Neural Review Generation for Product Recommendations', 'We propose a new neural model.'))[0], 'exclude')

    def test_original_method(self):
        self.assertEqual(screen(record('Training language models to follow instructions with human feedback'))[0], 'exclude')

    def test_review_generation_method(self):
        self.assertEqual(screen(record('LiRA: A Multi-Agent Framework for Reliable Literature Review Generation', 'We review existing methods before proposing our system.'))[0], 'exclude')

    def test_astronomical_survey(self):
        self.assertEqual(screen(record('A Catalog of Radio Galaxies from the FIRST Survey via Deep Learning'))[0], 'exclude')

    def test_true_code_review_survey(self):
        self.assertEqual(screen(record('A Survey of Code Review with Large Language Models', 'This paper provides a comprehensive review of existing methods.'))[0], 'include')

    def test_non_ai_review(self):
        self.assertEqual(screen(record('A Review of Marine Sediment Chemistry', 'We review sediment chemistry in the ocean.'))[0], 'exclude')

    def test_tutorial_requires_review(self):
        self.assertEqual(screen(record('A Tutorial on Large Language Models'))[0], 'review')


class ClassificationTests(unittest.TestCase):
    def test_quantization(self):
        self.assertEqual(classify('A Survey of Quantization for Large Language Models')[0], '16-systems')

    def test_medical_vision(self):
        self.assertEqual(classify('A Comprehensive Survey of Medical Image Segmentation')[0], '17-applications')

    def test_secondary_benchmark_word(self):
        self.assertEqual(classify('A Survey on Knowledge Graphs: Benchmarks, Evaluation, and Challenges')[0], '09-knowledge')

    def test_multimodal_alignment(self):
        self.assertNotEqual(classify('Multimodal Alignment and Fusion: A Survey')[0], '15-trustworthy')


class IdentityTests(unittest.TestCase):
    def test_cross_source_work(self):
        a=record('A Survey of Neural Networks', authors=['Ada Lovelace'])
        b=record('A Survey of Neural Networks.', url='https://doi.org/10.1234/example', authors=['Lovelace, Ada'], conf='TPAMI2026')
        groups=deduplicate([a,b])
        self.assertEqual(len(groups),1)
        paper=make_paper(groups[0],{})
        self.assertEqual(paper['venue'],'TPAMI')
        self.assertEqual(paper['year'],2026)
        self.assertEqual(len(paper['versions']),2)

    def test_same_title_different_authors(self):
        a=record('A Survey of Neural Networks', authors=['Ada Lovelace'])
        b=record('A Survey of Neural Networks', authors=['Alan Turing'])
        self.assertEqual(len(deduplicate([a,b])),2)

    def test_same_url_conflicting_title(self):
        self.assertEqual(len(deduplicate([record('A Survey of Neural Networks'),record('A Survey of Computer Vision')])),2)

    def test_version_suffixes(self):
        a=record('A Survey of Neural Networks',url='https://arxiv.org/abs/2501.00001v1')
        b=record('A Survey of Neural Networks',url='https://arxiv.org/abs/2501.00001v2')
        self.assertEqual(len(deduplicate([a,b])),1)

    def test_untrusted_markdown_title(self):
        p=dict(year=2025,title='A | B <script> [x]',venue='arXiv',paper_url='https://arxiv.org/abs/2501.00001',code_url=None,id='x')
        rendered=table([p])
        self.assertIn('&#124;',rendered)
        self.assertNotIn('<script>',rendered)
        self.assertIn('N/A',rendered)


class MetricsTests(unittest.TestCase):
    def paper(self, work_id, count, year=2025):
        return {'id': work_id, 'title': work_id, 'year': year, '_metrics': {'citation_count': count}}

    def test_citation_order_unknown_after_zero(self):
        rows = [self.paper('unknown',None),self.paper('zero',0),self.paper('high',300)]
        self.assertEqual([p['id'] for p in ordered(rows,'citations')],['high','zero','unknown'])

    def test_time_order_newest_year_first(self):
        rows = [self.paper('old-popular',300,2024),self.paper('new',1,2026)]
        self.assertEqual([p['id'] for p in ordered(rows,'time')],['new','old-popular'])

    def test_time_order_uses_dates_before_citations(self):
        old, new, unknown = self.paper('old',300), self.paper('new',1), self.paper('unknown',500)
        old['versions'] = [{'year':2025,'source_first_submitted_at':'2025-02-15T12:00:00Z'}]
        new['versions'] = [{'year':2025,'source_first_submitted_at':'2025-10-01T12:00:00Z'}]
        self.assertEqual([p['id'] for p in ordered([unknown,old,new],'time')],['new','old','unknown'])

    def test_time_does_not_invent_dates_from_other_years(self):
        paper = self.paper('p',1,2026)
        paper['versions'] = [{'year':2024,'source_first_submitted_at':'2024-05-01T00:00:00Z'}]
        self.assertIsNone(source_date(paper))

    def test_counts_with_github_stars(self):
        p = self.paper('p',123)
        p['_metrics'].update(citation_source_url='https://openalex.org/W1',github_repository='owner/repo',
                             github_stars=456,github_stars_url='https://github.com/owner/repo')
        cell = citation_cell(p)
        self.assertIn('[123]',cell)
        self.assertIn(' (',cell)
        self.assertIn('⭐ 456',cell)

    def test_missing_counts_are_not_zero(self):
        p = self.paper('p',None)
        self.assertEqual(citation_cell(p),'N/A')

    def test_github_subdirectory_maps_to_repository(self):
        self.assertEqual(repo_name('https://github.com/Owner/Repo/tree/main/docs'),'owner/repo')
        self.assertIsNone(repo_name('https://example.com/owner/repo'))

    def test_identifier_does_not_override_wrong_title(self):
        paper={'title':'A Survey of Large Language Models','dois':['10.1/wrong'],'arxiv_ids':[],'year':2025,'authors':['Ada Lovelace']}
        work={'title':'A Survey of Deep Sea Chemistry','doi':'https://doi.org/10.1/wrong','publication_year':2025}
        self.assertFalse(accepts(paper,work)[0])

    def test_title_only_needs_author_evidence(self):
        paper={'title':'A Survey of Large Language Models','dois':[],'arxiv_ids':[],'year':2025,'authors':['Ada Lovelace']}
        work={'title':paper['title'],'doi':None,'publication_year':2025,'authorships':[{'author':{'display_name':'Alan Turing'}}]}
        self.assertFalse(accepts(paper,work)[0])

    def test_time_view_navigation_keeps_selected_sort(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            path = root/'docs/papers/topic.md'
            with patch.multiple(render, ROOT=root, SORT_MODE='time'):
                render.save(path, '# Topic\n\n[Home](../../README.md) [Next](topic-2.md) [Source](https://example.com/p.md) [Count](<https://openalex.org/W1>)')
            text = (root/'docs/papers/topic.by-time.md').read_text(encoding='utf-8')
            self.assertIn('(../../README.by-time.md)',text)
            self.assertIn('(topic-2.by-time.md)',text)
            self.assertIn('[按引用 ↓](topic.md)',text)
            self.assertIn('(https://example.com/p.md)',text)
            self.assertIn('(<https://openalex.org/W1>)',text)
            self.assertNotIn('.by-time.by-time',text)


if __name__ == '__main__':
    unittest.main()
