import hashlib
import pickle
import os
import sys
import unittest
import uuid

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.argv = [os.path.join(ROOT, "main.py")]

try:
    import main  # noqa: E402  pylint: disable=wrong-import-position
    from ulauncher.api.shared.action.CopyToClipboardAction import (  # noqa: E402
        CopyToClipboardAction,
    )
    from ulauncher.api.shared.action.ExtensionCustomAction import (  # noqa: E402
        ExtensionCustomAction,
    )
    from ulauncher.api.shared.action.SetUserQueryAction import (  # noqa: E402
        SetUserQueryAction,
    )
    from ulauncher.api.shared.item.ExtensionResultItem import (  # noqa: E402
        ExtensionResultItem,
    )
    from ulauncher.api.shared.action.RenderResultListAction import (  # noqa: E402
        RenderResultListAction,
    )
    from ulauncher.api.shared.event import ItemEnterEvent, KeywordQueryEvent  # noqa: E402
    from ulauncher.search.Query import Query  # noqa: E402
    ULAUNCHER_AVAILABLE = True
except Exception as error:  # pragma: no cover - only when Ulauncher is absent
    ULAUNCHER_AVAILABLE = False
    IMPORT_ERROR = error


class FakeExtension(object):
    def __init__(self, preferences=None):
        self.preferences = preferences if preferences is not None else {}


@unittest.skipUnless(ULAUNCHER_AVAILABLE, "Ulauncher API is not installed")
class ItemBuildingTests(unittest.TestCase):

    def setUp(self):
        self.settings = main.token_specs.DEFAULT_SETTINGS
        self.cache = main.ValueCache()
        self.keyword = "gen"

    def build(self, argument, settings=None, cache=None):
        settings = settings or self.settings
        request = main.token_specs.parse(argument, settings)
        return main.build_items(request, settings, self.keyword, cache or self.cache)

    def copied(self, item):
        action = item.on_enter(None)
        self.assertIsInstance(action, CopyToClipboardAction)
        return action.text

    def test_overview_lists_quick_generators(self):
        items = self.build("")
        self.assertEqual(len(items), 5)
        self.assertEqual(uuid.UUID(self.copied(items[0])).version, 4)
        self.assertEqual(len(self.copied(items[1])), main.token_specs.DEFAULT_TOKEN_LENGTH)
        self.assertEqual(len(self.copied(items[2])), 20)
        self.assertTrue(self.copied(items[3]).isdigit())
        self.assertIsInstance(items[4].on_enter(None), SetUserQueryAction)

    def test_token_has_requested_length(self):
        items = self.build("token 40")
        self.assertEqual(items[0].get_name(), "URL-safe token (40 chars)")
        self.assertEqual(len(self.copied(items[0])), 40)
        self.assertEqual(items[1].get_name(), "Hex token (40 chars)")
        self.assertEqual(len(self.copied(items[1])), 40)

    def test_pin_and_password_are_rendered(self):
        items = self.build("pin 8")
        self.assertTrue(self.copied(items[0]).isdigit())
        self.assertEqual(len(self.copied(items[0])), 8)
        self.assertEqual(items[-1].get_name(), "Regenerate")

    def test_value_is_stable_across_renders(self):
        first = self.copied(self.build("uuid")[0])
        second = self.copied(self.build("uuid")[0])
        self.assertEqual(first, second)

    def test_regenerate_produces_a_new_value(self):
        first = self.copied(self.build("token 32")[0])
        self.cache.invalidate_all()
        second = self.copied(self.build("token 32")[0])
        self.assertNotEqual(first, second)

    def test_regenerate_item_keeps_the_window_open(self):
        items = self.build("password 20")
        action = items[-1].on_enter(None)
        self.assertIsInstance(action, ExtensionCustomAction)
        self.assertTrue(action.keep_app_open())

    def test_alt_enter_regenerates(self):
        item = self.build("uuid")[0]
        self.assertIsInstance(item.on_alt_enter(None), ExtensionCustomAction)

    def test_alt_enter_always_returns_an_action(self):
        # Ulauncher closes the window when Alt+Enter returns nothing.
        for argument in ("", "uuid", "token 32", "sha256 abc", "help", "qwerty"):
            for item in self.build(argument):
                self.assertIsNotNone(item.on_alt_enter(None), item.get_name())

    def test_hash_renders_every_algorithm(self):
        items = self.build("sha256 hello")
        self.assertEqual(len(items), 4)
        self.assertEqual(self.copied(items[0]), hashlib.sha256(b"hello").hexdigest())
        self.assertEqual(self.copied(items[1]), hashlib.sha1(b"hello").hexdigest())
        self.assertEqual(self.copied(items[2]), hashlib.md5(b"hello").hexdigest())
        self.assertFalse(any(item.get_name() == "Regenerate" for item in items))

    def test_hash_variants_do_not_repeat_the_requested_algorithm(self):
        items = self.build("sha512 abc")
        names = [item.get_name() for item in items]
        self.assertEqual(names.count("SHA-512 hash"), 1)
        self.assertEqual(len(items), 3)

    def test_unknown_command_shows_help_action(self):
        items = self.build("qwerty")
        self.assertIn("Unknown command", items[0].get_name())
        self.assertEqual(items[0].on_enter(None).new_query, "gen help")

    def test_incomplete_hash_command_suggests_example(self):
        items = self.build("hash")
        self.assertEqual(items[0].on_enter(None).new_query, "gen sha256 hello")

    def test_help_lists_commands(self):
        items = self.build("help")
        names = [item.get_name() for item in items]
        self.assertIn("gen uuid", names)
        self.assertEqual(names[-1], "Options")
        self.assertTrue(all(isinstance(item.on_enter(None), SetUserQueryAction)
                            for item in items))

    def test_results_are_limited(self):
        for argument in ("", "uuid", "token 64", "sha256 x", "qwerty", "u"):
            self.assertLessEqual(len(self.build(argument)), main.MAX_RESULTS)
        self.assertLessEqual(len(self.build("help")), main.MAX_HELP_RESULTS)

    def test_icons_exist(self):
        for item in self.build(""):
            self.assertTrue(os.path.exists(item._icon))  # pylint: disable=protected-access


