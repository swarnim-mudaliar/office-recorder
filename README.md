# Office Recorder → Fireflies

A standalone Raspberry Pi appliance that records a room from a USB mic on a
button press and auto-uploads the audio to [Fireflies](https://fireflies.ai)
for transcription — no laptop in the loop. A small 7" screen shows live status
(recording timer, upload/transcription progress, errors).

Press the button to start; press again to stop. On stop the clip is spooled
locally and the device returns to idle immediately, while a background worker
uploads it to S3 (durable), submits it to Fireflies, and confirms the
transcript appeared.

## How it works

A single Python systemd service on Raspberry Pi OS Lite. Independent
components — button, recorder, uploader, reconciler, display — are wired by a
state-machine controller and a tiny thread-safe SQLite state DB:

```
button ─▶ controller ─▶ recorder (ffmpeg/ALSA)
                            │ spool (local, instant)
                            ▼
   worker thread ─▶ S3 upload ─▶ Fireflies submit ─▶ reconcile (confirm transcript)
                            │
                            ▼
                     7" framebuffer status display
```

Each recording gets a unique 6-hex-char title suffix; the reconciler confirms
transcription by finding that suffix in `transcripts(mine: true)`.

## Hardware

- Raspberry Pi 4
- USB microphone (e.g. Blue Snowball iCE)
- USB button (keyboard-style HID)
- 7" HDMI screen (1024×600)

## Development

Most of the logic is pure and unit-tested off-device; hardware/external
boundaries (ALSA, evdev, framebuffer, S3, Fireflies) are thin wrappers
verified on the Pi.

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
python3 -m pytest -m "not integration"     # off-device suite
```

> **Note:** `evdev` (the button library) is Linux-only — it does not build on
> macOS. On a Mac, install the other deps and run the suite excluding the
> button module; the button logic is exercised on Linux/CI and on-device.

## Deployment & setup

See [`deploy/setup-os.md`](deploy/setup-os.md) for flashing the OS, the display
cmdline, AWS/Fireflies provisioning, and writing the `0600`
`/etc/office-recorder.env` secrets file (which is **never** committed).

## Design

The full design spec lives in [`docs/design.md`](docs/design.md)
(human-readable summary: [`docs/design.html`](docs/design.html)).

## License

[MIT](LICENSE)
