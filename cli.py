import argparse, asyncio, sys
from pathlib import Path
from download import Downloader
from errors import (
    PermanentMegaError, QuotaExceeded, RateLimited,
    EXIT_OK, EXIT_PERMANENT, EXIT_QUOTA, EXIT_RETRY_EXHAUST,
    EXIT_BAD_LINK, EXIT_GENERIC,
)

def main():
    ap = argparse.ArgumentParser("megapull")
    ap.add_argument("link", help="MEGA public file or folder link")
    ap.add_argument("-o", "--out", default=".", help="destination directory")
    ap.add_argument("-w", "--workers", type=int, default=8)
    ap.add_argument("--proxies", help="file with one proxy URL per line", default=None)
    ap.add_argument("--force-proxy", action="store_true")
    ap.add_argument("--verify-mac", action="store_true")
    ap.add_argument("--strict-mac", action="store_true")
    args = ap.parse_args()

    proxies = None
    if args.proxies:
        proxies = [
            l.strip() for l in Path(args.proxies).read_text().splitlines()
            if l.strip() and not l.startswith("#")
        ]

    dl = Downloader(
        args.link, Path(args.out),
        workers=args.workers,
        proxies=proxies,
        use_proxy_free_first=not args.force_proxy,
        verify_mac=args.verify_mac,
        strict_mac=args.strict_mac,
    )
    try:
        asyncio.run(dl.run())
        sys.exit(EXIT_OK)
    except ValueError as e:
        print(f"[bad-link] {e}", file=sys.stderr)
        sys.exit(EXIT_BAD_LINK)
    except PermanentMegaError as e:
        print(f"[permanent] {e}", file=sys.stderr)
        sys.exit(EXIT_PERMANENT)
    except QuotaExceeded as e:
        print(f"[quota] {e} — rotate proxies or wait", file=sys.stderr)
        sys.exit(EXIT_QUOTA)
    except RateLimited as e:
        print(f"[rate-limit] HTTP {e.status}", file=sys.stderr)
        sys.exit(EXIT_RETRY_EXHAUST)
    except Exception as e:
        print(f"[error] {type(e).__name__}: {e}", file=sys.stderr)
        sys.exit(EXIT_GENERIC)

if __name__ == "__main__":
    main()
