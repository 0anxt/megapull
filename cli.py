import argparse, asyncio, sys
from pathlib import Path
from .download import Downloader

def main():
    ap = argparse.ArgumentParser("megapull")
    ap.add_argument("link", help="MEGA public file link")
    ap.add_argument("-o", "--out", default=".", help="destination directory")
    ap.add_argument("-w", "--workers", type=int, default=8)
    ap.add_argument("--proxies", help="file with one proxy URL per line", default=None)
    ap.add_argument("--force-proxy", action="store_true",
                    help="route all traffic through proxies from the start")
    args = ap.parse_args()

    proxies = None
    if args.proxies:
        proxies = [l.strip() for l in Path(args.proxies).read_text().splitlines()
                   if l.strip() and not l.startswith("#")]

    dl = Downloader(args.link, Path(args.out), workers=args.workers,
                    proxies=proxies, use_proxy_free_first=not args.force_proxy)
    out = asyncio.run(dl.run())
    print(f"[done] {out}", file=sys.stderr)

if __name__ == "__main__":
    main()