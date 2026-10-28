"""Parsing of the user query into a generation request.

Pure Python (no Ulauncher imports) so it can be unit tested on its own.

Grammar::

    <keyword> [options] [[<length>] <command> [<length>] [options] [<argument>]]

Examples::

    gen                 -> overview of the most useful generators
    gen 64              -> URL-safe token with 64 characters
    gen hex 48          -> hex token with 48 characters
    gen token -n 64 -c  -> 64 chars, no look-alike characters
    gen password 24 -s  -> 24 chars, symbols forced on
    gen sha256 hello    -> SHA-256 digest of "hello"
    gen apikey live     -> sk_-style key with the "live" prefix
"""

import difflib
import re
from collections import OrderedDict, namedtuple

from generators import HASH_ALGORITHMS

DEFAULT_TOKEN_LENGTH = 32
DEFAULT_PIN_LENGTH = 6
DEFAULT_PASSWORD_LENGTH = 20
DEFAULT_BASE64_BYTES = 24
DEFAULT_API_KEY_LENGTH = 32
DEFAULT_API_KEY_PREFIX = "sk_"

MIN_TOKEN_LENGTH, MAX_TOKEN_LENGTH = 1, 2048
MIN_PIN_LENGTH, MAX_PIN_LENGTH = 1, 64
MIN_PASSWORD_LENGTH, MAX_PASSWORD_LENGTH = 4, 256
MIN_BASE64_BYTES, MAX_BASE64_BYTES = 1, 1024
MIN_API_KEY_LENGTH, MAX_API_KEY_LENGTH = 8, 256

Settings = namedtuple("Settings", "default_length pin_length password_symbols hash_algorithm")
DEFAULT_SETTINGS = Settings(DEFAULT_TOKEN_LENGTH, DEFAULT_PIN_LENGTH, True, "sha256")

# length_kind: "chars" for textual lengths, "bytes" for raw byte counts,
# None for commands that take no length argument.
Mode = namedtuple("Mode", "key label icon example length_kind min_length max_length default_length description")

MODES = OrderedDict([
    ("uuid4", Mode("uuid4", "UUID v4", "uuid.png", "uuid", None, None, None, None,
                   "Random UUID v4 (RFC 4122)")),
    ("uuid7", Mode("uuid7", "UUID v7", "uuid.png", "uuid7", None, None, None, None,
                   "Time-ordered UUID v7 (RFC 9562)")),
    ("ulid", Mode("ulid", "ULID", "uuid.png", "ulid", None, None, None, None,
                  "Sortable 26-character ULID")),
    ("token", Mode("token", "URL-safe token", "link.png", "token 64", "chars",
                   MIN_TOKEN_LENGTH, MAX_TOKEN_LENGTH, None,
                   "Random URL-safe token")),
    ("hex", Mode("hex", "Hex token", "token.png", "hex 48", "chars",
                 MIN_TOKEN_LENGTH, MAX_TOKEN_LENGTH, None,
                 "Lowercase hexadecimal token")),
    ("pin", Mode("pin", "Numeric PIN", "number.png", "pin 6", "chars",
                 MIN_PIN_LENGTH, MAX_PIN_LENGTH, None,
                 "Numeric PIN / OTP code")),
    ("password", Mode("password", "Password", "key.png", "password 24", "chars",
                      MIN_PASSWORD_LENGTH, MAX_PASSWORD_LENGTH, DEFAULT_PASSWORD_LENGTH,
                      "Strong random password")),
    ("base64", Mode("base64", "Base64 token", "token.png", "base64 24", "bytes",
                    MIN_BASE64_BYTES, MAX_BASE64_BYTES, DEFAULT_BASE64_BYTES,
                    "URL-safe Base64 string")),
    ("apikey", Mode("apikey", "API key", "key.png", "apikey live", "chars",
                    MIN_API_KEY_LENGTH, MAX_API_KEY_LENGTH, DEFAULT_API_KEY_LENGTH,
                    "API key with a custom prefix")),
    ("hash", Mode("hash", "Hash", "token.png", "sha256 hello", None, None, None, None,
                  "Hash text with sha256, sha1, md5 or sha512")),
])

