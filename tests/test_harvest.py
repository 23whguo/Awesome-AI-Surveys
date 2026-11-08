import sys
from pathlib import Path
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from harvest import crossref_date, crossref_record, hf_record, plain, months
from catalog import screen, make_paper, external_review_hint, deduplicate, is_candidate, classify
import datetime as dt


class SourceAdapterTests(unittest.TestCase):
    def test_posted_date_precedes_registry_creation(self):
        work={'posted':{'date-parts':[[2026,2,1]]},'created':{'date-parts':[[2026,3,2]]}}
        self.assertEqual(crossref_date(work),('2026-02-01','posted'))

    def test_invalid_date_falls_back_without_inventing_day(self):
        work={'posted':{'date-parts':[[2026]]},'published':{'date-parts':[[2026,2,30]]}}
        self.assertEqual(crossref_date(work),(None,None))

    def test_crossref_identity_and_authors_are_preserved(self):
        work={'DOI':'10.20944/Preprints202601.0001.v2','title':['AI &amp; ML: A Review'],
              'author':[{'given':'Ada','family':'Lovelace'},{'name':'Research Group'}],
              'posted':{'date-parts':[[2026,1,3]]}}
        row=crossref_record(work,'preprints','2026-11-08T00:00:00Z')
        self.assertEqual(row['paper_authors'],['Ada Lovelace','Research Group'])
        self.assertEqual(row['paper_name'],'AI & ML: A Review')
        self.assertEqual(row['source_record_id'],'10.20944/preprints202601.0001.v2')
        self.assertEqual(row['conf'],'Preprints.org2026')

    def test_hf_selection_year_does_not_replace_publication_year(self):
        entry={'paper':{'id':'2512.12345','title':'A Survey of Language Models','authors':[],
                        'publishedAt':'2025-12-28T00:00:00Z','submittedOnDailyAt':'2026-01-02T00:00:00Z'}}
        row=hf_record(entry,'2026-01-02','2026-11-08T00:00:00Z')
        self.assertEqual(row['conf'],'ARXIV2025')
        self.assertEqual(row['paper_url'],'https://arxiv.org/abs/2512.12345')
        self.assertEqual(row['source_selected_on'],'2026-01-02')

    def test_cutoff_month_is_not_extended_to_month_end(self):
        intervals=list(months(dt.date(2026,1,1),dt.date(2026,11,8)))
        self.assertEqual(len(intervals),11)
        self.assertEqual(intervals[-1][1],dt.date(2026,11,8))

    def test_html_is_not_retained_in_abstracts(self):
        self.assertEqual(plain('<jats:p>AI &amp; <b>ML</b>.</jats:p>'),'AI & ML .')
        self.assertEqual(plain('&lt;span&gt;AI&lt;/span&gt;'),'AI')


