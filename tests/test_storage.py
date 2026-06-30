from datetime import datetime
from recorder.storage import s3_key
def test_key():
    assert s3_key("office-1", datetime(2026,6,26,14,30,7), "abcd") == "office-1/2026/06/20260626T143007-abcd.mp3"
