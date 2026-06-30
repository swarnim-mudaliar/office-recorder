import glob, logging, time
import evdev

log = logging.getLogger("button")
# Pick a node with real KEY_* (<0x100) or consumer keys (>=0x160), skipping BTN_* pointer codes
# (0x100-0x15f). (A few exotic gamepad BTN_* sit >=0x160 but are irrelevant for a keyboard-style button.)

def debounce_ok(last_ts, now_ts, debounce_ms) -> bool:
    return last_ts is None or (now_ts - last_ts) * 1000.0 >= debounce_ms

def select_event_node(devices):
    for d in devices:
        keys = d.capabilities().get(evdev.ecodes.EV_KEY, [])
        if any(k < 0x100 or k >= 0x160 for k in keys):   # real KEY_* / consumer, not BTN_* pointer
            return d
    raise RuntimeError("No keyboard/consumer EV_KEY node found for the button")

class ButtonWatcher:
    def __init__(self, glob_pattern, on_toggle, debounce_ms=300, _opener=None):
        self.glob_pattern, self.on_toggle, self.debounce_ms = glob_pattern, on_toggle, debounce_ms
        self._opener = _opener or evdev.InputDevice

    def _resolve(self):
        paths = sorted(glob.glob(self.glob_pattern))
        if not paths:
            raise RuntimeError(f"No input device matching {self.glob_pattern} (check `ls /dev/input/by-id/`)")
        devs = [self._opener(p) for p in paths]
        dev = select_event_node(devs)
        for d in devs:                       # close the non-selected nodes (no fd leak)
            if d is not dev:
                try: d.close()
                except Exception: pass
        dev.grab()
        log.info("grabbed %s (%s)", dev.path, dev.name)
        return dev

    def run(self):
        # Resilient: a device error (e.g. mic/button unplugged) never permanently kills the watcher.
        while True:
            try:
                dev = self._resolve(); last = None
                for ev in dev.read_loop():
                    if ev.type != evdev.ecodes.EV_KEY or ev.value != 1:   # key-down only
                        continue
                    now = time.monotonic()
                    if debounce_ok(last, now, self.debounce_ms):
                        last = now
                        try:
                            self.on_toggle()
                        except Exception:
                            log.exception("on_toggle error; ignoring this press")
            except Exception:
                log.exception("button watcher error; retrying in 5s")
                time.sleep(5)
