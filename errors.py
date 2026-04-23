# MEGA application-layer error codes (negative ints returned in JSON body).
# Source: reverse-engineered; not officially documented by MEGA.
MEGA_ERRORS = {
    -1: ("EINTERNAL", "internal error", True),
    -2: ("EARGS", "bad arguments", False),
    -3: ("EAGAIN", "try again", True),
    -4: ("ERATELIMIT", "rate limited", True),
    -5: ("EFAILED", "upload failed", True),
    -6: ("ETOOMANY", "too many concurrent", True),
    -7: ("ERANGE", "out of range", False),
    -8: ("EEXPIRED", "resource expired", True),
    -9: ("ENOENT", "not found", False),
    -10: ("ECIRCULAR", "circular link", False),
    -11: ("EACCESS", "access denied", False),
    -12: ("EEXIST", "already exists", False),
    -13: ("EINCOMPLETE", "incomplete", True),
    -14: ("EKEY", "bad crypto key", False),
    -15: ("ESID", "bad session id", False),
    -16: ("EBLOCKED", "resource blocked", False),
    -17: ("EOVERQUOTA", "quota exceeded", True),
    -18: ("ETEMPUNAVAIL", "temp unavailable", True),
}

class MegaError(Exception):
    def __init__(self, code: int):
        name, msg, retriable = MEGA_ERRORS.get(code, (f"E{code}", "unknown", False))
        self.code = code
        self.name = name
        self.retriable = retriable
        super().__init__(f"MEGA {name} ({code}): {msg}")

class QuotaExceeded(MegaError):
    """EOVERQUOTA: IP burned, needs proxy rotation or wait."""

class GUrlExpired(MegaError):
    """EEXPIRED: reissue a=g."""

class PermanentMegaError(MegaError):
    """Non-retriable: bad args, not found, blocked, bad key."""

class RateLimited(Exception):
    """HTTP-layer 8008 / 509 from the load balancer (not a MEGA -code)."""
    def __init__(self, status: int, body: str = ""):
        self.status = status
        self.body = body
        super().__init__(f"HTTP rate-limit {status}: {body[:120]}")

def raise_for_code(code: int):
    if code == -17:
        raise QuotaExceeded(code)
    if code == -8:
        raise GUrlExpired(code)
    err = MegaError(code)
    if not err.retriable:
        raise PermanentMegaError(code)
    raise err

EXIT_OK = 0
EXIT_GENERIC = 1
EXIT_PERMANENT = 2
EXIT_RETRY_EXHAUST = 3
EXIT_QUOTA = 4
EXIT_BAD_LINK = 5
