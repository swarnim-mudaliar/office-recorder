import pytest
from recorder.audio import resolve_alsa_device, build_ffmpeg_cmd

ARECORD = "null\nplughw:CARD=ICE,DEV=0\n    Blue Snowball iCE\nsysdefault:CARD=ICE\n"

def test_resolve_plughw():
    assert resolve_alsa_device("ice", ARECORD) == "plughw:CARD=ICE,DEV=0"
def test_resolve_absent_raises():
    with pytest.raises(RuntimeError): resolve_alsa_device("zoom", ARECORD)
def test_cmd_native_mono_with_maxdur():
    cmd = build_ffmpeg_cmd("plughw:CARD=ICE,DEV=0", "/tmp/o.mp3", 21600)
    assert "alsa" in cmd and "plughw:CARD=ICE,DEV=0" in cmd
    assert cmd[cmd.index("-ac")+1] == "1" and cmd[cmd.index("-b:a")+1] == "64k"
    assert cmd[cmd.index("-t")+1] == "21600"            # hard cap present
    assert cmd[cmd.index("-ar")+1] == "44100"           # native rate, set as INPUT option
    assert cmd.index("-ar") < cmd.index("-i") and cmd[-1] == "/tmp/o.mp3"
