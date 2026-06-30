# Office Discussion Recorder → Fireflies — Design Spec

**Date:** 2026-06-26
**Status:** Design converged
**Owner:** <you>

## 1. Summary

A small, self-contained hardware device for the office: press a button to record an
in-person discussion from a USB mic, press again to stop, and the device automatically
uploads the audio to Fireflies for transcription. It runs entirely on its own (a
Raspberry Pi) with no dependency on anyone's laptop — power it on and it's ready.

A 7" screen shows live status (the single feedback channel — see §6.5).

## 2. Goals & non-goals

**Goals**
- One physical button: press to start recording, press again to stop + upload.
- Fully standalone: boots into the service, joins WiFi, works with no laptop attached.
- Reliable upload, surviving transient WiFi/network failures.
- **Never lose a recording, and know when one didn't transcribe:** the audio is durably held
  in S3 (30-day retention) as soon as it's recorded; an on-device reconciler confirms the
  transcript appeared and warns if it didn't (§6.4, §9).
- Clear, glanceable status on screen so anyone can use it and people know recording is live.

**Non-goals (YAGNI)**
- No pause/resume; no spoken/audio feedback (the screen suffices); no on-device
  transcription/editing; no multi-button UI; no touch; no battery.
- No inbound webhooks (unreachable behind office NAT) — confirmation is by **outbound
  polling** of the `transcripts` query.

## 3. Hardware (bill of materials — ~£121, all ordered)

| Part | Price | Connection | Notes |
|---|---|---|---|
| Raspberry Pi 4 1GB Starter Kit (db-tronic) | £78 | — | Pi 4 (1GB), **official 15W USB-C PSU**, 64GB microSD, official case, heatsinks, micro-HDMI→full-HDMI cable, card reader |
| Blue Snowball iCE USB mic | (owned) | USB-A | Cardioid; point at the group. **Fixed 44.1 kHz / 16-bit** (§6.2) |
| Kukyller Programmable Single-Key Button | £15 | USB-A | USB HID device; emits a keypress. We read the keypress, don't reprogram it |
| Vutlace 7" HDMI Monitor (non-touch, IPS, **native 1024×600**) | £28 | **full-size HDMI** + DC barrel-jack power | Kit's micro-HDMI→full-HDMI cable into the monitor; use **HDMI0** (port nearest USB-C). Speakers unused |

**Assembly (no soldering, no jumper wires):** insert microSD, attach heatsinks, seat Pi in
case; plug mic → USB-A, button → USB-A, monitor → HDMI0; power the Pi (USB-C) and the
monitor (its DC adapter). Cables only. The official 15W PSU is mandatory (under-voltage →
silent crashes/SD corruption); it's in the kit.

## 4. Data & privacy note

This device records **our own office discussions** — an internal tool. The S3 bucket lives
in a dedicated AWS account with a **narrowly-scoped IAM user** (§8). No third-party or
customer data is involved.

