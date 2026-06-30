import requests

ENDPOINT = "https://api.fireflies.ai/graphql"
_UPLOAD_Q = "mutation($input: AudioUploadInput) { uploadAudio(input: $input) { success title message } }"
_TRANSCRIPTS_Q = ("query($fromDate: DateTime, $toDate: DateTime, $mine: Boolean, $limit: Int, $skip: Int) "
                  "{ transcripts(fromDate: $fromDate, toDate: $toDate, mine: $mine, limit: $limit, skip: $skip) "
                  "{ id title duration } }")

def build_upload_payload(url, title, attendees, client_reference_id):
    return {"query": _UPLOAD_Q, "variables": {"input": {
        "url": url, "title": title, "attendees": attendees or [],
        "bypass_size_check": True, "client_reference_id": client_reference_id}}}

def build_transcripts_payload(from_iso, to_iso, skip):
    return {"query": _TRANSCRIPTS_Q, "variables": {
        "fromDate": from_iso, "toDate": to_iso, "mine": True, "limit": 50, "skip": skip}}

class Fireflies:
    def __init__(self, api_key, session=None):
        self._s = session or requests.Session()
        self._h = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    def _post(self, payload):
        r = self._s.post(ENDPOINT, json=payload, headers=self._h, timeout=30)
        r.raise_for_status()
        body = r.json()
        if body.get("errors"):
            raise RuntimeError(f"Fireflies API error: {body['errors']}")
        return body["data"]

    def upload_audio(self, url, title, attendees, client_reference_id):
        res = self._post(build_upload_payload(url, title, attendees, client_reference_id))["uploadAudio"]
        if not res.get("success"):
            raise RuntimeError(f"uploadAudio failed: {res.get('message')}")
        return res

    def list_transcripts(self, from_iso, to_iso):
        out, skip = [], 0
        while True:
            page = self._post(build_transcripts_payload(from_iso, to_iso, skip))["transcripts"]
            out.extend(page)
            if len(page) < 50:
                return out
            skip += 50
