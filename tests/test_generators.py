import os
import sys
import unittest
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import generators  # noqa: E402  pylint: disable=wrong-import-position


class TokenGeneratorTests(unittest.TestCase):

    def test_url_safe_token_has_exact_length_and_charset(self):
        for length in (1, 8, 32, 129):
            value = generators.url_safe_token(length)
            self.assertEqual(len(value), length)
            self.assertTrue(set(value) <= set(generators.URL_SAFE))

    def test_url_safe_token_can_exclude_ambiguous_characters(self):
        for _ in range(25):
            value = generators.url_safe_token(64, exclude_ambiguous=True)
            self.assertFalse(set(value) & set(generators.AMBIGUOUS_CHARS))

    def test_hex_token_has_exact_length_and_charset(self):
        for length in (1, 2, 31, 64):
            value = generators.hex_token(length)
            self.assertEqual(len(value), length)
            self.assertTrue(set(value) <= set(generators.HEX_CHARS))

    def test_numeric_code_is_all_digits(self):
        for _ in range(20):
            value = generators.numeric_code(8)
            self.assertEqual(len(value), 8)
            self.assertTrue(value.isdigit())

    def test_numeric_code_can_start_with_zero(self):
        values = [generators.numeric_code(6) for _ in range(3000)]
        self.assertTrue(any(value.startswith("0") for value in values))

    def test_base64_token_is_url_safe_without_padding(self):
        for num_bytes in (1, 3, 16, 24):
            value = generators.base64_token(num_bytes)
            expected = 4 * ((num_bytes + 2) // 3) - ((3 - num_bytes % 3) % 3)
            self.assertEqual(len(value), expected)
            self.assertNotIn("=", value)
            self.assertTrue(set(value) <= set(generators.URL_SAFE))

    def test_api_key_keeps_prefix(self):
        self.assertTrue(generators.api_key(16, "sk_").startswith("sk_"))
        self.assertTrue(generators.api_key(16, "live_").startswith("live_"))
        self.assertEqual(len(generators.api_key(16, "sk_")), 19)

    def test_invalid_lengths_are_rejected(self):
        for function in (generators.url_safe_token, generators.hex_token,
                         generators.numeric_code, generators.base64_token):
            with self.assertRaises(ValueError):
                function(0)

    def test_random_string_rejects_empty_alphabet(self):
        with self.assertRaises(ValueError):
            generators.random_string(4, "")


class PasswordTests(unittest.TestCase):

    def test_password_contains_every_required_class(self):
        for _ in range(25):
            value = generators.password(12)
            self.assertTrue(any(c.islower() for c in value))
            self.assertTrue(any(c.isupper() for c in value))
            self.assertTrue(any(c.isdigit() for c in value))
            self.assertTrue(any(c in generators.SYMBOLS for c in value))

    def test_password_without_symbols(self):
        for _ in range(25):
            value = generators.password(16, symbols=False)
            self.assertEqual(len(value), 16)
            for char in generators.SYMBOLS:
                self.assertNotIn(char, value)

    def test_password_excludes_ambiguous_characters(self):
        for _ in range(25):
            value = generators.password(20, exclude_ambiguous=True)
            self.assertFalse(set(value) & set(generators.AMBIGUOUS_CHARS))

    def test_password_shorter_than_class_count_still_works(self):
        self.assertEqual(len(generators.password(2)), 2)


class UuidAndUlidTests(unittest.TestCase):

    def test_uuid4_is_version_4(self):
        parsed = uuid.UUID(generators.uuid4_str())
        self.assertEqual(parsed.version, 4)
        self.assertEqual(parsed.variant, uuid.RFC_4122)

    def test_uuid7_is_version_7_and_variant_rfc4122(self):
        for _ in range(50):
            parsed = uuid.UUID(generators.uuid7_str())
            self.assertEqual(parsed.version, 7)
            self.assertEqual(parsed.variant, uuid.RFC_4122)

    def test_uuid7_is_monotonic(self):
        values = [generators.uuid7_str() for _ in range(200)]
        self.assertEqual(values, sorted(values))

    def test_ulid_has_26_crockford_characters(self):
        for _ in range(50):
            value = generators.ulid_str()
            self.assertEqual(len(value), 26)
            self.assertTrue(set(value) <= set(generators.CROCKFORD32))

    def test_ulid_is_monotonic(self):
        values = [generators.ulid_str() for _ in range(200)]
        self.assertEqual(values, sorted(values))

    def test_ulid_starts_with_current_timestamp(self):
        value = generators.ulid_str()
        timestamp = 0
        for char in value[:10]:
            timestamp = timestamp * 32 + generators.CROCKFORD32.index(char)
        self.assertAlmostEqual(timestamp, generators.time.time() * 1000, delta=5000)


class HashTests(unittest.TestCase):

    def test_known_vectors(self):
        self.assertEqual(
            generators.hash_text("", "sha256"),
            "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855")
        self.assertEqual(
            generators.hash_text("abc", "sha1"),
            "a9993e364706816aba3e25717850c26c9cd0d89d")
        self.assertEqual(
            generators.hash_text("abc", "md5"),
            "900150983cd24fb0d6963f7d28e17f72")
        self.assertEqual(
            generators.hash_text("abc", "sha512"),
            "ddaf35a193617abacc417349ae20413112e6fa4e89a97ea20a9eeee64b55d39a"
            "2192992a274fc1a836ba3c23a3feebbd454d4423643ce80e2a9ac94fa54ca49f")

    def test_unknown_algorithm_is_rejected(self):
        with self.assertRaises(ValueError):
            generators.hash_text("abc", "crc32")


class EntropyTests(unittest.TestCase):

    def test_entropy_of_hex_and_digits(self):
        self.assertEqual(generators.entropy_bits(16, 8), 32.0)
        self.assertEqual(generators.entropy_bits(10, 6), 19.9)
        self.assertEqual(generators.entropy_bits(1, 10), 0.0)
        self.assertEqual(generators.entropy_bits(64, 0), 0.0)


if __name__ == "__main__":
    unittest.main()
