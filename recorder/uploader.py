import logging, os
from datetime import datetime, timezone
from recorder import titles
from recorder.state import Item
from recorder.storage import s3_key

log = logging.getLogger("uploader")
SUBMIT_COOLOFF_S = 3600   # don't re-submit a maybe-accepted upload within this window (anti-duplicate)

class Uploader:
    def __init__(self, config, statedb, storage, fireflies, clock_is_synced):
        self.cfg, self.db, self.storage, self.ff = config, statedb, storage, fireflies
        self.clock_is_synced = clock_is_synced
        self.offline = False        # S3 unreachable on last pass
        self.submit_failing = False  # Fireflies submit failing on last pass

    def spool(self, recording):
        now = datetime.now()
        suffix = titles.gen_suffix()
        title = titles.make_title(self.cfg.title_prefix, now, suffix)
        key = s3_key(self.cfg.device_id, now, recording.uuid)
        self.db.add(Item(uuid=recording.uuid, title=title, suffix=suffix,
                         duration=recording.duration, s3_key=key, local_path=recording.path,
                         recorded_at=now.isoformat(), submitted_at=None,
                         status="spooled", transcript_id=None))
        log.info("spooled %s", recording.uuid)

    def upload_spooled(self):
        hit_error = False
        for it in self.db.by_status("spooled"):
            try:
                self.storage.put(it.local_path, it.s3_key, {
                    "title": it.title, "recorded_at": it.recorded_at,
                    "duration": it.duration, "client_reference_id": it.uuid})
                # Delete the local file BEFORE marking 'uploaded'. Invariant: status=='uploaded'
                # implies the file is gone, so recover_orphans() can never re-spool it (no double-upload).
                if it.local_path and os.path.exists(it.local_path):
                    os.remove(it.local_path)
                self.db.set_status(it.uuid, "uploaded", local_path=None)
                log.info("uploaded %s -> %s", it.uuid, it.s3_key)
            except Exception as e:
                hit_error = True
                log.error("S3 upload failed for %s: %s", it.uuid, e)
        self.offline = hit_error

    def process_pending(self):
        if not self.clock_is_synced():
            log.warning("clock not synced; deferring submissions")
            return
        now = datetime.now(timezone.utc); fail = False
        for it in self.db.by_status("uploaded"):
            if it.last_attempt_at:   # cool-off: give a maybe-accepted upload time to be confirmed
                age = (now - datetime.fromisoformat(it.last_attempt_at)).total_seconds()
                if age < SUBMIT_COOLOFF_S:
                    continue
            # record the attempt BEFORE the POST: a timeout-after-accept then can't be re-submitted
            self.db.set_status(it.uuid, "uploaded", last_attempt_at=now.isoformat())
            try:
                url = self.storage.presign_get(it.s3_key)
                self.ff.upload_audio(url, it.title, self.cfg.attendees, it.uuid)
                self.db.set_status(it.uuid, "submitted", submitted_at=now.isoformat())
                log.info("submitted %s", it.uuid)
            except Exception as e:
                fail = True
                log.error("uploadAudio failed for %s: %s", it.uuid, e)   # retried after cool-off
        self.submit_failing = fail
