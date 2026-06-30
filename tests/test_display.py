from recorder.display import compose_frame, pack_xrgb8888, compute_display_state

def test_compose_size():
    img = compose_frame("RECORDING","02:14"); assert img.size==(1024,600) and img.mode=="RGB"

def test_pack_stride_and_x_bytes():
    raw = pack_xrgb8888(compose_frame("IDLE","",size=(2,1)), line_length=16)
    assert len(raw)==16 and raw[3]==0 and raw[7]==0     # BGRX -> X bytes zero; padded to stride

def _c(s=0,u=0,sub=0): return {"spooled":s,"uploaded":u,"submitted":sub}
def _s(recording=False,timer="",synced=True,disk_ok=True,counts=None,unconf=0,
       offline=False,subfail=False,error=None):
    return compute_display_state(recording,timer,synced,disk_ok,counts or _c(),unconf,offline,subfail,error)

def test_priority_recording_wins(): assert _s(recording=True,counts=_c(s=3),offline=True)[0]=="RECORDING"
def test_error_state_visible():     assert _s(error="mic?")[0]=="ERROR"
def test_storage_low_over_unconfirmed(): assert _s(disk_ok=False,unconf=2)[0]=="STORAGE_LOW"
def test_unconfirmed():             assert _s(unconf=1)[0]=="UNCONFIRMED"
def test_wait_clock():              assert _s(synced=False,counts=_c(s=1))[0]=="WAIT_CLOCK"
def test_offline():                 assert _s(counts=_c(u=1),offline=True)[0]=="OFFLINE"
def test_submit_error():            assert _s(counts=_c(u=1),subfail=True)[0]=="SUBMIT_ERROR"
def test_uploading_syncing_idle():
    assert _s(counts=_c(u=1))[0]=="UPLOADING"
    assert _s(counts=_c(sub=1))[0]=="SYNCING"
    assert _s()[0]=="IDLE"
