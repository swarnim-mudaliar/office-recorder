from recorder.fireflies import build_upload_payload, build_transcripts_payload

def test_upload_payload():
    v = build_upload_payload("https://s3/x.mp3","T abc123",
                             [{"displayName":"A","email":"a@x.com"}],"u1")["variables"]["input"]
    assert v["url"]=="https://s3/x.mp3" and v["title"]=="T abc123"
    assert v["bypass_size_check"] is True and v["client_reference_id"]=="u1"
    assert v["attendees"]==[{"displayName":"A","email":"a@x.com"}]

def test_transcripts_payload():
    p = build_transcripts_payload("2026-06-26T00:00:00.000Z","2026-06-26T23:59:59.000Z",50)
    var = p["variables"]
    assert var["fromDate"].endswith("Z") and var["skip"]==50 and var["limit"]==50 and var["mine"] is True
    assert "transcripts" in p["query"] and "duration" in p["query"]
