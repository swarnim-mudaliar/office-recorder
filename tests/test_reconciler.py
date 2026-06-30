from datetime import datetime, timezone, timedelta
from recorder.state import StateDB, Item
from recorder.reconciler import Reconciler

class _Cfg: reconcile_base_hours = 2
class FakeFF:
    def __init__(self, t): self._t=t
    def list_transcripts(self, a, b): return self._t

def _sub(db, uuid, suffix, dur, when):
    db.add(Item(uuid=uuid, title=f"x {suffix}", suffix=suffix, duration=dur, s3_key="k",
                local_path=None, recorded_at="2026-06-26T14:30:07", submitted_at=when,
                status="submitted", transcript_id=None))

def test_confirms_on_suffix_match(tmp_path):
    db=StateDB(str(tmp_path/"s.db")); _sub(db,"u1","a1b2c3",600.0,datetime.now(timezone.utc).isoformat())
    rec=Reconciler(_Cfg(),db,FakeFF([{"id":"T1","title":"meet a1b2c3","duration":10}]),lambda:True)
    assert rec.reconcile()==[]                       # duration(min) ignored for single match
    assert db.get("u1").status=="confirmed" and db.get("u1").transcript_id=="T1"

def test_unconfirmed_past_threshold(tmp_path):
    db=StateDB(str(tmp_path/"s.db"))
    _sub(db,"u1","a1b2c3",600.0,(datetime.now(timezone.utc)-timedelta(hours=5)).isoformat())
    rec=Reconciler(_Cfg(),db,FakeFF([{"id":"T","title":"none","duration":1}]),lambda:True)
    assert rec.reconcile()==["u1"] and db.get("u1").status=="submitted"

def test_recent_unmatched_not_flagged(tmp_path):
    db=StateDB(str(tmp_path/"s.db")); _sub(db,"u1","a1b2c3",600.0,datetime.now(timezone.utc).isoformat())
    rec=Reconciler(_Cfg(),db,FakeFF([]),lambda:True)
    assert rec.reconcile()==[]
