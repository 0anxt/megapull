# MEGA application-layer error codes (negative ints returned in JSON body).
# Source: reverse-engineered; not officially documented by MEGA.
MEGA_ERRORS = {
    -1: ("EINTERNAL", True),
    -2: ("ENOENT", True),
    -3: ("EAGAIN", False),
    -4: ("ERLIMIT", False),
    -9: ("EBADARGS", True),
    -11: ("ECONTENT", True),
    -12: ("EKEY", True),
    -13: ("EROLLOVER", True),
    -14: ("EMASTER", True),
    -15: ("EOL", True),
    -16: ("EFLDRMD", True),
    -17: ("EFULL", False),
    -18: ("ECLOSE", False),
    -19: ("ENOLOC", False),
    -20: ("ELOCCMD", False),
    -21: ("ESESSION", True),
    -22: ("EUDWLM", False),
    -23: ("EBLOCKED", True),
    -24: ("EOVERFLOW", True),
    -509: ("QUOTA", False),  # community label
}

# Exit codes map to error classes.
EXIT_OK = 0
EXIT_GENERIC = 1
EXIT_PERMANENT = 2
EXIT_RETRY_EXHAUST = 3
EXIT_QUOTA = 4
EXIT_BAD_LINK = 5

class MegaError(Exception):
    permanent: bool = False
    code: int | None = None
    def __init__(self, message: str, code: int | None = None):
        super().__init__(message)
        self.code = code

class PermanentMegaError(MegaError):
    permanent = True

class RetriableMegaError(MegaError):
    permanent = False

class QuotaExceeded(RetriableMegaError):
    pass

class GUrlExpired(RetriableMegaError):
    pass

class RateLimited(RetriableMegaError):
    def __init__(self, message: str, status: int, code: int | None = None):
        super().__init__(message, code)
        self.status = status

def raise_from_code(code: int, context: str = "") -> None:
    name, permanent = MEGA_ERRORS.get(code, ("UNKNOWN", True))
    msg = f"MEGA {name} ({code})"
    if context:
        msg = f"{msg} — {context}"
    if code == -3:
        raise RetriableMegaError(msg, code)
    if code == -509 or name == "QUOTA":
        raise QuotaExceeded(msg, code)
    if permanent:
        raise PermanentMegaError(msg, code)
    raise RetriableMegaError(msg, code)
