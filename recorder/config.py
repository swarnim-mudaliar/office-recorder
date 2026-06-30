import json
from dataclasses import dataclass, field

REQUIRED = ["FIREFLIES_API_KEY", "AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY",
            "AWS_REGION", "S3_BUCKET", "DEVICE_ID", "BUTTON_GLOB"]

@dataclass
class Config:
    fireflies_api_key: str
    aws_access_key_id: str
    aws_secret_access_key: str
    aws_region: str
    s3_bucket: str
    device_id: str
    button_glob: str
    mic_hint: str = "ice"
    presign_ttl: int = 604800
    title_prefix: str = "Office discussion"
    attendees: list = field(default_factory=list)
    min_record_seconds: int = 3
    max_record_seconds: int = 21600
    reconcile_base_hours: int = 2
    min_free_disk_mb: int = 500

def _parse_env(text):
    out = {}
    for line in text.splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            out[k.strip()] = v.strip()
    return out

def load_config(env_path: str) -> Config:
    with open(env_path) as f:
        env = _parse_env(f.read())
    missing = [k for k in REQUIRED if not env.get(k)]
    if missing:
        raise ValueError(f"Missing required config keys: {', '.join(missing)}")
    return Config(
        fireflies_api_key=env["FIREFLIES_API_KEY"],
        aws_access_key_id=env["AWS_ACCESS_KEY_ID"],
        aws_secret_access_key=env["AWS_SECRET_ACCESS_KEY"],
        aws_region=env["AWS_REGION"], s3_bucket=env["S3_BUCKET"],
        device_id=env["DEVICE_ID"], button_glob=env["BUTTON_GLOB"],
        mic_hint=env.get("MIC_HINT", "ice"),
        presign_ttl=int(env.get("PRESIGN_TTL", 604800)),
        title_prefix=env.get("TITLE_PREFIX", "Office discussion"),
        attendees=json.loads(env["ATTENDEES"]) if env.get("ATTENDEES") else [],
        min_record_seconds=int(env.get("MIN_RECORD_SECONDS", 3)),
        max_record_seconds=int(env.get("MAX_RECORD_SECONDS", 21600)),
        reconcile_base_hours=int(env.get("RECONCILE_BASE_HOURS", 2)),
        min_free_disk_mb=int(env.get("MIN_FREE_DISK_MB", 500)),
    )
