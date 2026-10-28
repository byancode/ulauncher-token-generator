"""Token & UUID Generator — a Ulauncher extension.

Entry point: builds the result list and handles the "regenerate" action.
Generation itself lives in :mod:`generators`, query parsing in
:mod:`token_specs`; both are free of Ulauncher imports so they stay testable.
"""

import logging
import os
from collections import OrderedDict
from threading import Lock

from ulauncher.api.client.EventListener import EventListener
from ulauncher.api.client.Extension import Extension
from ulauncher.api.shared.action.CopyToClipboardAction import CopyToClipboardAction
from ulauncher.api.shared.action.DoNothingAction import DoNothingAction
from ulauncher.api.shared.action.ExtensionCustomAction import ExtensionCustomAction
from ulauncher.api.shared.action.RenderResultListAction import RenderResultListAction
from ulauncher.api.shared.action.SetUserQueryAction import SetUserQueryAction
from ulauncher.api.shared.event import ItemEnterEvent, KeywordQueryEvent
from ulauncher.api.shared.item.ExtensionResultItem import ExtensionResultItem

import generators
import token_specs

logger = logging.getLogger(__name__)

MAX_RESULTS = 9
# The help list is allowed to scroll a little instead of being truncated.
MAX_HELP_RESULTS = 12
DEFAULT_KEYWORD = "gen"

ICON_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "images")
FALLBACK_ICON = os.path.join(ICON_DIR, "token.png")

OVERVIEW_MODES = ("uuid4", "token", "password", "pin")
# Commands offered right below the requested one.
VARIANT_MODES = {
    "uuid4": ("uuid7", "ulid"),
    "uuid7": ("uuid4", "ulid"),
    "ulid": ("uuid7", "uuid4"),
    "token": ("hex", "password"),
    "hex": ("token",),
    "pin": ("password",),
    "password": ("token",),
    "base64": ("token",),
    "apikey": ("token",),
}
HASH_VARIANTS = ("sha1", "md5", "sha512")


def icon_path(filename):
    """Absolute icon path, falling back to a single known-good icon."""
    path = filename if os.path.isabs(filename) else os.path.join(ICON_DIR, filename)
    return path if os.path.exists(path) else FALLBACK_ICON


class ValueCache(object):
    """Keeps generated values stable while the user keeps typing.

    Without this the token would change on every keystroke. "Regenerate"
    invalidates the whole cache, which is cheap and always consistent.
    """

    def __init__(self, max_entries=256, max_refreshes=64):
        self._values = OrderedDict()
        self._refreshed = OrderedDict()
        self._max_entries = max_entries
        self._max_refreshes = max_refreshes
        self._lock = Lock()

    def get_or_create(self, key, factory):
        with self._lock:
            if key in self._values:
                self._values.move_to_end(key)
                return self._values[key]

        value = factory()

        with self._lock:
            self._values[key] = value
            self._values.move_to_end(key)
            while len(self._values) > self._max_entries:
                self._values.popitem(last=False)
        return value

    def invalidate_all(self):
        with self._lock:
            self._values.clear()

    def refresh_once(self, marker):
        """Invalidate cached values the first time a query asks for it.

        Typing ``-r`` must not regenerate the value on every re-render, so the
        refresh only happens once per distinct query.
        """
        with self._lock:
            if marker in self._refreshed:
                return False
            self._refreshed[marker] = True
            self._refreshed.move_to_end(marker)
            while len(self._refreshed) > self._max_refreshes:
                self._refreshed.popitem(last=False)
            self._values.clear()
            return True


def read_settings(extension):
    prefs = getattr(extension, "preferences", None) or {}
    return token_specs.Settings(
        default_length=_int_pref(
            prefs, "default_length", token_specs.DEFAULT_TOKEN_LENGTH,
            token_specs.MIN_TOKEN_LENGTH, token_specs.MAX_TOKEN_LENGTH),
        pin_length=_int_pref(
            prefs, "pin_length", token_specs.DEFAULT_PIN_LENGTH,
            token_specs.MIN_PIN_LENGTH, token_specs.MAX_PIN_LENGTH),
        password_symbols=_bool_pref(prefs, "password_symbols", True),
        hash_algorithm=_hash_pref(prefs, "hash_algorithm", "sha256"),
    )


def read_keyword(extension):
    prefs = getattr(extension, "preferences", None) or {}
    return str(prefs.get("kw") or DEFAULT_KEYWORD).strip() or DEFAULT_KEYWORD


def _int_pref(prefs, name, default, minimum, maximum):
    try:
        value = int(str(prefs.get(name, "")).strip())
    except (TypeError, ValueError):
        return default
    if value < minimum or value > maximum:
        logger.warning(
            "Preference '%s' must be between %d and %d, using %d",
            name, minimum, maximum, default)
        return default
    return value


def _bool_pref(prefs, name, default):
    value = str(prefs.get(name, "")).strip().lower()
    if value in ("1", "true", "yes", "on", "y"):
        return True
    if value in ("0", "false", "no", "off", "n"):
        return False
    return default