ALIASES = {
    "uuid": "uuid4",
    "uuid4": "uuid4",
    "uuidv4": "uuid4",
    "guid": "uuid4",
    "uuid7": "uuid7",
    "uuidv7": "uuid7",
    "ulid": "ulid",
    "sortable": "ulid",
    "token": "token",
    "tok": "token",
    "key": "token",
    "nanoid": "token",
    "url": "token",
    "urlsafe": "token",
    "hex": "hex",
    "pin": "pin",
    "otp": "pin",
    "code": "pin",
    "numeric": "pin",
    "digits": "pin",
    "password": "password",
    "pass": "password",
    "pw": "password",
    "pwd": "password",
    "base64": "base64",
    "b64": "base64",
    "apikey": "apikey",
    "api": "apikey",
    "secret": "apikey",
    "hash": "hash",
    "help": "help",
    "commands": "help",
    "?": "help",
}
ALIASES.update({algorithm: "hash" for algorithm in HASH_ALGORITHMS})

HELP_WORDS = {"help", "?", "commands"}

FLAG_REFRESH = {"-r", "--refresh", "refresh"}
FLAG_SYMBOLS = {"-s", "--symbols"}
FLAG_NO_SYMBOLS = {"-p", "--plain", "--no-symbols"}
FLAG_NO_AMBIGUOUS = {"-c", "--no-ambiguous", "--no-lookalikes"}
LENGTH_FLAGS = {"-n", "--length"}

_NUMERIC = re.compile(r"\d{1,5}\Z")
_PREFIX = re.compile(r"[A-Za-z0-9_.:\-]{1,24}\Z")


class Request(object):
    """A fully resolved generation request (or an error with suggestions)."""

    __slots__ = (
        "mode", "length", "payload", "algorithm", "symbols",
        "exclude_ambiguous", "refresh", "error", "suggestions", "argument",
    )

    def __init__(self, mode=None, length=None, payload="", algorithm=None, symbols=None,
                 exclude_ambiguous=None, refresh=False, error=None, suggestions=(),
                 argument=""):
        self.mode = mode
        self.length = length
        self.payload = payload
        self.algorithm = algorithm
        self.symbols = symbols
        self.exclude_ambiguous = exclude_ambiguous
        self.refresh = refresh
        self.error = error
        self.suggestions = tuple(suggestions)
        self.argument = argument

    def __repr__(self):
        return (
            "Request(mode=%r, length=%r, payload=%r, algorithm=%r, symbols=%r, "
            "exclude_ambiguous=%r, refresh=%r, error=%r)" % (
                self.mode, self.length, self.payload, self.algorithm, self.symbols,
                self.exclude_ambiguous, self.refresh, self.error,
            )
        )


def parse(argument, settings=DEFAULT_SETTINGS):
    """Turn the raw text typed after the keyword into a :class:`Request`."""
    argument = (argument or "").strip()
    if not argument:
        return Request(mode="overview", argument="")

    tokens = _tokenize(argument)
    if not tokens:
        return Request(mode="overview", argument=argument)

    modifiers = _Modifiers()
    mode_word = None
    remainder = []

    index = 0
    while index < len(tokens):
        token = tokens[index]
        try:
            consumed = modifiers.consume(tokens, index)
        except _BadLength as error:
            return Request(error=str(error), suggestions=["-n 64"], argument=argument)
        if consumed:
            index += consumed
            continue
        if _NUMERIC.match(token):
            modifiers.length = modifiers.length if modifiers.length is not None else int(token)
            index += 1
            continue
        if token.startswith("-") and len(token) > 1:
            return Request(
                error="Unknown option '%s'" % token,
                suggestions=["token", "help"],
                argument=argument,
            )
        mode_word = token
        remainder = tokens[index + 1:]
        break

    if mode_word is None:
        if modifiers.length is None:
            return Request(mode="overview", refresh=modifiers.refresh, argument=argument)
        mode_key = "token"
        algorithm = None
    else:
        mode_key = ALIASES.get(mode_word.lower())
        if mode_key == "help":
            return Request(mode="help", argument=argument)
        if mode_key is None:
            mode_key, error, suggestions = _resolve_mode(mode_word)
            if error:
                return Request(error=error, suggestions=suggestions, argument=argument)
        algorithm = mode_word.lower() if mode_word.lower() in HASH_ALGORITHMS else None

    if mode_key == "hash":
        # Everything after the command is text to hash, options included.
        payload = " ".join(remainder).strip()
    else:
        payload_tokens, error = modifiers.consume_payload(remainder, MODES[mode_key])
        if error:
            return Request(mode=mode_key, error=error, argument=argument)
        payload = " ".join(payload_tokens).strip()

    return resolve(
        mode_key,
        settings,
        length=modifiers.length,
        payload=payload,
        algorithm=algorithm,
        symbols=modifiers.symbols,
        exclude_ambiguous=modifiers.exclude_ambiguous,
        refresh=modifiers.refresh,
        argument=argument,
    )


