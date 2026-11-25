import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch
import io
import json
import fog
from api import analyze as web

class FogTests(unittest.TestCase):
    def test_sample_disagreements_and_lines(self):
        spec = Path('sample-spec.md').read_text()
        answers = [fog.validate(fog.offline(spec, p), len(spec.splitlines())) for p in fog.PERSONAS]
        findings = fog.compare(spec, answers)
        self.assertGreaterEqual(len(findings), 3)
        self.assertTrue(all(f['spec'] == spec.splitlines()[f['line']-1] for f in findings))
        self.assertTrue(all(len(set(f['assumptions'].values())) == 3 for f in findings))
        self.assertEqual([f['severity'] for f in findings], sorted([f['severity'] for f in findings], reverse=True))

    def test_agreement_and_missing_coverage_are_not_disagreements(self):
        answers = [dict(persona=p, decisions=[dict(line=1, topic='x', impact=3, assumption='same')]) for p in fog.PERSONAS]
        self.assertEqual(fog.compare('text', answers), [])
        answers[1]['decisions'] = []
        answers[2]['decisions'] = []
        self.assertEqual(fog.compare('text', answers), [])

    def test_html_escaping(self):
        spec = 'daily <script>alert(1)</script>'
        answers = [fog.offline(spec, p) for p in fog.PERSONAS]
        with tempfile.TemporaryDirectory() as td:
            fog.write_reports(Path(td), spec, answers, fog.compare(spec, answers), 'offline')
            page = (Path(td) / 'report.html').read_text()
            self.assertNotIn('<script>', page)
            self.assertIn('&lt;script&gt;', page)

    def test_live_transport_preserves_evidence(self):
        interpretation = dict(data_model={'Habit': ['id']}, endpoints=['GET /habits'],
                              decisions=[dict(line=1, topic='day boundary', impact=3, assumption='Local midnight.')])
        response = dict(model='test-model', usage={'total_tokens': 123},
                        choices=[{'message': {'content': json.dumps(interpretation)}}])
        with patch.dict('os.environ', {'OPENAI_API_KEY': 'placeholder'}), patch('urllib.request.urlopen', return_value=io.BytesIO(json.dumps(response).encode())) as send:
            answer = fog.remote('daily habits', 'backend engineer', 'api')
        fog.validate(answer, 1)
        self.assertEqual(answer['provider_evidence']['usage']['total_tokens'], 123)
        self.assertEqual(json.loads(answer['provider_evidence']['raw_content']), interpretation)
        request_body = json.loads(send.call_args.args[0].data)
        self.assertIn('Numbered spec:', request_body['messages'][0]['content'])
        self.assertIn('day boundary', request_body['messages'][0]['content'])

    def test_empty_recognized_topics(self):
        self.assertEqual(fog.compare('Build a blue button.', [fog.offline('Build a blue button.', p) for p in fog.PERSONAS]), [])

    def test_keywords_match_whole_words_only(self):
        self.assertEqual(fog.recognized_topics('Users paste a steam link gracefully.'), [])
        self.assertEqual(fog.recognized_topics('Teams can edit past entries daily.'),
                         [(1, 'day boundary'), (1, 'team habit ownership'), (1, 'historical edits')])
        self.assertEqual(fog.recognized_topics('Send a reminder.\nNotifications go out.'),
                         [(1, 'notification delivery'), (2, 'notification delivery')])

    def test_sample_topics_unchanged_by_word_matching(self):
        spec = Path('sample-spec.md').read_text()
        self.assertEqual(len(fog.recognized_topics(spec)), 6)
        self.assertEqual(len(fog.analyze(spec)['findings']), 6)

    def test_spec_limits(self):
        for bad in ('', '   \n', None, 'x' * (fog.MAX_SPEC_CHARS + 1), 'a\n' * (fog.MAX_SPEC_LINES + 1)):
            with self.assertRaises(ValueError):
                fog.check_spec(bad)

    def test_non_object_model_response_fails_loudly(self):
        response = dict(model='m', choices=[{'message': {'content': '[1, 2]'}}])
        with patch.dict('os.environ', {'OPENAI_API_KEY': 'placeholder'}), patch('urllib.request.urlopen', return_value=io.BytesIO(json.dumps(response).encode())):
            with self.assertRaises(ValueError):
                fog.remote('daily habits', 'QA engineer', 'api')

    def test_cli_writes_reports(self):
        with tempfile.TemporaryDirectory() as td, patch('sys.argv', ['fog.py', 'sample-spec.md', '--out', td]):
            fog.main()
            evidence = json.loads((Path(td) / 'evidence.json').read_text())
            self.assertEqual(len(evidence['findings']), 6)
            self.assertTrue((Path(td) / 'raw-interpretations.json').exists())
            self.assertNotIn('\u2014', (Path(td) / 'report.md').read_text())


class WebApiTests(unittest.TestCase):
    def test_offline_by_default_even_with_key(self):
        with patch.dict('os.environ', {'OPENAI_API_KEY': 'k'}, clear=True):
            self.assertEqual(web.configured_backend(), 'offline')
        with patch.dict('os.environ', {'FOG_LIVE_BACKEND': 'api'}, clear=True):
            self.assertEqual(web.configured_backend(), 'offline')
        with patch.dict('os.environ', {'FOG_LIVE_BACKEND': 'api', 'OPENAI_API_KEY': 'k'}, clear=True):
            self.assertEqual(web.configured_backend(), 'api')

    def test_run_sample(self):
        with patch.dict('os.environ', {}, clear=True):
            status, body = web.run(json.dumps({'spec': Path('sample-spec.md').read_text()}).encode())
        self.assertEqual(status, 200)
        self.assertEqual(len(body['findings']), 6)
        self.assertEqual(body['backend'], 'offline')
        self.assertEqual(body['line_count'], 7)

    def test_run_rejects_bad_input(self):
        self.assertEqual(web.run(b'not json')[0], 400)
        self.assertEqual(web.run(b'[1]')[0], 400)
        self.assertEqual(web.run(b'{"spec": ""}')[0], 400)
        self.assertEqual(web.run(b'{"spec": 5}')[0], 400)
        self.assertEqual(web.run(json.dumps({'spec': 'x' * (fog.MAX_SPEC_CHARS + 1)}).encode())[0], 400)

    def test_raw_provider_text_not_returned(self):
        answer = dict(persona='QA engineer', provider_evidence=dict(model='m', usage={}, raw_content='secret-ish'))
        self.assertNotIn('raw_content', web.public_interpretation(answer)['provider_evidence'])
        self.assertIn('raw_content', answer['provider_evidence'])


if __name__ == '__main__':
    unittest.main()
