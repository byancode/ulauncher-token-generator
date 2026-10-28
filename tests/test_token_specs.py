import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import token_specs  # noqa: E402  pylint: disable=wrong-import-position

SETTINGS = token_specs.Settings(
    default_length=48,
    pin_length=8,
    password_symbols=False,
    hash_algorithm="sha1",
)


class ParseCommandTests(unittest.TestCase):

    def parse(self, argument, settings=token_specs.DEFAULT_SETTINGS):
        return token_specs.parse(argument, settings)

    def test_empty_argument_is_overview(self):
        self.assertEqual(self.parse("").mode, "overview")
        self.assertEqual(self.parse("   ").mode, "overview")
        self.assertIsNone(self.parse("").error)

    def test_uuid_commands(self):
        self.assertEqual(self.parse("uuid").mode, "uuid4")
        self.assertEqual(self.parse("uuid4").mode, "uuid4")
        self.assertEqual(self.parse("GUID").mode, "uuid4")
        self.assertEqual(self.parse("uuid7").mode, "uuid7")
        self.assertEqual(self.parse("ulid").mode, "ulid")

    def test_bare_number_is_token_length(self):
        request = self.parse("64")
        self.assertEqual((request.mode, request.length), ("token", 64))

    def test_length_can_precede_the_command(self):
        request = self.parse("64 hex")
        self.assertEqual((request.mode, request.length), ("hex", 64))

    def test_explicit_lengths(self):
        self.assertEqual(self.parse("hex 48").length, 48)
        self.assertEqual(self.parse("token 16").length, 16)
        self.assertEqual(self.parse("pin 4").length, 4)
        self.assertEqual(self.parse("password 30").length, 30)
        self.assertEqual(self.parse("base64 32").length, 32)
        self.assertEqual(self.parse("apikey 12").length, 12)

    def test_length_flag(self):
        self.assertEqual(self.parse("-n 40 token").length, 40)
        self.assertEqual(self.parse("token -n 40").length, 40)
        self.assertEqual(self.parse("token --length 40").length, 40)

    def test_default_lengths_come_from_settings(self):
        self.assertEqual(self.parse("token", SETTINGS).length, 48)
        self.assertEqual(self.parse("pin", SETTINGS).length, 8)
        self.assertEqual(self.parse("password", SETTINGS).length,
                         token_specs.DEFAULT_PASSWORD_LENGTH)

    def test_symbol_flags(self):
        self.assertTrue(self.parse("password 20 -s").symbols)
        self.assertFalse(self.parse("password 20", SETTINGS).symbols)
        self.assertTrue(self.parse("password 20", token_specs.DEFAULT_SETTINGS).symbols)
        self.assertFalse(self.parse("password 20 -p").symbols)

    def test_ambiguous_characters_flag(self):
        self.assertTrue(self.parse("token 20 -c").exclude_ambiguous)
        self.assertTrue(self.parse("--no-ambiguous token 20").exclude_ambiguous)
        self.assertFalse(self.parse("token 20").exclude_ambiguous)

    def test_refresh_flag(self):
        self.assertTrue(self.parse("-r uuid").refresh)
        self.assertTrue(self.parse("uuid --refresh").refresh)
        self.assertTrue(self.parse("refresh").refresh)

    def test_hash_commands(self):
        request = self.parse("sha256 hello world")
        self.assertEqual((request.mode, request.payload, request.algorithm),
                         ("hash", "hello world", "sha256"))
        self.assertIsNone(request.error)

    def test_hash_keeps_numeric_payload(self):
        request = self.parse("md5 12345")
        self.assertEqual((request.payload, request.algorithm), ("12345", "md5"))

    def test_hash_uses_default_algorithm_from_settings(self):
        request = self.parse("hash some text", SETTINGS)
        self.assertEqual((request.mode, request.payload, request.algorithm),
                         ("hash", "some text", "sha1"))

    def test_hash_requires_text(self):
        request = self.parse("hash")
        self.assertEqual(request.mode, "hash")
        self.assertIsNotNone(request.error)

    def test_api_key_prefix(self):
        self.assertEqual(self.parse("apikey live").payload, "live_")
        self.assertEqual(self.parse("apikey sk-").payload, "sk-")
        self.assertEqual(self.parse("apikey").payload, token_specs.DEFAULT_API_KEY_PREFIX)
        self.assertIsNotNone(self.parse("apikey bad prefix!").error)

    def test_help(self):
        self.assertEqual(self.parse("help").mode, "help")
        self.assertEqual(self.parse("?").mode, "help")

    def test_unknown_command_suggests_matches(self):
        request = self.parse("qwerty")
        self.assertIsNone(request.mode)
        self.assertIn("Unknown", request.error)
        self.assertTrue(request.suggestions)

    def test_ambiguous_prefix_lists_candidates(self):
        request = self.parse("u")
        self.assertIsNone(request.mode)
        self.assertIn("uuid", request.suggestions)
        self.assertIn("ulid", request.suggestions)

    def test_unknown_option_is_reported(self):
        request = self.parse("-x uuid")
        self.assertIsNotNone(request.error)
        self.assertIn("-x", request.error)

    def test_length_flag_without_number_is_reported(self):
        request = self.parse("-n uuid")
        self.assertIsNotNone(request.error)

    def test_out_of_range_lengths_are_reported(self):
        self.assertIsNotNone(self.parse("pin 0").error)
        self.assertIsNotNone(self.parse("token 5000").error)
        self.assertIsNotNone(self.parse("password 2").error)

    def test_extra_words_are_ignored_for_non_hash_commands(self):
        request = self.parse("uuid some extra words")
        self.assertEqual(request.mode, "uuid4")
        self.assertIsNone(request.error)

    def test_quoted_payload_is_unquoted(self):
        request = self.parse('sha256 "hello world"')
        self.assertEqual(request.payload, "hello world")

    def test_argument_is_preserved_for_regeneration(self):
        self.assertEqual(self.parse("  token 40 -c ").argument, "token 40 -c")


class ResolveTests(unittest.TestCase):

    def test_resolve_fills_defaults(self):
        request = token_specs.resolve("pin", SETTINGS)
        self.assertEqual(request.length, 8)
        self.assertIsNone(request.error)

    def test_resolve_reports_unknown_mode(self):
        self.assertIsNotNone(token_specs.resolve("nope").error)

    def test_resolve_keeps_payload(self):
        request = token_specs.resolve("hash", payload="abc", algorithm="md5")
        self.assertEqual((request.payload, request.algorithm), ("abc", "md5"))

    def test_resolve_rejects_unknown_hash_algorithm(self):
        request = token_specs.resolve("hash", payload="abc", algorithm="crc32")
        self.assertEqual(request.algorithm, "sha256")


if __name__ == "__main__":
    unittest.main()