def resolve(mode_key, settings=DEFAULT_SETTINGS, length=None, payload="", algorithm=None,
            symbols=None, exclude_ambiguous=None, refresh=False, argument=""):
    """Fill in defaults and validate a request for ``mode_key``."""
    if mode_key not in MODES:
        return Request(error="Unknown command '%s'" % mode_key, argument=argument, refresh=refresh)

    mode = MODES[mode_key]

    if mode.length_kind is None:
        length = None
    else:
        if length is None:
            length = _default_length(mode, settings)
        if length < mode.min_length or length > mode.max_length:
            return Request(
                mode=mode_key,
                error="%s length must be between %d and %d" % (
                    mode.label, mode.min_length, mode.max_length),
                suggestions=[mode.example],
                argument=argument,
                refresh=refresh,
            )

    if mode_key == "hash":
        payload = payload.strip()
        if not payload:
            return Request(
                mode="hash",
                algorithm=algorithm or settings.hash_algorithm,
                error="Type the text to hash, e.g. 'sha256 hello'",
                suggestions=[MODES["hash"].example],
                argument=argument,
                refresh=refresh,
            )
        algorithm = (algorithm or settings.hash_algorithm).lower()
        if algorithm not in HASH_ALGORITHMS:
            algorithm = "sha256"
    elif mode_key == "apikey":
        payload = payload.strip()
        if payload and not _PREFIX.match(payload):
            return Request(
                mode=mode_key,
                error="Prefix must be 1-24 characters: letters, digits, _ . : -",
                suggestions=[MODES["apikey"].example],
                argument=argument,
                refresh=refresh,
            )
        payload = payload or DEFAULT_API_KEY_PREFIX
        if payload[-1].isalnum():
            # "gen apikey live" -> live_xxxx instead of livexxxx
            payload += "_"

    if symbols is None and mode_key == "password":
        symbols = settings.password_symbols

    return Request(
        mode=mode_key,
        length=length,
        payload=payload,
        algorithm=algorithm,
        symbols=symbols,
        exclude_ambiguous=exclude_ambiguous,
        refresh=refresh,
        argument=argument,
    )


def _default_length(mode, settings):
    if mode.key in ("token", "hex"):
        return settings.default_length
    if mode.key == "pin":
        return settings.pin_length
    return mode.default_length


def _tokenize(argument):
    tokens = argument.split()
    # shlex would also strip quotes; only use it when it cannot hurt.
    if '"' in argument or "'" in argument:
        import shlex

        try:
            return shlex.split(argument)
        except ValueError:
            return tokens
    return tokens


def _resolve_mode(word):
    lowered = word.lower()
    matches = sorted({ALIASES[alias] for alias in ALIASES if alias.startswith(lowered)})
    if len(matches) == 1:
        return matches[0], None, ()
    if len(matches) > 1:
        return (
            None,
            "'%s' matches several commands" % word,
            [MODES[match].example.split(" ")[0] for match in matches],
        )

    close = difflib.get_close_matches(lowered, list(ALIASES), n=3, cutoff=0.5)
    suggestions = []
    for alias in close:
        example = MODES[ALIASES[alias]].example
        if example not in suggestions:
            suggestions.append(example)
    return None, "Unknown command '%s'" % word, suggestions


class _Modifiers(object):
    """Options accepted before and after the command word."""

    def __init__(self):
        self.length = None
        self.symbols = None
        self.exclude_ambiguous = None
        self.refresh = False

    def consume(self, tokens, index):
        """Apply the option at ``index``; return how many tokens were consumed."""
        token = tokens[index].lower()
        if token in FLAG_REFRESH:
            self.refresh = True
        elif token in FLAG_SYMBOLS:
            self.symbols = True
        elif token in FLAG_NO_SYMBOLS:
            self.symbols = False
        elif token in FLAG_NO_AMBIGUOUS:
            self.exclude_ambiguous = True
        elif token in LENGTH_FLAGS:
            if index + 1 < len(tokens) and _NUMERIC.match(tokens[index + 1]):
                self.length = int(tokens[index + 1])
                return 2
            raise _BadLength("'%s' needs a number" % tokens[index])
        else:
            return 0
        return 1

    def consume_payload(self, tokens, mode):
        """Split the tokens after the command into (payload, error)."""
        payload = []
        index = 0
        while index < len(tokens):
            token = tokens[index]
            try:
                consumed = self.consume(tokens, index)
            except _BadLength as error:
                return payload, str(error)
            if consumed:
                index += consumed
                continue
            if _NUMERIC.match(token) and mode.length_kind and self.length is None:
                self.length = int(token)
            else:
                payload.append(token)
            index += 1
        return payload, None


class _BadLength(Exception):
    pass
