import glob, logging, os, shutil, signal, threading, time
from recorder.config import load_config
from recorder.state import StateDB
from recorder.audio import Recorder, Recording, mp3_duration
from recorder.storage import Storage
from recorder.fireflies import Fireflies
from recorder.uploader import Uploader
from recorder.reconciler import Reconciler
from recorder.display import Display, compute_display_state
from recorder.button import ButtonWatcher
from recorder.controller import Controller
from recorder.clock import is_synced

ENV = os.environ.get("OFFICE_RECORDER_ENV", "/etc/office-recorder.env")
SPOOL = "/var/lib/office-recorder/spool"; DB = "/var/lib/office-recorder/state.db"
UPLOAD_EVERY, RECONCILE_EVERY = 15, 60   # transcripts confirm within ~60s (Fireflies is usually quick)
log = logging.getLogger("main")

def disk_free_mb(path=SPOOL): return shutil.disk_usage(path).free // (1024 * 1024)

def recover_orphans(db, uploader):
    """Spool any *.mp3 on disk with no DB row (crash/shutdown mid-recording) — never lose audio."""
    known = {i.local_path for i in db.by_status("spooled") if i.local_path}
    for path in glob.glob(os.path.join(SPOOL, "*.mp3")):
        if path in known:
            continue
        try:
            dur = mp3_duration(path)
        except (RuntimeError, OSError):
            dur = 0.0
        uid = os.path.splitext(os.path.basename(path))[0]
        uploader.spool(Recording(path=path, duration=dur, uuid=uid))
        log.warning("recovered orphan recording %s", path)

def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    os.makedirs(SPOOL, exist_ok=True); os.makedirs(os.path.dirname(DB), exist_ok=True)
    cfg = load_config(ENV); db = StateDB(DB)
    rec = Recorder(cfg.mic_hint, SPOOL, cfg.min_record_seconds, cfg.max_record_seconds)
    storage = Storage(cfg); ff = Fireflies(cfg.fireflies_api_key)
    uploader = Uploader(cfg, db, storage, ff, clock_is_synced=is_synced)
    reconciler = Reconciler(cfg, db, ff, clock_is_synced=is_synced)
    display = Display(); ctl = Controller(rec, uploader, display, db, cfg, disk_free_mb)

    recover_orphans(db, uploader)
    shutdown = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: shutdown.set())   # handler only flags; no work here
    signal.signal(signal.SIGINT, lambda *_: shutdown.set())

    threading.Thread(target=ButtonWatcher(cfg.button_glob, ctl.on_toggle).run, daemon=True).start()

    shared = {"unconfirmed": 0}
    def worker():   # background S3 upload + Fireflies submit/reconcile (never blocks the timer)
        last_up = last_rec = 0.0
        while not shutdown.is_set():
            now = time.monotonic()
            try:
                if now - last_up >= UPLOAD_EVERY:
                    last_up = now; uploader.upload_spooled(); uploader.process_pending()
                if now - last_rec >= RECONCILE_EVERY:
                    last_rec = now; shared["unconfirmed"] = len(reconciler.reconcile())
            except Exception:
                log.exception("worker error; continuing")
            shutdown.wait(2.0)
    threading.Thread(target=worker, daemon=True).start()

    _sync = {"v": False, "t": -1e9}
    def synced_cached():   # avoid forking timedatectl every second
        now = time.monotonic()
        if now - _sync["t"] >= 30:
            _sync["v"], _sync["t"] = is_synced(), now
        return _sync["v"]

    while not shutdown.is_set():
        ctl.tick()                         # refreshes the RECORDING timer if recording
        if ctl.state != "RECORDING":
            counts = {s: len(db.by_status(s)) for s in ("spooled", "uploaded", "submitted")}
            state, detail = compute_display_state(
                False, "", synced_cached(), disk_free_mb() >= cfg.min_free_disk_mb,
                counts, shared["unconfirmed"], uploader.offline, uploader.submit_failing, ctl.error)
            display.show(state, detail)
        time.sleep(1.0)

    ctl.shutdown()                         # finalise + spool any in-progress recording, then exit
    log.info("clean shutdown")
    os._exit(0)

if __name__ == "__main__":
    main()
