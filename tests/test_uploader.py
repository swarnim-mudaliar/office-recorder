import os
from recorder.state import StateDB
from recorder.audio import Recording
from recorder.uploader import Uploader

class FakeStorage:
    def __init__(self, fail=False): self.fail=fail; self.puts=[]
    def put(self, p, k, m):
        if self.fail: raise OSError("net down")
        self.puts.append((k, m))
    def presign_get(self, k): return f"https://s3/{k}"

class FakeFF:
    def __init__(self): self.calls=[]
    def upload_audio(self, url, title, att, ref): self.calls.append(ref); return {"success": True}

class _Cfg: device_id="office-1"; title_prefix="Office discussion"; attendees=[]

def _rec(tmp):
    p=tmp/"r.mp3"; p.write_bytes(b"x"*2000); return Recording(str(p),600.0,"u1")

def test_spool_is_cheap_and_local(tmp_path):
    db=StateDB(str(tmp_path/"s.db")); up=Uploader(_Cfg(),db,FakeStorage(),FakeFF(),lambda:True)
    rec=_rec(tmp_path); up.spool(rec)
    it=db.by_status("spooled")[0]
    assert it.local_path==rec.path and os.path.exists(rec.path)   # not uploaded yet
    assert it.suffix in it.title and it.duration==600.0

def test_upload_spooled_puts_and_deletes(tmp_path):
    db=StateDB(str(tmp_path/"s.db")); st=FakeStorage(); up=Uploader(_Cfg(),db,st,FakeFF(),lambda:True)
    rec=_rec(tmp_path); up.spool(rec); up.upload_spooled()
    assert not os.path.exists(rec.path) and st.puts and up.offline is False
    u=db.by_status("uploaded")[0]; assert u.local_path is None

def test_upload_spooled_offline_keeps_file(tmp_path):
    db=StateDB(str(tmp_path/"s.db")); up=Uploader(_Cfg(),db,FakeStorage(fail=True),FakeFF(),lambda:True)
    rec=_rec(tmp_path); up.spool(rec); up.upload_spooled()
    assert os.path.exists(rec.path) and up.offline is True and db.by_status("spooled")

def test_process_pending_gates_on_clock(tmp_path):
    db=StateDB(str(tmp_path/"s.db")); ff=FakeFF()
    up=Uploader(_Cfg(),db,FakeStorage(),ff,lambda:False)
    up.spool(_rec(tmp_path)); up.upload_spooled(); up.process_pending()
    assert ff.calls==[] and db.by_status("uploaded")           # waited for clock
    up.clock_is_synced=lambda:True; up.process_pending()
    assert ff.calls==["u1"] and db.by_status("submitted")

def test_process_pending_cooloff_skips_recent_attempt(tmp_path):
    from datetime import datetime, timezone
    from recorder.state import Item
    db=StateDB(str(tmp_path/"s.db")); ff=FakeFF()
    up=Uploader(_Cfg(),db,FakeStorage(),ff,lambda:True)
    db.add(Item(uuid="u9",title="t a1b2c3",suffix="a1b2c3",duration=600.0,s3_key="k",
                local_path=None,recorded_at="2026-06-26T14:30:07",submitted_at=None,
                status="uploaded",transcript_id=None,
                last_attempt_at=datetime.now(timezone.utc).isoformat()))
    up.process_pending()
    assert ff.calls==[]                                        # within cool-off, not re-submitted
