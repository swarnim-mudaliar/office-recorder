import pytest
evdev = pytest.importorskip("evdev")
from recorder.button import debounce_ok, select_event_node

def test_debounce():
    assert debounce_ok(None,100.0,300) is True
    assert debounce_ok(100.0,100.2,300) is False
    assert debounce_ok(100.0,100.4,300) is True

class _Dev:
    def __init__(s,name,caps): s.name=name; s.path="/d/"+name; s._c=caps
    def capabilities(s): return s._c

def test_select_skips_pointer_only_and_picks_key_node():
    EV_KEY=evdev.ecodes.EV_KEY; EV_REL=evdev.ecodes.EV_REL
    mouse=_Dev("m",{EV_KEY:[evdev.ecodes.BTN_LEFT], EV_REL:[0]})
    kbd=_Dev("k",{EV_KEY:[evdev.ecodes.KEY_C]})
    assert select_event_node([mouse,kbd]).name=="k"
