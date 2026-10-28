# Token & UUID Generator for Ulauncher

Generate secure tokens, passwords, UUIDs, ULIDs and hashes straight from
[Ulauncher](https://ulauncher.io/) — type a keyword, press Enter, the value is
in your clipboard.

## Features

- **Cryptographically secure** — everything is generated with `secrets`
  (`os.urandom`), never with the `random` Mersenne Twister.
- **Stable values** — the generated value does not change while you keep
  typing. Use *Regenerate* (or `Alt+Enter`) to get a new one.
- **Exact lengths** — ask for 64 characters and you get exactly 64 characters.
- **Entropy shown** — every result reports its approximate strength in bits.
- **Command palette** — `gen help` lists every command; every entry can be
  selected to fill in the query.
- **Friendly errors** — unknown commands suggest the closest match instead of
  failing silently.

## Commands

| Command | Result |
| --- | --- |
| `gen` | Overview: UUID v4, token, password and PIN |
| `gen uuid` / `gen uuid4` | Random UUID v4 (RFC 4122) |
| `gen uuid7` | Time-ordered UUID v7 (RFC 9562) |
| `gen ulid` | Sortable 26-character ULID |
| `gen token [len]` | URL-safe random token (default 32) |
| `gen hex [len]` | Lowercase hexadecimal token |
| `gen pin [len]` | Numeric PIN / OTP code |
| `gen password [len]` | Password with lower, upper, digit and symbol classes |
| `gen base64 [bytes]` | URL-safe Base64 string without padding |
| `gen apikey [prefix]` | API key such as `sk_9f3c…` or `live_9f3c…` |
| `gen sha256 <text>` | SHA-256 digest (also `sha1`, `md5`, `sha512`) |
| `gen 64` | Shorthand for `gen token 64` |
| `gen help` | List all commands |

### Options

Options can be placed before or after the command:

| Option | Meaning |
| --- | --- |
| `-n <len>`, `--length <len>` | Explicit length |
| `-s`, `--symbols` | Force symbols on (passwords) |
| `-p`, `--plain` | Letters and digits only |
| `-c`, `--no-ambiguous` | Skip look-alike characters (`Il1O0o`) |
| `-r`, `--refresh` | Discard the cached value and generate a new one |

Examples:

```
gen password 24 -s        # 24 characters with symbols
gen token -n 64 -c        # 64 characters without look-alikes
gen apikey live           # live_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
gen sha256 hello world    # b94d27b9…
```

## Keyboard shortcuts

- **Enter** — copy the value and close Ulauncher.
- **Alt+Enter** — copy the value and regenerate the list.
- Selecting *Regenerate* regenerates the list without copying.

## Preferences

| Preference | Default | Description |
| --- | --- | --- |
| Keyword | `gen` | Keyword used to trigger the extension |
| Default token length | `32` | Length used by `token` and `hex` |
| Default PIN length | `6` | Digits used by `pin` |
| Password symbols | `yes` | Include symbols in passwords |
| Default hash algorithm | `sha256` | Algorithm used by `hash` |

Invalid preference values are ignored and fall back to the defaults instead of
breaking the extension.

## Installation

### From the Ulauncher extension index

Search for *Token & UUID Generator* in Ulauncher → Preferences → Extensions.

### From source

```bash
git clone https://github.com/byancode/ulauncher-token-generator.git \
  ~/.local/share/ulauncher/extensions/com.github.byancode.ulauncher-token-generator
```

Restart Ulauncher afterwards.

## Development

The code base is split so the interesting parts can be tested without a running
Ulauncher:

| File | Purpose |
| --- | --- |
| `main.py` | Ulauncher wiring: builds result items, handles actions |
| `token_specs.py` | Query parsing (`gen token 64 -c` → request) |
| `generators.py` | Secure value generation (no Ulauncher imports) |
| `tests/` | `unittest` suite |

Run the tests:

```bash
python3 -m unittest discover -s tests -v
```

Requires Python 3.8+ (Ulauncher 5 API `2.0.0`).

> The extension installed in `~/.local/share/ulauncher/extensions/` is a
> separate clone. Copy or symlink this directory there (and restart Ulauncher)
> to try local changes.
