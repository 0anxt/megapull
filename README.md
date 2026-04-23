# megapull - Async Parallel MEGA.nz Downloader

**v0.2.0** — parallel chunked downloads from MEGA.nz public links without an account.

## Why

MEGAbasterd is Java/Swing — heavy, no headless support, no async. `megapull` uses `httpx` + `asyncio` + `cryptography` (OpenSSL AES-NI) for higher throughput, with proxy rotation, resume, folder enumeration, and chunk MAC verification.

## Features

- **Async chunked Range downloads** via HTTP/2
- **AES-128-CTR decryption** (MEGA CDN protocol, no account needed)
- **File + folder link support** (legacy + new format)
- **Proxy pool** with per-proxy scoring, auto-ejection, exponential backoff
- **Resume** via sidecar `.megapull.json`
- **Chunk MAC verification** (optional, log-only by default)
- **TUI progress** via `rich`
- **Fresh `g`-URL rotation** on 403/509
- **Typed error taxonomy** with distinct exit codes

## Install

```bash
pip install httpx[http2] cryptography rich
# or for SOCKS5 proxy support:
pip install "httpx[socks]" cryptography rich
```

## Usage

```bash
# single file
python -m megapull.cli "https://mega.nz/file/XXXXXXX#YYYYYYYYYY" -o /dest

# folder
python -m megapull.cli "https://mega.nz/folder/vkB30B5K#2ayjn2j2Y" -o /dest -w 8

# single file within a folder
python -m megapull.cli "https://mega.nz/folder/XXX#YYY/file/ZZZ" -o /dest

# with proxies
python -m megapull.cli "<link>" -o /dest --proxies proxies.txt

# force all traffic through proxies (bypass free quota)
python -m megapull.cli "<link>" -o /dest --proxies proxies.txt --force-proxy

# enable MAC verification (log warning on mismatch)
python -m megapull.cli "<link>" -o /dest --verify-mac

# strict MAC (abort on mismatch)
python -m megapull.cli "<link>" -o /dest --verify-mac --strict-mac
```

## Exit Codes

| Code | Meaning |
|------|---------|
| 0 | OK |
| 1 | Generic error |
| 2 | Permanent MEGA error (bad link/key/access) |
| 3 | Retriable exhausted |
| 4 | Quota exceeded (need proxy or wait) |
| 5 | Malformed link |

## Architecture

```
megapull/
├── api.py       # MEGA JSON-RPC client (file + folder session)
├── cli.py       # entrypoint + exit codes
├── crypto.py    # AES-CTR/ECB/CBC, key derivation, MAC
├── download.py  # async chunked downloader
├── errors.py    # error taxonomy + exit codes
├── folder.py    # folder enumeration + path building
├── links.py     # link parser (file + folder, legacy + new)
├── proxy.py     # proxy pool + scoring
├── state.py     # resume sidecar
└── __init__.py
```

## Links

- Repository: https://github.com/0anxt/megapull
- Based on MEGAbasterd design (tonikelope/megabasterd)
- MEGA protocol reconstructed from GadgetReactor/mega.py + odwyersoftware/mega.py
