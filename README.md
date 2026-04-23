# megapull - Improved Async MEGA.nz Downloader

Parallel chunked downloads from MEGA.nz public links without an account.

**Why:** MEGAbasterd is Java/Swing — heavy, no headless support, no async. `megapull` uses `httpx` + `asyncio` + `cryptography` (OpenSSL AES-NI) for 4-8× throughput on the same core, with proxy rotation, resume, and a clean CLI/TUI.

## Features

- Async chunked downloads via HTTP/2 Range requests
- AES-128-CTR decryption (MEGA's CDN protocol)
- Proxy pool with per-proxy scoring, auto-ejection, backoff
- Resume via sidecar `.megapull.json` (survives process restart)
- TUI progress bar (`rich`)
- Folder link support
- Fresh `g`-URL rotation on 403/509

## Install

```bash
pip install httpx[http2] cryptography rich
```

## Usage

```bash
python -m megapull.cli "https://mega.nz/file/XXXXXXX#YYYYYYYYYY" -o /dest -w 8

# with proxies
python -m megapull.cli "<link>" -o /dest --proxies proxies.txt

# force all traffic through proxies (bypass free quota entirely)
python -m megapull.cli "<link>" -o /dest --proxies proxies.txt --force-proxy
```

## Protocol Notes

MEGA's public API is undocumented. The anonymous download flow (`a=g`) is reverse-engineered from community libraries (mega.py, MEGAbasterd source). No account required.

Free unauthenticated IP quota is ~5 GB before hitting 509 (community-reported, not officially documented).

## Project Structure

```
megapull/
├── crypto.py    # AES-CTR, key derivation, attr decryption
├── api.py       # MEGA JSON-RPC client
├── download.py  # async chunked downloader + resume
├── proxy.py     # proxy pool + scoring
├── state.py     # sidecar resume file
├── cli.py       # entrypoint
└── __init__.py
```

## Status

Functional but MAC verification is optional (not implemented yet). See galaxy.ai chat for full design doc.

## License

GPL-3.0 (same as MEGAbasterd)