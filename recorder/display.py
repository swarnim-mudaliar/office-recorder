import logging, threading
from functools import lru_cache
from PIL import Image, ImageDraw, ImageFont

log = logging.getLogger("display")

_BG = {"RECORDING":(140,20,20),"UPLOADING":(20,40,110),"SYNCING":(20,40,110),
       "UNCONFIRMED":(150,90,10),"OFFLINE":(90,60,10),"STORAGE_LOW":(120,20,20),
       "ERROR":(120,20,20),"SUBMIT_ERROR":(110,40,20),"WAIT_CLOCK":(60,60,70),"IDLE":(24,26,30)}
_HEAD = {"IDLE":"READY","RECORDING":"REC","UPLOADING":"Uploading...","SYNCING":"Awaiting transcript",
         "OFFLINE":"OFFLINE","UNCONFIRMED":"UNCONFIRMED","STORAGE_LOW":"STORAGE LOW",
         "ERROR":"ERROR","SUBMIT_ERROR":"Fireflies unreachable","WAIT_CLOCK":"Starting..."}

@lru_cache(maxsize=8)
def _font(sz):
    try: return ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", sz)
    except OSError: return ImageFont.load_default()

def compose_frame(state, detail, size=(1024,600)):
    img = Image.new("RGB", size, _BG.get(state,(24,26,30)))
    d = ImageDraw.Draw(img)
    d.text((40, size[1]//2-70), _HEAD.get(state,state), font=_font(96), fill=(245,245,245))
    if detail:
        d.text((40, size[1]//2+50), detail, font=_font(48), fill=(220,220,220))
    return img

def pack_xrgb8888(img, line_length):
    w, h = img.size
    raw = img.convert("RGB").tobytes("raw", "BGRX")   # 4 bytes/px, X=0; C-speed
    row = w * 4
    if line_length == row:
        return raw
    pad = bytes(line_length - row)
    return b"".join(raw[y*row:(y+1)*row] + pad for y in range(h))

def compute_display_state(recording, timer, synced, disk_ok, counts, unconfirmed,
                          offline, submit_failing, error):
    pending_upload = counts["spooled"] + counts["uploaded"]
    if recording:      return ("RECORDING", timer)
    if error:          return ("ERROR", error)              # sticky hardware error (e.g. mic absent)
    if not disk_ok:    return ("STORAGE_LOW", "")
    if unconfirmed:    return ("UNCONFIRMED", f"{unconfirmed} not transcribed")
    if pending_upload and not synced: return ("WAIT_CLOCK", "waiting for time sync")
    if offline and pending_upload:    return ("OFFLINE", f"{pending_upload} not uploaded")
    if submit_failing and counts["uploaded"]: return ("SUBMIT_ERROR", "Fireflies unreachable")
    if pending_upload: return ("UPLOADING", f"{pending_upload} pending")
    if counts["submitted"]: return ("SYNCING", f"{counts['submitted']} awaiting transcript")
    return ("IDLE", "")

class Display:
    def __init__(self, fb_path="/dev/fb0"):
        self.fb_path = fb_path
        self._lock = threading.Lock()
        with open("/sys/class/graphics/fb0/virtual_size") as f:
            w, h = f.read().strip().split(","); self.size = (int(w), int(h))
        with open("/sys/class/graphics/fb0/stride") as f:
            self.stride = int(f.read().strip())

    def show(self, state, detail=""):
        data = pack_xrgb8888(compose_frame(state, detail, size=self.size), self.stride)
        with self._lock, open(self.fb_path, "wb") as fb:
            fb.write(data)