def _hash_pref(prefs, name, default):
    value = str(prefs.get(name, "")).strip().lower()
    return value if value in generators.HASH_ALGORITHMS else default


def build_items(request, settings, keyword, cache):
    """Render a :class:`token_specs.Request` into Ulauncher result items."""
    if request.mode == "overview":
        return _overview_items(settings, keyword, cache)
    if request.mode == "help":
        return _help_items(keyword)
    if request.error:
        return _error_items(request, keyword)

    items = [_value_item(request, cache, selected=True)]
    for variant in _variants(request, settings):
        items.append(_value_item(variant, cache))

    if request.mode != "hash":
        items.append(_regenerate_item(request))
    return items[:MAX_RESULTS]


def _variants(request, settings):
    if request.mode == "hash":
        algorithm = request.algorithm or "sha256"
        return [
            token_specs.resolve(
                "hash", settings, payload=request.payload, algorithm=other,
                argument=request.argument)
            for other in HASH_VARIANTS if other != algorithm
        ]

    variants = []
    for mode_key in VARIANT_MODES.get(request.mode, ()):
        mode = token_specs.MODES[mode_key]
        length = request.length
        if mode.length_kind and length is not None:
            length = max(mode.min_length, min(length, mode.max_length))
        variant = token_specs.resolve(mode_key, settings, length=length, argument=request.argument)
        if not variant.error:
            variants.append(variant)
    return variants


def _value_item(request, cache, selected=False):
    value = _value_for(request, cache)
    if request.mode == "hash":
        # Ulauncher closes the window when Alt+Enter returns no action.
        alt_action = CopyToClipboardAction(value)
    else:
        alt_action = _regenerate_action(request)
    return ExtensionResultItem(
        icon=icon_path(token_specs.MODES[request.mode].icon),
        name=_name_for(request),
        description=_description_for(request, value),
        on_enter=CopyToClipboardAction(value),
        on_alt_enter=alt_action,
        selected_by_default=selected,
        highlightable=False,
    )


def _regenerate_action(request):
    return ExtensionCustomAction({"argument": request.argument}, keep_app_open=True)


def _simple_item(icon, name, description, action, highlightable=False):
    """Item without a value to copy.

    ``on_alt_enter`` is set as well because Ulauncher closes the window when
    Alt+Enter yields no action.
    """
    return ExtensionResultItem(
        icon=icon_path(icon),
        name=name,
        description=description,
        on_enter=action,
        on_alt_enter=action,
        highlightable=highlightable,
    )


def _regenerate_item(request):
    return _simple_item(
        "token.png",
        "Regenerate",
        "Alt+Enter on a value copies it and generates a new one",
        _regenerate_action(request),
    )


def _value_for(request, cache):
    if request.mode == "hash":
        return generators.hash_text(request.payload, request.algorithm or "sha256")
    return cache.get_or_create(_cache_key(request), lambda: _generate(request))


def _cache_key(request):
    return "|".join(str(part) for part in (
        request.mode, request.length, request.payload,
        request.algorithm, request.symbols, request.exclude_ambiguous,
    ))


def _generate(request):
    mode = request.mode
    if mode == "uuid4":
        return generators.uuid4_str()
    if mode == "uuid7":
        return generators.uuid7_str()
    if mode == "ulid":
        return generators.ulid_str()
    if mode == "token":
        return generators.url_safe_token(request.length, bool(request.exclude_ambiguous))
    if mode == "hex":
        return generators.hex_token(request.length)
    if mode == "pin":
        return generators.numeric_code(request.length)
    if mode == "password":
        symbols = True if request.symbols is None else bool(request.symbols)
        return generators.password(
            request.length, symbols=symbols, exclude_ambiguous=bool(request.exclude_ambiguous))
    if mode == "base64":
        return generators.base64_token(request.length)
    if mode == "apikey":
        return generators.api_key(
            request.length, request.payload or token_specs.DEFAULT_API_KEY_PREFIX)
    if mode == "hash":
        return generators.hash_text(request.payload, request.algorithm or "sha256")
    raise ValueError("unsupported mode: %s" % mode)


def _name_for(request):
    mode = token_specs.MODES[request.mode]
    if request.mode in ("uuid4", "uuid7", "ulid"):
        return mode.label
    if request.mode == "hash":
        return "%s hash" % _algorithm_label(request.algorithm)
    if request.mode == "apikey":
        return "%s (%s...)" % (mode.label, request.payload)
    if request.mode == "base64":
        return "%s (%d bytes)" % (mode.label, request.length)
    unit = "digits" if request.mode == "pin" else "chars"
    return "%s (%d %s)" % (mode.label, request.length, unit)


def _algorithm_label(algorithm):
    algorithm = algorithm or "sha256"
    if algorithm.startswith("sha") and algorithm[3:].isdigit():
        return "SHA-%s" % algorithm[3:]
    return algorithm.upper()


