import threading
from recorder.state import StateDB, Item

def _item(uuid="u1", status="spooled"):
    return Item(uuid=uuid, title="t", suffix="a1b2c3", duration=600.0, s3_key="k",
                local_path="/spool/u1.mp3", recorded_at="2026-06-26T14:30:07",
                submitted_at=None, status=status, transcript_id=None)

def test_roundtrip_and_clear_local_path(tmp_path):
    db = StateDB(str(tmp_path/"s.db")); db.add(_item())
    assert db.get("u1").local_path == "/spool/u1.mp3"
    db.set_status("u1", "uploaded", local_path=None)
    g = db.get("u1"); assert g.status == "uploaded" and g.local_path is None

def test_by_status_transitions(tmp_path):
    db = StateDB(str(tmp_path/"s.db")); db.add(_item("u1")); db.add(_item("u2"))
    assert {i.uuid for i in db.by_status("spooled")} == {"u1", "u2"}
    db.set_status("u1", "submitted", submitted_at="2026-06-26T14:31:00")
    assert [i.uuid for i in db.by_status("submitted")] == ["u1"]
    db.set_status("u1", "confirmed", transcript_id="T9")
    assert db.get("u1").transcript_id == "T9"

def test_concurrent_writes_do_not_error(tmp_path):
    db = StateDB(str(tmp_path/"s.db"))
    def w(n):
        for i in range(50): db.add(_item(f"{n}-{i}"))
    ts = [threading.Thread(target=w, args=(n,)) for n in range(4)]
    [t.start() for t in ts]; [t.join() for t in ts]
    assert len(db.by_status("spooled")) == 200

def test_persists(tmp_path):
    p = str(tmp_path/"s.db"); StateDB(p).add(_item("keep")); assert StateDB(p).get("keep")