@unittest.skipUnless(ULAUNCHER_AVAILABLE, "Ulauncher API is not installed")
class EventFlowTests(unittest.TestCase):
    """Drive the real listeners the way Ulauncher does."""

    def setUp(self):
        self.extension = FakeExtension({"kw": "gen"})
        self.extension.cache = main.ValueCache()
        self.query_listener = main.KeywordQueryEventListener()
        self.enter_listener = main.ItemEnterEventListener()

    def query(self, text, extension=None):
        action = self.query_listener.on_event(
            KeywordQueryEvent(Query(text)), extension or self.extension)
        self.assertIsInstance(action, RenderResultListAction)
        return action.result_list

    def test_query_event_returns_results(self):
        items = self.query("gen token 40")
        self.assertEqual(len(items[0].on_enter(None).text), 40)

    def test_custom_action_regenerates_the_list(self):
        first = self.query("gen token 40")[0].on_enter(None).text
        action = self.enter_listener.on_event(
            ItemEnterEvent(pickle.dumps({"argument": "token 40"})), self.extension)
        self.assertIsInstance(action, RenderResultListAction)
        self.assertNotEqual(action.result_list[0].on_enter(None).text, first)

    def test_custom_action_without_argument_shows_overview(self):
        action = self.enter_listener.on_event(
            ItemEnterEvent(pickle.dumps({})), self.extension)
        self.assertEqual(len(action.result_list), 5)

    def test_unexpected_errors_are_reported_instead_of_crashing(self):
        class BrokenCache(object):
            def get_or_create(self, key, factory):
                raise RuntimeError("boom")

            def invalidate_all(self):
                pass

        extension = FakeExtension({"kw": "gen"})
        extension.cache = BrokenCache()
        with self.assertLogs(main.logger, level="ERROR"):
            items = self.query("gen token 40", extension)
        self.assertEqual(items[0].get_name(), "Token generator error")


