import logging, os, signal, subprocess, uuid as uuidlib
from dataclasses import dataclass

log = logging.getLogger("audio")

@dataclass
class Recording:
    path: str; duration: float; uuid: str

def resolve_alsa_device(name_hint, arecord_output) -> str:
    for line in arecord_output.splitlines():
        line = line.strip()
        if line.startswith("plughw:CARD="):
            card = line.split("CARD=",1)[1].split(",",1)[0]
            if name_hint.lower() in card.lower():
                return line
    raise RuntimeError(f"No ALSA plughw device matching '{name_hint}'. Run `arecord -L`.")

def build_ffmpeg_cmd(device, out_path, max_seconds) -> list:
    # -ac/-ar are INPUT options (before -i) so ALSA opens the Snowball at native 44.1k mono
    # (FFmpeg's ALSA demuxer otherwise defaults to 48k, forcing a resample).
    return ["ffmpeg","-hide_banner","-loglevel","error","-y",
            "-f","alsa","-ac","1","-ar","44100","-i",device,"-b:a","64k","-t",str(max_seconds), out_path]

def mp3_duration(path, ffprobe=subprocess.run) -> float:
    r = ffprobe(["ffprobe","-v","error","-show_entries","format=duration",
                 "-of","default=nw=1:nk=1", path], capture_output=True, text=True)
    try:
        return float(r.stdout.strip())
    except (ValueError, AttributeError):
        raise RuntimeError(f"ffprobe could not read duration of {path}: {r.stdout!r}")

class Recorder:
    def __init__(self, name_hint, out_dir, min_seconds, max_seconds):
        self.name_hint, self.out_dir = name_hint, out_dir
        self.min_seconds, self.max_seconds = min_seconds, max_seconds
        self._proc = self._path = self._uuid = None
        os.makedirs(out_dir, exist_ok=True)

    def _device(self):
        out = subprocess.run(["arecord","-L"], capture_output=True, text=True).stdout
        return resolve_alsa_device(self.name_hint, out)

    def start(self):
        if self._proc: return
        self._uuid = uuidlib.uuid4().hex
        self._path = os.path.join(self.out_dir, f"{self._uuid}.mp3")
        self._proc = subprocess.Popen(build_ffmpeg_cmd(self._device(), self._path, self.max_seconds))

    def poll(self) -> bool:
        return self._proc is not None and self._proc.poll() is not None

    def stop(self):
        if not self._proc: return None
        if self._proc.poll() is None:            # still running -> graceful finalise
            self._proc.send_signal(signal.SIGINT)
        try:
            self._proc.wait(timeout=30)          # reap; releases plughw
        except subprocess.TimeoutExpired:
            log.error("ffmpeg did not exit on SIGINT; killing")
            self._proc.kill(); self._proc.wait()
        self._proc, path, uid = None, self._path, self._uuid
        try:
            dur = mp3_duration(path)
        except (RuntimeError, OSError) as e:
            log.error("%s; keeping file for upload", e)   # loud, never delete on ambiguity
            return Recording(path=path, duration=0.0, uuid=uid)
        if dur < self.min_seconds:
            os.remove(path)
            return None
        return Recording(path=path, duration=dur, uuid=uid)
