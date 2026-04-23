import json
from pathlib import Path


def state_path(out_path: Path) -> Path:
    return out_path.with_suffix(out_path.suffix + ".megapull.json")


def load_state(out_path: Path, size: int) -> dict:
    sp = state_path(out_path)
    if sp.exists():
        st = json.loads(sp.read_text())
        if st.get("size") == size:
            return st
    return {"size": size, "done": []}


def save_state(out_path: Path, state: dict):
    state_path(out_path).write_text(json.dumps(state))


def pending_ranges(size: int, done: list[list[int]]):
    done = sorted(done)
    cur = 0
    for s, e in done:
        if s > cur:
            yield (cur, s)
        cur = max(cur, e)
    if cur < size:
        yield (cur, size)