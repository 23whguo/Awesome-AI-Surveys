import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from catalog import screen, classify, deduplicate, make_paper
from render import table


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


if __name__ == '__main__':
    unittest.main()