def _format_bits(bits):
    return "%d" % bits if float(bits).is_integer() else "%s" % bits


def _alphabet_size(request):
    excluded = len(generators.AMBIGUOUS_CHARS) if request.exclude_ambiguous else 0
    if request.mode in ("token", "apikey"):
        return len(generators.URL_SAFE) - excluded
    if request.mode == "hex":
        return len(generators.HEX_CHARS)
    if request.mode == "pin":
        return len(generators.DIGITS)
    if request.mode == "password":
        size = len(generators.ALPHANUMERIC)
        if request.symbols:
            size += len(generators.SYMBOLS)
        return size - excluded
    if request.mode == "base64":
        return 64
    return 0


def _description_for(request, value):
    if request.mode == "uuid4":
        detail = "RFC 4122 random UUID, 122 bits"
    elif request.mode == "uuid7":
        detail = "RFC 9562, time-ordered and sortable"
    elif request.mode == "ulid":
        detail = "Crockford base32, sortable, 80 random bits"
    elif request.mode == "base64":
        detail = "%d random bytes, %d chars" % (request.length, len(value))
    elif request.mode == "hash":
        detail = "%s of \"%s\"" % (
            _algorithm_label(request.algorithm), _shorten(request.payload))
    else:
        bits = generators.entropy_bits(_alphabet_size(request), request.length)
        unit = "digits" if request.mode == "pin" else "chars"
        detail = "%d %s, ~%s bits" % (request.length, unit, _format_bits(bits))
        if request.mode == "password":
            detail += ", symbols" if request.symbols else ", no symbols"
        if request.exclude_ambiguous:
            detail += ", no look-alikes"
    return "%s  ·  %s" % (value, detail)


def _shorten(text, limit=40):
    text = " ".join(str(text).split())
    return text if len(text) <= limit else text[:limit - 1] + "..."


def _overview_items(settings, keyword, cache):
    items = [
        _value_item(token_specs.resolve(mode_key, settings), cache, selected=index == 0)
        for index, mode_key in enumerate(OVERVIEW_MODES)
    ]
    items.append(_simple_item(
        "token.png",
        "All commands",
        "uuid, uuid7, ulid, token, hex, password, pin, base64, apikey, hash",
        SetUserQueryAction("%s help" % keyword),
    ))
    return items[:MAX_RESULTS]


def _help_items(keyword):
    items = []
    for mode in token_specs.MODES.values():
        command = "%s %s" % (keyword, mode.example)
        items.append(_simple_item(
            mode.icon, command, mode.description, SetUserQueryAction(command), highlightable=True))
    items.append(_simple_item(
        "key.png",
        "Options",
        "-n <len> length | -s symbols | -p no symbols | -c no look-alikes | -r refresh",
        SetUserQueryAction("%s help" % keyword),
    ))
    return items[:MAX_HELP_RESULTS]


def _error_items(request, keyword):
    if request.mode in token_specs.MODES:
        target = "%s %s" % (keyword, token_specs.MODES[request.mode].example)
        description = "Enter to try '%s'" % target
    else:
        target = "%s help" % keyword
        description = "Enter to see every command"
    items = [_simple_item("key.png", request.error, description, SetUserQueryAction(target))]
    for suggestion in request.suggestions[:MAX_RESULTS - 1]:
        command = "%s %s" % (keyword, suggestion)
        if command == target:
            continue
        items.append(_simple_item(
            token_specs.MODES["token"].icon, command, "Enter to use this command",
            SetUserQueryAction(command)))
    return items


def _render(argument, extension):
    settings = read_settings(extension)
    keyword = read_keyword(extension)
    request = token_specs.parse(argument, settings)
    if request.refresh:
        extension.cache.refresh_once(_cache_key(request))
    return RenderResultListAction(build_items(request, settings, keyword, extension.cache))


def _error_response(error):
    return RenderResultListAction([_simple_item(
        "key.png", "Token generator error", _shorten(error, 120), DoNothingAction())])


class KeywordQueryEventListener(EventListener):
    # pylint: disable=unused-argument
    def on_event(self, event, extension):
        try:
            return _render(event.get_argument(), extension)
        except Exception as error:  # pylint: disable=broad-except
            logger.exception("Failed to render results")
            return _error_response(error)


class ItemEnterEventListener(EventListener):
    # pylint: disable=unused-argument
    def on_event(self, event, extension):
        try:
            data = event.get_data()
            argument = data.get("argument", "") if isinstance(data, dict) else ""
            extension.cache.invalidate_all()
            return _render(argument, extension)
        except Exception as error:  # pylint: disable=broad-except
            logger.exception("Failed to regenerate values")
            return _error_response(error)


class TokenGenExtension(Extension):
    def __init__(self):
        super(TokenGenExtension, self).__init__()
        self.cache = ValueCache()
        self.subscribe(KeywordQueryEvent, KeywordQueryEventListener())
        self.subscribe(ItemEnterEvent, ItemEnterEventListener())


if __name__ == "__main__":
    TokenGenExtension().run()
