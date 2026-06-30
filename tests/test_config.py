import pytest
from recorder.config import load_config

REQUIRED = """FIREFLIES_API_KEY=ff
AWS_ACCESS_KEY_ID=ak
AWS_SECRET_ACCESS_KEY=sk
AWS_REGION=eu-west-1
S3_BUCKET=rec-bucket
DEVICE_ID=office-1
BUTTON_GLOB=/dev/input/by-id/usb-Kukyller*-event*
"""

def _w(tmp, body):
    p = tmp / "env"; p.write_text(body); return str(p)

def test_loads_required_and_defaults(tmp_path):
    c = load_config(_w(tmp_path, REQUIRED))
    assert c.s3_bucket == "rec-bucket" and c.device_id == "office-1"
    assert c.button_glob.startswith("/dev/input/by-id/")
    assert c.presign_ttl == 604800 and c.title_prefix == "Office discussion"
    assert c.attendees == [] and c.min_record_seconds == 3 and c.max_record_seconds == 21600

def test_overrides_and_attendees_json(tmp_path):
    body = REQUIRED + 'TITLE_PREFIX=Standup\nMIN_RECORD_SECONDS=5\nATTENDEES=[{"displayName":"A","email":"a@x.com"}]\n'
    c = load_config(_w(tmp_path, body))
    assert c.title_prefix == "Standup" and c.min_record_seconds == 5
    assert c.attendees == [{"displayName": "A", "email": "a@x.com"}]

def test_missing_required_lists_all(tmp_path):
    with pytest.raises(ValueError) as e:
        load_config(_w(tmp_path, "FIREFLIES_API_KEY=ff\n"))
    m = str(e.value)
    assert "AWS_ACCESS_KEY_ID" in m and "S3_BUCKET" in m and "BUTTON_GLOB" in m
