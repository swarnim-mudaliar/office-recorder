import logging, threading, time
log = logging.getLogger("controller")

class Controller:
    def __init__(self, recorder, uploader, display, statedb, config, disk_free_mb):
        self.recorder, self.uploader, self.display = recorder, uploader, display
        self.db, self.cfg, self.disk_free_mb = statedb, config, disk_free_mb
        self.state = "IDLE"; self._started = None; self._lock = threading.Lock()
        self.error = None   # sticky hardware error (e.g. mic-start failure), surfaced on-screen

    def _finish(self):
        rec = self.recorder.stop(); self.state = "IDLE"; self._started = None
        if rec:
            self.uploader.spool(rec); self.display.show("UPLOADING", "")
        else:
            self.display.show("IDLE", "")

    def on_toggle(self):
        with self._lock:
            if self.state == "IDLE":
                if self.disk_free_mb() < self.cfg.min_free_disk_mb:
                    self.display.show("STORAGE_LOW", ""); log.error("refusing: disk low"); return
                try:
                    self.recorder.start()
                except Exception as e:
                    log.error("failed to start recording: %s", e)
                    self.error = "mic?"; self.display.show("ERROR", "mic?"); return   # sticky; survives
                self.error = None
                self.state = "RECORDING"; self._started = time.monotonic()
                self.display.show("RECORDING", "00:00")
            elif self.state == "RECORDING":
                self._finish()

    def shutdown(self):
        # Single synchronized stop path (shares _lock with the button thread): finalise + spool
        # any in-progress recording so a reboot/stop never loses it.
        with self._lock:
            if self.state == "RECORDING":
                self._finish()

    def tick(self):
        with self._lock:
            if self.state != "RECORDING":
                return False
            if self.recorder.poll():        # ffmpeg hit -t max -> auto-stop
                log.info("max-duration auto-stop"); self._finish(); return True
            secs = int(time.monotonic() - self._started)
            self.display.show("RECORDING", f"{secs//60:02d}:{secs%60:02d}")
            return False
