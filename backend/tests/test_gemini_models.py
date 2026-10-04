import io
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import engine


class GeminiModelTests(unittest.TestCase):
    def model(self, name, methods=('generateContent',)):
        return {'name': 'models/' + name, 'supportedGenerationMethods': list(methods)}

    def resolve(self, model):
        return engine.resolve_gemini_model({'gemini_key': 'test-only-key', 'gemini_model': model})

    def test_preserves_available_model_and_normalizes_resource_prefix(self):
        with patch('engine.api', return_value={'models': [self.model('gemini-2.5-flash')]}):
            self.assertEqual(self.resolve(' models/gemini-2.5-flash '), 'gemini-2.5-flash')

    def test_retired_model_uses_available_stable_flash(self):
        with patch('engine.api', return_value={'models': [self.model('gemini-2.5-flash')]}):
            self.assertEqual(self.resolve('gemini-2.0-flash'), 'gemini-2.5-flash')

    def test_does_not_choose_pro_or_unsupported_generation(self):
        with patch('engine.api', return_value={'models': [self.model('gemini-2.5-pro'), self.model('gemini-2.5-flash', ('embedContent',))]}):
            with self.assertRaisesRegex(engine.ProcessingError, 'unavailable'):
                self.resolve('gemini-2.0-flash')

    def test_follows_model_list_pagination(self):
        with patch('engine.api', side_effect=[{'models': [], 'nextPageToken': 'next'}, {'models': [self.model('gemini-2.5-flash')]}]) as api:
            self.assertEqual(self.resolve('gemini-2.0-flash'), 'gemini-2.5-flash')
            self.assertIn('pageToken=next', api.call_args.args[0])

    def test_http_404_is_specific_without_disclosing_provider_body_or_key(self):
        failure = HTTPError('https://example.invalid', 404, 'not found', {}, io.BytesIO(b'private diagnostic'))
        with patch('engine.request.urlopen', side_effect=failure):
            with self.assertRaises(engine.ProviderHTTPError) as result:
                engine.api('https://example.invalid', 'test-only-key', provider='gemini')
            self.assertEqual(result.exception.status, 404)
            self.assertIn('model', str(result.exception))
            self.assertNotIn('quota', str(result.exception))
            self.assertNotIn('private diagnostic', str(result.exception))


if __name__ == '__main__':
    unittest.main()
