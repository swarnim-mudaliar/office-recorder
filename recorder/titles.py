import os, re
from datetime import datetime

_SUFFIX_RE = re.compile(r"\b([0-9a-f]{6})\b")

def gen_suffix() -> str:
    return os.urandom(3).hex()

def make_title(prefix, when: datetime, suffix) -> str:
    return f"{prefix} {when:%Y-%m-%d %H:%M:%S} {suffix}"

def extract_suffix(title):
    m = _SUFFIX_RE.findall(title or "")
    return m[-1] if m else None

def title_contains_suffix(suffix, t_title) -> bool:
    return bool(suffix) and suffix in (t_title or "")

def pick_match(suffix, item_duration_s, transcripts):
    cands = [t for t in transcripts if title_contains_suffix(suffix, t.get("title"))]
    if not cands:
        return None
    if len(cands) == 1:
        return cands[0]
    def gap(t):
        d = t.get("duration")
        return abs((float(d) * 60.0) - float(item_duration_s)) if d is not None else float("inf")
    return min(cands, key=gap)
