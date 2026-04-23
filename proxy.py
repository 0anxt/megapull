import time, random
from dataclasses import dataclass

@dataclass
class Proxy:
    url: str  # "http://user:pass@host:port" or "socks5://..."
    score: float = 1.0
    last_fail: float = 0.0
    in_use: int = 0

class ProxyPool:
    def __init__(self, proxies: list[str] | None):
        self.proxies = [Proxy(u) for u in (proxies or [])]
        self.enabled = bool(self.proxies)

    def pick(self) -> Proxy | None:
        if not self.enabled:
            return None
        now = time.time()
        cands = [p for p in self.proxies if now - p.last_fail > 30 and p.in_use < 4]
        if not cands:
            return None
        total = sum(p.score for p in cands)
        r = random.uniform(0, total)
        acc = 0
        for p in cands:
            acc += p.score
            if r <= acc:
                p.in_use += 1
                return p
        p = cands[-1]
        p.in_use += 1
        return p

    def release(self, p: Proxy | None, ok: bool, status: int | None = None):
        if p is None:
            return
        p.in_use = max(0, p.in_use - 1)
        if ok:
            p.score = min(2.0, p.score + 0.05)
        else:
            p.last_fail = time.time()
            p.score = max(0.05, p.score * 0.7)
        if status == 509:
            p.score *= 0.5