@unittest.skipUnless(ULAUNCHER_AVAILABLE, "Ulauncher API is not installed")
class SettingsTests(unittest.TestCase):

    def test_defaults_when_preferences_are_missing(self):
        settings = main.read_settings(FakeExtension())
        self.assertEqual(settings, main.token_specs.DEFAULT_SETTINGS)
        self.assertEqual(main.read_keyword(FakeExtension()), "gen")

    def test_valid_preferences_are_applied(self):
        extension = FakeExtension({
            "kw": "tok",
            "default_length": "64",
            "pin_length": "9",
            "password_symbols": "no",
            "hash_algorithm": "sha512",
        })
        settings = main.read_settings(extension)
        self.assertEqual(settings.default_length, 64)
        self.assertEqual(settings.pin_length, 9)
        self.assertFalse(settings.password_symbols)
        self.assertEqual(settings.hash_algorithm, "sha512")
        self.assertEqual(main.read_keyword(extension), "tok")

    def test_invalid_preferences_fall_back_to_defaults(self):
        extension = FakeExtension({
            "default_length": "not a number",
            "pin_length": "999",
            "password_symbols": "maybe",
            "hash_algorithm": "crc32",
        })
        with self.assertLogs(main.logger, level="WARNING"):
            settings = main.read_settings(extension)
        self.assertEqual(settings, main.token_specs.DEFAULT_SETTINGS)


@unittest.skipUnless(ULAUNCHER_AVAILABLE, "Ulauncher API is not installed")
class ValueCacheTests(unittest.TestCase):

    def test_cache_returns_the_same_value(self):
        cache = main.ValueCache()
        self.assertEqual(cache.get_or_create("k", lambda: "value"), "value")
        self.assertEqual(cache.get_or_create("k", lambda: "other"), "value")

    def test_cache_evicts_old_entries(self):
        cache = main.ValueCache(max_entries=2)
        cache.get_or_create("a", lambda: 1)
        cache.get_or_create("b", lambda: 2)
        cache.get_or_create("c", lambda: 3)
        self.assertEqual(list(cache._values), ["b", "c"])  # pylint: disable=protected-access

    def test_invalidate_all_clears_cache(self):
        cache = main.ValueCache()
        cache.get_or_create("a", lambda: 1)
        cache.invalidate_all()
        self.assertEqual(list(cache._values), [])  # pylint: disable=protected-access

    def test_refresh_once_only_triggers_the_first_time(self):
        cache = main.ValueCache()
        self.assertTrue(cache.refresh_once("marker"))
        self.assertFalse(cache.refresh_once("marker"))
        self.assertTrue(cache.refresh_once("other"))


@unittest.skipUnless(ULAUNCHER_AVAILABLE, "Ulauncher API is not installed")
class RefreshFlagTests(unittest.TestCase):

    def setUp(self):
        self.extension = FakeExtension({"kw": "gen"})
        self.extension.cache = main.ValueCache()
        self.listener = main.KeywordQueryEventListener()

    def render(self, text):
        action = self.listener.on_event(
            KeywordQueryEvent(Query(text)), self.extension)
        return action.result_list

    def test_refresh_flag_invalidates_the_value_once(self):
        first = self.render("gen token 32")[0].on_enter(None).text
        refreshed = self.render("gen token 32 -r")[0].on_enter(None).text
        self.assertNotEqual(first, refreshed)
        self.assertEqual(self.render("gen token 32 -r")[0].on_enter(None).text, refreshed)


if __name__ == "__main__":
    unittest.main()