**Consent / GDPR:** recording identifiable people engages UK GDPR (lawful basis + notice).
The `● RECORDING` indicator gives awareness but is **not** lawful basis on its own — a
written team notice/policy must exist (per your organisation's data-protection policy).
Consent is policy, not just UX.

## 5. Architecture overview

```
[ USB Button ] --keypress--> +------------------+
[ USB Mic    ] --audio-----> |   Controller     | --status--> [ HDMI Screen ]
                             | (state machine)  |
                             +------------------+
                                  |   ^
                             start|   |mp3 path on stop (then immediately IDLE)
                                  v   |
                             [ Recorder (ffmpeg) ]
                                       |
                              writes mp3 to local spool (timestamped name)
                                       |
                                       v
                  [ Uploader ] --PutObject--> [ S3 (30-day retention) ]
                       |  (on success: DELETE local copy; track item in a small state DB)
                       |                              |
                       |                       presigned URL (7-day TTL)
                       v                              |
                  uploadAudio (GraphQL, Bearer, unique ASCII title) <--+
                       |
                       v
                  [ Reconciler ] --transcripts(fromDate/toDate, mine) outbound poll-->
                       |  (match locally by unique suffix + duration; persist transcript id)
                  confirmed -> done; unconfirmed past (duration-scaled) threshold -> warn
```

Fireflies' API accepts a **URL** (not a file upload). **Record, upload, and reconcile are
decoupled.** **S3 is the durability anchor:** the local audio is deleted as soon as S3
`PutObject` succeeds (S3 is 11-nines durable), so a transcription/confirmation problem can
**never** cascade into local disk filling up or recording being blocked. Item state
(s3 key, title, suffix, duration, timestamps, status) lives in a tiny on-disk state DB, not
in retained audio.

## 6. Components (each isolated, testable)

### 6.1 ButtonWatcher
- **Does:** Emits a debounced `toggle` on press.
- **How:** `python-evdev`. Composite HID gadgets enumerate as **multiple input nodes**; the
  keypress may land off `*-kbd`. At startup enumerate **all** nodes under the button's
  `/dev/input/by-id/<prefix>*`, find which carries the key event, and `grab()` (EVIOCGRAB)
  it. Map **any** key/consumer code → `toggle`. Trigger on key-**down** (`value==1`), ignore
  autorepeat (`value==2`). **Debounce ~300 ms.**
- **Depends on:** `python-evdev`; service user in the `input` group.

### 6.2 Recorder
- **Does:** Starts/stops capture; returns the finished MP3 path + its duration.
- **How:** One `ffmpeg` subprocess captures from the Snowball via ALSA → MP3:
  - **Native 44.1 kHz, mono, ~64 kbps MP3** (iCE is locked to 44.1 kHz; native avoids
    resampling; ~29 MB/h). Resolve the device by **`CARD=` name** via `arecord -L`
    (`plughw:CARD=…`), never a hard index.
  - **Stop via `SIGINT`** to ffmpeg (NOT `q` on stdin — under systemd stdin is `/dev/null`).
    ffmpeg flushes/finalises on SIGINT; MP3 is frame-based so even a hard kill is playable.
  - **Await the ffmpeg exit before the next capture** — it must release `plughw` first, else
    a fast re-toggle hits "device busy".
  - **Anti-tap min-duration (~3 s):** discard accidental taps. (This is *only* about taps —
    the 50 KB Fireflies floor is handled by `bypass_size_check:true`, and a genuinely tiny
    clip may simply not produce a transcript; that's acceptable.)
  - **Max-duration auto-stop (6 h):** ~6 h @ 64 kbps ≈ 173 MB < 200 MB cap (§13).
- **Depends on:** `ffmpeg`, the Snowball's ALSA `plughw` device.

### 6.3 Uploader (background worker over the local spool)
1. `boto3` `put_object` to a **sortable, timestamped key**
   `s3://<bucket>/<device>/<YYYY>/<MM>/<YYYYMMDDTHHMMSS>-<uuid>.mp3` with **metadata**
   `title`, `recorded_at`, `duration`, `client_reference_id`. Client built with the bucket's
   **region** (`AWS_REGION` must match, else `SignatureDoesNotMatch`).
2. **On `PutObject` success, delete the local audio** (it is now durable in S3) and record
   the item in the state DB (`status=uploaded`, with s3 key, title, suffix, duration). Local
   disk now only ever holds *not-yet-uploaded* audio (offline backlog), never confirmation
   backlog.
3. Mint a presigned GET URL (**7-day TTL**, SigV4 max for IAM-user keys).
4. POST `uploadAudio` (`https://api.fireflies.ai/graphql`, `Authorization: Bearer <key>`)
   with `url`, a **unique ASCII title** (§7), `attendees`, **`bypass_size_check:true`**,
   `client_reference_id` = the UUID. On `success:true` → `status=submitted` (store submit
   time). 
5. **Retry policy (avoids duplicate transcripts):** retry/re-mint only when the
   `uploadAudio` *call itself* fails or the presigned URL expired (the audio is in S3, so
   re-mint from the s3 key). A `success:true`-but-not-yet-transcribed item is **not**
   re-submitted (that would risk a duplicate transcript + double charge) — the Reconciler
   handles it.
6. **Gate on confirmed NTP sync** (§6.6): bad clock → bad SigV4 window / TLS.
- **Depends on:** `boto3`, `requests`, scoped AWS creds, Fireflies key, synced clock, state DB.

### 6.4 Reconciler (visibility — outbound, NAT-safe, robust matching)
- Only `submitted` items are polled, and only while some exist (idle otherwise). Cadence
  ~10 min. Each pass runs **one batched** `transcripts` query over a date window from the
  oldest pending submit → now: `transcripts(fromDate, toDate, mine: true, limit: 50, skip)`
  — **`limit` caps at 50, so paginate** via `skip`. The `mine` filter (API-key owner is
  organiser) plus a dedicated service account (§8) keeps results to this device's uploads.
- **Matching is not keyword-dependent.** `keyword` is a tokenised text search, so we do
  **local** matching on the returned transcripts: match by the **unique ASCII suffix**
  contained in the title, with **`duration`** as a tie-breaker/confirmation (the Transcript
  object returns both `title` and `duration`). On match, **persist the transcript `id`** so
  later polls are id-based and immune to any title normalisation. (Title fidelity — that the
  uploaded title appears verbatim — is an explicit gating test, §12; the suffix+duration
  match tolerates whitespace/charset normalisation if it isn't.)
- **Confirmed:** mark `status=confirmed` (optionally delete the S3 object early; otherwise
  the 30-day lifecycle reclaims it).
- **Unconfirmed past a duration-scaled threshold** (`max(RECONCILE_BASE_HOURS, k × duration)`
  — so a 6 h recording isn't declared late at 1 h): surface a loud
  **`⚠ N recordings unconfirmed`** screen state; the audio is in S3 (30 days, timestamped key
  + metadata) for manual recovery. No blind re-submit (M3).
- Poll budget: idle most of the day; ≤ ~144 batched calls/day when active — well within
  Pro 500/day (§13).
- *Future: if Fireflies ever makes `client_reference_id` queryable on the transcript, this
  whole title/suffix-matching layer collapses to a deterministic id lookup — revisit then.*
- **Depends on:** `requests`, Fireflies API, synced clock, state DB.

### 6.5 StatusDisplay (screen only — the single feedback channel; the #1 build risk)
- **Force the HDMI pipeline via the KERNEL cmdline** (Bookworm KMS ignores legacy `hdmi_*`).
  In `/boot/firmware/cmdline.txt` (appended to the single line):
  `video=HDMI-A-1:1024x600-32@60D consoleblank=0 fbcon=map:1` —
  - `1024x600` = the panel's native mode. **Do not force CVT (`M`)** — cheap non-VESA panels
    often reject computed timings. Because the device must come up **with the monitor off at
    boot** (so no EDID is readable then), an **explicit modeline is the likely required
    outcome**, not EDID-preferred; the exact working modeline is **settled empirically at
    bring-up** (§12). Do not assume EDID will be available.
  - **`-32` forces 32bpp** (vc4-kms defaults to 16bpp RGB565; writing Pillow RGB to a 565 fb
    renders garbage). We write `XRGB8888`.
  - **`D`** force-enables the connector (pipeline up with the monitor off at boot).
  - **`consoleblank=0`** disables the fbcon blank timer. With **no compositor and fbcon off
    fb0, nothing actively drives DPMS**, so the panel won't sleep — there is no extra "DPMS
    off" knob to flip; if a panel still blanks, address it at bring-up. (The failure to avoid:
    the screen sleeping and our direct-fb writes not waking it.)
  - **`fbcon=map:1`** maps the console to a non-existent fb so fbcon does **not** own fb0
    (an empty `fbcon=map:` is a no-op).
- **Rendering (primary):** Pillow renders frames; write packed **`XRGB8888`** to **`/dev/fb0`**
  honouring **byte order (BGR) and stride** (`fix.line_length` ≥ width×4); one frame/second
  for the live timer. No X/Wayland/SDL.
  - *Fallbacks (decided by the §12 bring-up test): `fbi` with pre-rendered PNGs; or pygame
    KMSDRM. `/dev/fb0`-direct is chosen for simplicity on static status frames.*
- **Recovery:** keep **`sshd`** enabled — a renderer failure is recoverable over SSH (a tty2
  getty is not on-screen since fbcon is off HDMI). Log display-init failures to journald.
- **Depends on:** Pillow + `/dev/fb0` (32bpp); the forced `cmdline.txt`; SSH access.

### 6.6 Controller + config + time-sync gate + storage policy
- **States:** `IDLE`, `RECORDING` (+ transient overlays).
- **Transition table:**

  | State | `toggle` | Other |
  |---|---|---|
  | `IDLE` | start Recorder → `RECORDING`; `● RECORDING` + timer | — |
  | `RECORDING` | stop (SIGINT, await exit); if ≥ anti-tap min `enqueue(mp3)`, else discard; → **`IDLE` immediately**; overlay `Uploading…` | max-duration auto-stop = `toggle` |
  | any | presses inside the ~300 ms debounce ignored; a `toggle` during an in-flight upload just starts a **new** recording (single mic/ffmpeg → only one at a time, enforced by the single-button toggle) | Uploader success → `Uploaded`; Reconciler confirmed → `✓ Transcribed`; failure → `⚠ Upload failed — retrying` |

- **Special screen states:** boot/pre-NTP `Starting… (waiting for time sync)` (recording
  allowed, uploads wait; escalates after N min); **offline** `⚠ OFFLINE — N not uploaded`;
  **unconfirmed** `⚠ N recordings unconfirmed`; **storage low** `⚠ STORAGE LOW — cannot record`.
- **Config** (`0600` env file): `FIREFLIES_API_KEY`, `AWS_ACCESS_KEY_ID`,
  `AWS_SECRET_ACCESS_KEY`, `AWS_REGION`, `S3_BUCKET`, `DEVICE_ID`, `PRESIGN_TTL` (7 d),
  `TITLE_PREFIX` ("Office discussion"), `ATTENDEES` (optional JSON), `MIN_RECORD_SECONDS` (3),
  `MAX_RECORD_SECONDS` (21600), `RECONCILE_BASE_HOURS` (2), `MIN_FREE_DISK_MB`.
- **Time-sync gate (no RTC):** the Pi 4 has no battery-backed clock; with `fake-hwclock`
  (default) the boot clock = **last shutdown time** (always past). Uploader/Reconciler require
  `systemd-timesyncd` "synchronized: yes" before minting URLs, stamping titles, or polling.
  Configure **multiple NTP pools**. Office WiFi is assumed plain WPA2-PSK (UDP/123 works); a
  captive portal would block *all* connectivity (out of scope for a headless device). Optional
  fallback: **`htpdate` over HTTP** (avoids the TLS-cert-validity bootstrap an HTTPS-Date
  fetch would hit). Escalate the screen state if unsynced after N minutes. (Optional hardware:
  an I²C RTC.)
- **Storage policy:** the local spool only holds not-yet-uploaded audio, bounded by free disk.
  If free space < `MIN_FREE_DISK_MB`, **refuse to start a new recording** with the loud
  `STORAGE LOW` state (never corrupt/silently drop). Unconfirmed items live in S3, not local,
  so they cannot fill the disk.

### 6.7 Boot / OS configuration
- `/boot/firmware/cmdline.txt`: append `video=HDMI-A-1:1024x600-32@60D consoleblank=0
  fbcon=map:1` (modeline tuned at bring-up).
- Keep `sshd` enabled for recovery. Plymouth is usually absent on Lite (no-op if present).
- `systemd-timesyncd` enabled with fallback NTP pools.
- `journald` bounded (`Storage=volatile` or size cap) — protects SD endurance.
- Service user added to `input`, `video`, `render` groups.
- WiFi + SSH pre-configured at flash via Raspberry Pi Imager. Bookworm NetworkManager
  auto-reconnects WiFi; the upload retry queue covers reconnect gaps.

### 6.8 systemd unit
- Starts the Controller on boot, restarts on crash, logs to journald, drains the persistent
  spool + state-DB queues on startup. Use **`KillMode=mixed`** (+ `KillSignal=SIGINT`, generous
  `TimeoutStopSec`) so the stop signal goes to the main process only and the Controller owns
  ffmpeg's single SIGINT — avoiding a double-SIGINT that could truncate the MP3 flush.

## 7. Data flow (record → confirmed transcript)

1. Press → ffmpeg captures the Snowball (native 44.1k mono) to a timestamped spool file.
2. Press (or max-duration) → MP3 finalised (SIGINT); if ≥ anti-tap min it enters the spool;
   Controller → `IDLE` immediately.
3. Once NTP-synced, the Uploader PutObjects to S3 (durable, 30-day), **deletes the local
   copy**, records state, mints a 7-day URL.
4. Uploader calls `uploadAudio` with `bypass_size_check:true` + a unique ASCII title.
5. Fireflies async-fetches and transcribes.
6. The Reconciler polls `transcripts(fromDate/toDate, mine)`, matches locally by suffix +
   duration, persists the transcript id, marks confirmed. If never confirmed (duration-scaled
   threshold), it warns; recover from S3.

**Title format (ASCII — no em-dash):** `"<TITLE_PREFIX> 2026-06-26 14:30:07 a1b2c3"` —
upload-time + seconds + a short alphanumeric suffix → unique, tokenises cleanly, and
deterministically matchable. (Timestamp is the *upload* moment; uniqueness comes from the
suffix, so correctness holds even for offline-then-uploaded clips.)

## 8. Security

- **Scoped IAM, not admin keys.** A dedicated IAM user limited to `s3:PutObject` +
  `s3:GetObject` on **`arn:aws:s3:::<bucket>/<device>/*`**. Presign generation is local crypto
  (no IAM call, no `s3:ListBucket`).
- **Bucket:** private; reachable only via presigned URLs. **Lifecycle auto-deletes after
  30 days** — the recovery window; balances recoverability vs exfil exposure.
- **Residual risk (accepted, internal tool):** the long-lived key on the SD card can mint
  presigned GETs under the device prefix (audio exfil if the SD is stolen) — bounded by the
  lifecycle + per-prefix scope; rotate if compromised (rotating invalidates outstanding URLs
  → re-mint on next retry).
- **Secrets on device:** env file `chmod 600`, owned by the service user.
- **Fireflies key:** a **dedicated Fireflies service account** on a **PAID plan** (Free cannot
  `uploadAudio`, §13) — privacy, offboarding, and a clean `mine` reconciler filter.

## 9. Resilience / error handling

- **Never lose a recording:** the audio is durable in S3 the moment `PutObject` succeeds; the
  local copy is deleted only then. A confirmation/transcription problem therefore **cannot**
  fill local disk or block recording.
- **Always know:** the Reconciler turns a silent Fireflies fetch failure into a visible
  `unconfirmed` warning; recover from the timestamped S3 copy + metadata.
- **No duplicate charges:** re-submit only on upload-call failure / expired URL, never on a
  merely-unconfirmed item (§6.3.5).
- **Recording never blocked:** stop → enqueue → IDLE immediately.
- **Clock gate:** uploads/polls wait for NTP (multi-pool); state escalates if blocked.
- **Storage low:** refuse to start a new recording (loud), never corrupt/silently drop.
- **Display:** no blanking (`consoleblank=0`), console off fb0 (`fbcon=map:1`), SSH recovery,
  journald logging — no silent dark screen / brick.
- **Device re-enumeration:** mic/button/DRM-connector resolved by name/role at startup.
- **ffmpeg lifecycle:** single SIGINT (`KillMode=mixed`) + await exit (clean finalise + device
  release); a crash is detected, surfaced, and the partial (playable) MP3 salvaged.

## 10. Software stack

- Raspberry Pi OS **Lite** (64-bit, Bookworm, headless).
- Python 3: `evdev`, `boto3`, `requests`, `Pillow`; a small embedded state DB (sqlite/JSON).
- System packages: `ffmpeg` (+ `fbi` only if a display fallback; `htpdate` optional).
- Boot config (§6.7): `cmdline.txt` `video=…-32@60D consoleblank=0 fbcon=map:1`; sshd;
  `systemd-timesyncd` + fallback pools; journald bounded; user in `input`/`video`/`render`.
- `systemd` service unit (`KillMode=mixed`, `KillSignal=SIGINT`, generous `TimeoutStopSec`).
- WiFi + SSH via Raspberry Pi Imager.

## 11. Setup / build outline (full step-by-step guide to follow in the plan)

1. Flash Pi OS Lite (64-bit); pre-set hostname, WiFi, SSH, locale.
2. `cmdline.txt`: append `video=HDMI-A-1:1024x600-32@60D consoleblank=0 fbcon=map:1` (tune the
   modeline at bring-up); keep sshd; timesyncd + fallback pools; journald bounded; add the
   service user to `input`/`video`/`render`.
3. Assemble hardware (heatsinks, case; mic/button → USB; monitor → HDMI0).
4. First boot; SSH in; install deps. **Gating bring-up tests:** (a) the renderer draws at the
   right depth/colours **as the systemd boot service**; (b) the screen does **not** blank after
   >15 min idle; (c) **title fidelity** — upload a clip and confirm the transcript's title
   matches (or that suffix+duration matching works regardless). Settle the modeline here.
5. Create the S3 bucket (+ 30-day lifecycle) + per-device-prefix scoped IAM user in
   a dedicated AWS account; create the dedicated paid Fireflies service account + key; write the `0600`
   env file.
6. Deploy the Python service + systemd unit; enable on boot.
7. Verify each path end-to-end (§12).

## 12. Testing / verification (must actually exercise, not just static-review)

- **Display (as a boot service):** each state renders with correct colours/no garbage
  (confirms 32bpp/stride); **idle >15 min → no blank**; SSH recovery works.
- **Modeline:** clean image, incl. monitor off at boot then on.
- **Title fidelity (gating):** the uploaded title appears on the transcript verbatim, OR
  suffix+duration matching confirms regardless of normalisation.
- **Button:** one debounced `toggle` per press; correct node grabbed (no console leak).
- **Mic capture + stop:** record 10s, SIGINT-stop → clean playable MP3; fast re-toggle does
  not hit "device busy".
- **Guards:** <3s discarded; ~5s clip uploads (validates `bypass_size_check`); max-duration
  auto-stop fires, file < 200 MB.
- **S3:** timestamped key + metadata present; presigned URL downloads it; lifecycle = 30 days;
  **local copy is deleted after PutObject**.
- **Fireflies + Reconciler:** `uploadAudio` → `success:true`; Reconciler finds the transcript
  by suffix+duration, persists id, marks confirmed; force an unconfirmed case → no re-submit,
  the `unconfirmed` warning appears; verify a long (>1h-transcribing) item is not falsely
  re-submitted.
- **Clock gate:** unsynced/blocked NTP → uploads/polls wait, state escalates; proceeds on sync.
- **Resilience:** WiFi off, stop a recording → spools locally; WiFi on → uploads (local
  deleted) + reconciles; reboot mid-spool → resumes; expired-URL retry re-mints; recording
  during in-flight upload → not blocked.
- **Storage low:** simulate low disk → device refuses to record with the loud state.
- **Boot:** power-cycle → service comes up ready, no laptop.

## 13. Constraints / config decisions

- **Fireflies plan (verify before building!):** `uploadAudio` is documented to **require a
  PAID plan** — confirm against the live account. Rate limits: Free 50/day, **Pro 500/day**,
  Business/Ent 60/min. `transcripts` `limit` caps at **50** (paginate via `skip`). Audio max
  **200 MB**; min 50 KB (bypassed via `bypass_size_check:true`).
- **Fireflies account:** a **dedicated paid service account** (not a personal key).
- **Attendees:** optional.
- **S3 retention:** 30-day lifecycle (recovery window).
- **Presigned TTL:** 7 days (SigV4 max for IAM-user keys); re-minted on expired-URL retry.
- **Display:** Pillow→`/dev/fb0` at 32bpp, no blanking, console off fb0; modeline tuned
  empirically; `fbi`/pygame fallbacks. Highest-risk part of the build.
- **Time sync:** multi-pool NTP (no HTTPS-Date; optional `htpdate`).
- **Feedback:** screen only.
- **Matching key:** title-suffix + duration (Fireflies doesn't expose `client_reference_id`
  to polling); revisit if the API adds it.
