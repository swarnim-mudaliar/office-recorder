import sqlite3, threading
from dataclasses import dataclass

_UNSET = object()

@dataclass
class Item:
    uuid: str; title: str; suffix: str; duration: float; s3_key: str
    local_path: str | None; recorded_at: str; submitted_at: str | None
    status: str; transcript_id: str | None; last_attempt_at: str | None = None

_COLS = ["uuid","title","suffix","duration","s3_key","local_path",
         "recorded_at","submitted_at","status","transcript_id","last_attempt_at"]

class StateDB:
    def __init__(self, path):
        self._lock = threading.Lock()
        self._db = sqlite3.connect(path, check_same_thread=False)
        self._db.execute(
            "CREATE TABLE IF NOT EXISTS items (uuid TEXT PRIMARY KEY, title TEXT, suffix TEXT, "
            "duration REAL, s3_key TEXT, local_path TEXT, recorded_at TEXT, submitted_at TEXT, "
            "status TEXT, transcript_id TEXT, last_attempt_at TEXT)")
        self._db.commit()

    def add(self, item):
        with self._lock:
            self._db.execute(
                f"INSERT OR REPLACE INTO items ({','.join(_COLS)}) VALUES ({','.join('?'*len(_COLS))})",
                [getattr(item, c) for c in _COLS])
            self._db.commit()

    def set_status(self, uuid, status, *, transcript_id=None, submitted_at=None,
                   local_path=_UNSET, last_attempt_at=None):
        sets, vals = ["status=?"], [status]
        if transcript_id is not None: sets.append("transcript_id=?"); vals.append(transcript_id)
        if submitted_at is not None: sets.append("submitted_at=?"); vals.append(submitted_at)
        if local_path is not _UNSET: sets.append("local_path=?"); vals.append(local_path)
        if last_attempt_at is not None: sets.append("last_attempt_at=?"); vals.append(last_attempt_at)
        vals.append(uuid)
        with self._lock:
            self._db.execute(f"UPDATE items SET {','.join(sets)} WHERE uuid=?", vals)
            self._db.commit()

    def _row(self, r): return Item(**dict(zip(_COLS, r)))

    def by_status(self, status):
        with self._lock:
            cur = self._db.execute(
                f"SELECT {','.join(_COLS)} FROM items WHERE status=? ORDER BY recorded_at", [status])
            return [self._row(r) for r in cur.fetchall()]

    def get(self, uuid):
        with self._lock:
            cur = self._db.execute(f"SELECT {','.join(_COLS)} FROM items WHERE uuid=?", [uuid])
            r = cur.fetchone()
        return self._row(r) if r else None
