from recorder.controller import Controller
from recorder.audio import Recording

class FakeRec:
    def __init__(s, rec, exits=False): s._rec=rec; s.started=False; s._exits=exits
    def start(s): s.started=True
    def poll(s): return s._exits and s.started
    def stop(s): s.started=False; return s._rec
class FakeUp:
    def __init__(s): s.spooled=[]
    def spool(s, rec): s.spooled.append(rec)
class FakeDisp:
    def __init__(s): s.last=None
    def show(s, st, d=""): s.last=(st,d)
class _Cfg: min_free_disk_mb=500

def _c(rec=Recording("p",600.0,"u1"), free=9999, exits=False):
    return Controller(FakeRec(rec,exits),FakeUp(),FakeDisp(),None,_Cfg(),lambda:free)

def test_toggle_records_then_spools():
    c=_c(); c.on_toggle(); assert c.state=="RECORDING" and c.display.last[0]=="RECORDING"
    c.on_toggle(); assert c.state=="IDLE" and len(c.uploader.spooled)==1

def test_short_recording_not_spooled():
    c=_c(rec=None); c.on_toggle(); c.on_toggle(); assert c.uploader.spooled==[] and c.state=="IDLE"

def test_refuses_when_disk_low():
    c=_c(free=10); c.on_toggle(); assert c.state=="IDLE" and c.display.last[0]=="STORAGE_LOW"

def test_tick_auto_stops_at_max_duration():
    c=_c(exits=True); c.on_toggle(); assert c.state=="RECORDING"
    assert c.tick() is True and c.state=="IDLE" and len(c.uploader.spooled)==1

def test_shutdown_finalizes_active_recording():
    c=_c(); c.on_toggle(); assert c.state=="RECORDING"
    c.shutdown(); assert c.state=="IDLE" and len(c.uploader.spooled)==1
