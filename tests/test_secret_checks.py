import importlib.util
from pathlib import Path
import unittest

path = Path(__file__).resolve().parents[1] / 'scripts/check-secrets.py'
spec = importlib.util.spec_from_file_location('secret_checks', path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class SecretChecks(unittest.TestCase):
    def test_mixed_payload_does_not_hide_plaintext(self):
        secret = {'kind': 'Secret', 'stringData': {'encrypted': 'ENC[AES256_GCM,test]', 'plain': 'not-encrypted'}, 'sops': {'mac': 'ENC[test]'}}
        errors = module.check_object(secret, 'fixture')
        self.assertEqual(len(errors), 1)
        self.assertIn('stringData.plain', errors[0])
        self.assertNotIn('not-encrypted', errors[0])

    def test_sops_empty_values_are_allowed(self):
        self.assertEqual(module.check_object({'kind': 'Secret', 'stringData': {'unused': ''}, 'sops': {'mac': 'ENC[test]'}}, 'fixture'), [])

    def test_list_payload_is_checked(self):
        errors = module.check_object({'kind': 'List', 'items': [{'kind': 'Secret', 'data': {'plain': 'not-encrypted'}}]}, 'fixture')
        self.assertTrue(errors)

    def test_ciphertext_without_sops_metadata_is_rejected(self):
        self.assertTrue(module.check_object({'kind': 'Secret', 'data': {'key': 'ENC[AES256_GCM,test]'}}, 'fixture'))


if __name__ == '__main__':
    unittest.main()