class ExtendedDiscoveryTests(unittest.TestCase):
    def record(self,title,abstract):
        return {'paper_name':title,'paper_abstract':abstract,'source_external':'preprints',
                'paper_url':'https://doi.org/10.20944/example','paper_authors':['Ada Lovelace'],
                'paper_code':'#','conf':'Preprints.org2026','_source':'fixture','_line':1}

    def test_review_without_title_marker_is_discovered(self):
        row=self.record('Machine Learning for Clinical Decision Support','This systematic review synthesizes evidence from 140 studies.')
        self.assertTrue(is_candidate(row))
        self.assertEqual(screen(row)[0],'include')

    def test_review_in_method_introduction_is_not_auto_included(self):
        row=self.record('Machine Learning for Clinical Decision Support','This review informs our design. We propose a new neural method.')
        self.assertEqual(screen(row)[0],'review')

    def test_bibliometric_titles_are_retained_for_review(self):
        row=self.record('A Bibliometric Analysis of Artificial Intelligence in Education','We analyze publication trends and citation networks.')
        self.assertTrue(is_candidate(row))
        self.assertEqual(screen(row)[0],'include')

    def test_withdrawn_reviews_are_not_silently_included(self):
        row=self.record('A Survey of Large Language Models','A comprehensive survey.')
        row['source_withdrawn_at']='2026-05-01T00:00:00Z'
        self.assertEqual(screen(row)[0],'review')

    def test_biological_neural_mechanisms_are_not_ai_evidence(self):
        row=self.record('A Review of Neural Mechanisms in Human Vision','This review discusses neural mechanisms and brain pathways.')
        self.assertEqual(screen(row)[0],'exclude')

    def test_explicit_ai_subfields_are_not_lost_to_singular_word_boundaries(self):
        titles=[
            'A Comprehensive Survey of 4D Gaussian Splatting',
            'A Comprehensive Survey of Tabular Anomaly Detection',
            'Multi-Agent Systems and Their Evolution: A Comparative Survey',
            'Human-Centric Content Generation with Diffusion Models: A Survey',
            'A Survey of Knowledge Graphs',
            'Recent Advances in Adversarial Attacks: A Comprehensive Survey',
            'A Survey of Federated Model Evolution',
            'Meta-Learning and Few-Shot Learning: A Comprehensive Survey',
            'From Specialist to Generalist: A Comprehensive Survey on World Models',
            'A Survey on Federated Unlearning',
            'Foundation Neural Operators: A Survey on Pretraining Methods',
            'From Models to Systems: A Comprehensive Survey of Efficient Multimodal Learning',
            'A Survey of Agent Skills for Foundation-Model Agents',
            'Neural Question Generation: A Survey of Techniques',
            'Unraveling Noise in 3D Point Clouds: A Comprehensive Survey',
        ]
        for title in titles:
            with self.subTest(title=title):
                self.assertEqual(screen(self.record(title,'We examine recent developments.'))[0],'include')

    def test_expanded_ai_scope_can_support_an_abstract_led_review(self):
        row=self.record('RAG in Self-Regulated Personalised Learning','This review examines existing systems and evidence.')
        self.assertEqual(screen(row)[0],'include')

    def test_power_transformer_review_is_not_automatically_an_ai_survey(self):
        for title in ['A Review of Power Transformer Insulation','A Review of Power Transformers']:
            row=self.record(title,'This review discusses cellulose aging and dielectric oils.')
            self.assertEqual(screen(row)[0],'exclude')

    def test_original_method_is_not_made_a_survey_by_diffusion_scope(self):
        row=self.record('DiffusionOPD: A Unified Perspective of On-Policy Distillation in Diffusion Models',
                        'We propose a new multi-task training method for diffusion models.')
        self.assertNotEqual(screen(row)[0],'include')

    def test_informed_consent_review_is_a_task_not_an_article_type(self):
        row=self.record('Retrieval-Augmented Generation Enhanced GPT-4.1 to Support Clinical Trial Informed Consent Review for Data Reuse',
                        'We evaluate a new system on 438 informed-consent documents.')
        self.assertEqual(screen(row)[0],'exclude')

    def test_explicit_review_subtypes_are_recognized_for_external_sources(self):
        for title in ['AI in Cardiac Amyloidosis: A State-of-the-Art Review',
                      'Artificial Intelligence in Higher Education: Short Review',
                      'Machine Learning in the Energy Industry: A Systematic, Evidence-Graded Survey']:
            with self.subTest(title=title):
                self.assertEqual(screen(self.record(title,'We examine the current literature.'))[0],'include')

    def test_dataset_counts_and_pdf_line_numbers_are_not_participant_surveys(self):
        for title,abstract in [
            ('A Survey of 1000+ Medical Imaging Datasets for Foundation Models',
             'We compare dataset modalities, annotations and evaluation protocols.'),
            ('LLM-Based Multi-Agent Orchestration: A Survey of Frameworks',
             'This survey 4 examines existing frameworks and protocols.'),
        ]:
            with self.subTest(title=title):
                self.assertEqual(screen(self.record(title,abstract))[0],'include')

    def test_numeric_participant_survey_is_still_excluded(self):
        row=self.record('A Survey of AI Adoption in Higher Education',
                        'We surveyed 1,000 university students about AI adoption.')
        self.assertEqual(screen(row)[0],'exclude')

    def test_gallium_nitride_is_not_a_generative_adversarial_network(self):
        row=self.record('A Review of Double Pulse Test Techniques for GaN Power Devices',
                        'This paper reviews GaN-based high-frequency power converters.')
        self.assertEqual(screen(row)[0],'exclude')

    def test_ai_assisted_search_is_not_review_subject_evidence(self):
        row=self.record('A Systematic Review of Overhead Transmission Line Ratings',
                        'This systematic review retrieved 1234 records with the AI-assisted tool Consensus.')
        self.assertNotEqual(screen(row)[0],'include')

    def test_protocol_is_not_a_completed_review(self):
        row=self.record('Artificial Intelligence in Medicine: A Scoping Review Protocol','This review will examine artificial intelligence.')
        self.assertEqual(screen(row)[0],'review')

    def test_preprint_does_not_replace_archival_venue(self):
        preprint=self.record('A Survey of Large Language Models','This review summarizes existing models.')
        archival={**preprint,'conf':'TPAMI2026','source_external':None,'paper_url':'https://doi.org/10.1234/archival'}
        preprint['source_first_submitted_at']='2026-02-01'
        paper=make_paper([preprint,archival],{})
        self.assertEqual(paper['venue'],'TPAMI')
        self.assertTrue(any(v['source_first_submitted_at']=='2026-02-01' for v in paper['versions']))
        self.assertEqual(len(paper['sources']),2)

    def test_versioned_dois_merge_with_author_evidence(self):
        first=self.record('A Survey of Large Language Models','Review.')
        first['paper_url']='https://doi.org/10.20944/preprints202601.0001.v1'
        second={**first,'paper_url':'https://doi.org/10.20944/preprints202601.0001.v2'}
        self.assertEqual(len(deduplicate([first,second])),1)

    def test_small_title_update_can_merge_only_with_shared_identifier(self):
        first=self.record('A Comprehensive Survey of Large Language Models: Techniques and Applications','Review.')
        second={**first,'paper_name':'A Comprehensive Survey of Large Language Models: Techniques & Applications'}
        self.assertEqual(len(deduplicate([first,second])),1)
        second['paper_url']='https://doi.org/10.20944/different'
        self.assertEqual(len(deduplicate([first,second])),2)

    def test_original_preprint_identity_is_preserved(self):
        original=self.record('A Survey of Large Language Models','Short abstract.')
        original['source_external']=None
        original['conf']='ARXIV2026'
        updated={**original,'conf':'Preprints.org2026','source_external':'preprints','paper_abstract':'A much longer abstract with more details.'}
        paper=make_paper([original,updated],{})
        self.assertEqual(paper['venue'],'arXiv')

    def test_colon_does_not_hide_scope_inside_subtitle(self):
        result=classify('Understanding the Adversary: A Survey of Adversarial Machine Learning in Network Intrusion Detection',expanded_scope=True)
        self.assertFalse(result[3])
        self.assertEqual(result[0],'17-applications')


if __name__=='__main__':
    unittest.main()
