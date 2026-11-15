import unittest
from unittest.mock import patch

from app.security import create_token, hash_password, read_token, verify_password


class PasswordTests(unittest.TestCase):
    def test_password_round_trip(self):
        encoded = hash_password("Correct horse battery staple!")
        self.assertTrue(verify_password("Correct horse battery staple!", encoded))
        self.assertFalse(verify_password("wrong password", encoded))

    def test_malformed_hash_is_rejected(self):
        for value in ("", "not-base64", "YWJj", "!!!!"):
            self.assertFalse(verify_password("password", value))


class TokenTests(unittest.TestCase):
    def test_token_round_trip(self):
        token = create_token(42)
        self.assertEqual(read_token(token), 42)

    def test_tampered_token_is_rejected(self):
        token = create_token(42)
        self.assertIsNone(read_token(token + "x"))

    def test_invalid_subject_is_rejected(self):
        with self.assertRaises(ValueError):
            create_token(0)
        with self.assertRaises(ValueError):
            create_token(True)

    def test_expired_token_is_rejected(self):
        with patch("app.security.TOKEN_TTL_SECONDS", -1):
            token = create_token(42)
        self.assertIsNone(read_token(token))

    def test_malformed_tokens_are_rejected(self):
        for token in ("", "abc", "a.b", None, "x" * 5000):
            self.assertIsNone(read_token(token))


if __name__ == "__main__":
    unittest.main()
