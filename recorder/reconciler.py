import logging
from datetime import datetime, timezone
from recorder import titles

log = logging.getLogger("reconciler")

def _iso_z(dt): return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")

class Reconciler:
    def __init__(self, config, statedb, fireflies, clock_is_synced, now=None):
        self.cfg, self.db, self.ff = config, statedb, fireflies
        self.clock_is_synced = clock_is_synced
        self._now = now or (lambda: datetime.now(timezone.utc))

    def reconcile(self):
        if not self.clock_is_synced(): return []
        pending = self.db.by_status("submitted")
        if not pending: return []
        oldest = min(datetime.fromisoformat(i.submitted_at) for i in pending)
        now = self._now()
        transcripts = self.ff.list_transcripts(_iso_z(oldest), _iso_z(now))
        unconfirmed = []
        for it in pending:
            dupes = [t for t in transcripts if titles.title_contains_suffix(it.suffix, t.get("title"))]
            if len(dupes) > 1:    # belt-and-suspenders against a duplicate-submit (see uploader cool-off)
                log.warning("multiple transcripts share suffix %s: %s",
                            it.suffix, [d.get("id") for d in dupes])
            match = titles.pick_match(it.suffix, it.duration, transcripts)
            if match:
                self.db.set_status(it.uuid, "confirmed", transcript_id=str(match["id"]))
                log.info("confirmed %s -> %s", it.uuid, match["id"]); continue
            threshold = max(self.cfg.reconcile_base_hours*3600, 2*it.duration)
            if (now - datetime.fromisoformat(it.submitted_at)).total_seconds() > threshold:
                unconfirmed.append(it.uuid)
                log.warning("unconfirmed past threshold: %s", it.uuid)
        return unconfirmed
