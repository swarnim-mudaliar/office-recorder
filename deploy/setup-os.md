# Office Recorder — Raspberry Pi setup (beginner-friendly)

This is the full, no-prior-experience-needed walkthrough to turn a Raspberry Pi,
a USB button, a USB mic, and a 7" screen into the recording appliance. Work
through it top to bottom. Each phase ends at a checkpoint — don't move on until
the checkpoint passes.

You drive everything from your Mac (to flash the SD card and to SSH in) plus a
few commands typed on the Pi itself once it's online.

---

## Phase 0 — Inventory & what else you need

**You should have:**
- Raspberry Pi 4 board (in the kit), its USB-C power supply, and a **microSD card**
  (often in the kit; you flash the OS onto it).
- A **USB button** (a keyboard-style HID — when pressed it sends a key event).
- A **7" screen**.
- A **USB microphone** — ⚠️ the appliance records from a USB mic. If your kit did
  NOT include one, you need one (the design was built around a Blue Snowball iCE,
  but any USB mic works — see Phase 6).

**Two things to check now — they change the steps:**
1. **Micro-HDMI:** the Pi 4 has **micro-HDMI** ports (smaller than normal HDMI).
   To connect an HDMI screen you need a **micro-HDMI → HDMI** cable or adapter.
   The kit or screen may include one; if not, order one.
2. **Screen type:** is your screen connected by an **HDMI cable** (this guide), or
   by a **wide flat ribbon cable** (that's the official Pi DSI touchscreen — its
   setup is different; if that's what you have, stop here and ask). Most generic
   7" 1024×600 screens are HDMI and are also powered by a USB cable.

**On your Mac, install once:**
- [Raspberry Pi Imager](https://www.raspberrypi.com/software/) (flashes the SD card).

---

## Phase 1 — Flash the OS onto the SD card (on your Mac)

We use **Raspberry Pi OS Lite (64-bit)** — "Lite" = no desktop, which is exactly
what an always-on appliance wants.

1. Insert the microSD card into your Mac (use the USB reader from the kit if your
   Mac has no SD slot).
2. Open **Raspberry Pi Imager**.
3. **Choose Device:** Raspberry Pi 4.
4. **Choose OS:** *Raspberry Pi OS (other)* → **Raspberry Pi OS Lite (64-bit)**.
5. **Choose Storage:** your SD card.
6. Click **Next**, then **Edit Settings** (the customization dialog) — this is the
   magic that makes the Pi reachable with no keyboard/monitor:
   - **Set hostname:** `office-recorder` (so it's reachable as `office-recorder.local`).
   - **Set username and password:** pick a username (e.g. `alice`) and a password.
     **Remember these** — you log in with them. (This username is the `<user>` used
     throughout.)
   - **Configure wireless LAN:** your Wi-Fi SSID + password + your country (e.g. `GB`).
   - **Set locale:** your timezone (e.g. `Europe/London`).
   - **Services tab → Enable SSH → Use password authentication.**
7. **Save**, then **Write**. Wait for it to flash + verify (a few minutes).

**Checkpoint:** Imager says "Write Successful". Eject the card.

---

## Phase 2 — First boot & connect from your Mac

1. Put the SD card into the Pi. Connect the **mic**, **button**, and **screen**
   (and the screen's USB power if it has a separate USB power lead). Leave the
   micro-HDMI connected.
2. Plug in the Pi's USB-C power. It boots (green LED blinks as it reads the card).
3. Give it ~90 seconds for the first boot to expand the filesystem and join Wi-Fi.
4. On your Mac, open Terminal and SSH in (use the username you set):
   ```bash
   ssh alice@office-recorder.local
   ```
   Type `yes` to trust it on first connect, then your password.

**Checkpoint:** you see a prompt like `alice@office-recorder:~ $`. You're on the Pi.
*(If `office-recorder.local` doesn't resolve, find the Pi's IP from your router's
device list and `ssh alice@<that-ip>` instead.)*

> From here, commands prefixed with **(Pi)** are typed in this SSH session.

---

## Phase 3 — System preparation

**(Pi)** Update and install the system packages the app needs:
```bash
sudo apt update && sudo apt full-upgrade -y
sudo apt install -y ffmpeg python3-venv python3-dev build-essential fonts-dejavu-core git
```
- `ffmpeg` — records and encodes the audio (also provides `ffprobe`).
- `python3-venv` — isolated Python environment for the app.
- `python3-dev` + `build-essential` — C compiler + Python headers, needed to build the
  `evdev` button library (it compiles a C extension from source; Lite doesn't ship these).
- `fonts-dejavu-core` — the font drawn on the status screen.
- `git` — to download the app code.

**Time sync (important):** the app waits for the clock to be NTP-synced before
sending to Fireflies (so transcripts aren't mis-dated). Verify:
```bash
timedatectl
```
Look for **`System clock synchronized: yes`** and **`NTP service: active`**. (If
not, it usually syncs within a minute of being online.)

**Bound the logs** so they can't fill the card over months of uptime:
```bash
sudo sed -i 's/^#\?SystemMaxUse=.*/SystemMaxUse=50M/' /etc/systemd/journald.conf
sudo systemctl restart systemd-journald
```

**Permissions** — let your user read the button/mic and write the screen:
```bash
sudo usermod -aG input,video,render $USER
```
Then **log out and back in** for it to take effect:
```bash
exit
```
…and `ssh` back in.

**Checkpoint:** `groups` (Pi) lists `input video render`, and `timedatectl` shows
clock synchronized.

---

## Phase 4 — The 7" screen (the trickiest part)

The app draws directly to the framebuffer (`/dev/fb0`) at 1024×600, 32-bit. We tell
the Pi's firmware to use that exact mode, never blank, and keep the console off the
screen so only our status frames show.

**(Pi)** Edit the boot command line — it is **one single line**; append our tokens
to the **end of that same line** (do not add a new line):
```bash
sudo nano /boot/firmware/cmdline.txt
```
At the very end of the existing line, add a space then:
```
video=HDMI-A-1:1024x600-32@60D consoleblank=0 fbcon=map:1
```
Save in nano with **Ctrl-O, Enter**, then exit with **Ctrl-X**. Reboot:
```bash
sudo reboot
```
SSH back in after ~30s and confirm the framebuffer came up at the right size/depth:
```bash
cat /sys/class/graphics/fb0/virtual_size   # expect: 1024,600
cat /sys/class/graphics/fb0/stride         # expect: 4096  (1024 * 4 bytes)
```

**Checkpoint:** those two values are correct. If the screen is blank or garbled,
the **modeline** needs tuning for your exact panel — note your screen's model and
ask; this is the single most common bring-up snag and is expected to need one tweak.

---

## Phase 5 — The button

**(Pi)** Plug the button in (if not already), then list input devices by stable name:
```bash
ls /dev/input/by-id/
```
Find the entry for your button — something like
`usb-SomeVendor_SomeModel-event-kbd` or `...-event-if00`. Your **`BUTTON_GLOB`** is
that name with the variable tail replaced by a wildcard, e.g.:
```
/dev/input/by-id/usb-SomeVendor_SomeModel*-event*
```
Write the exact value down — it goes in the secrets file (Phase 9). If unsure which
entry is the button, run this and press it:
```bash
sudo apt install -y evtest && sudo evtest   # pick a device number, press the button, watch for events; Ctrl-C to quit
```

> ⚠️ **Multi-interface buttons.** Many cheap USB buttons enumerate as a *composite*
> HID device exposing several `-event-*` nodes (e.g. `-event-if03`, `-event-kbd`,
> `-if02-event-mouse`). A broad wildcard can grab the wrong one and the press never
> registers (the app starts, the screen shows `READY`, but pressing does nothing).
> If that happens, find which node actually fires — run `evtest` against each `-event-*`
> node and press the button; the one that prints a `KEY_*` event (value 1 on press) is
> the right one. Then set `BUTTON_GLOB` to that **exact** node, no wildcard, e.g.
> `BUTTON_GLOB=/dev/input/by-id/usb-5131_2019-event-kbd`. (The Blue-button MSR
> `5131:2019` fires `KEY_ENTER` on its `-event-kbd` node.)

**Checkpoint:** you have a `BUTTON_GLOB` string that matches your button.

---

## Phase 6 — The microphone

**(Pi)** Plug the USB mic in, then list capture devices:
```bash
arecord -L | grep -A1 plughw
```
You'll see lines like `plughw:CARD=ICE,DEV=0`. The **card name** (here `ICE`) is what
matters. The app matches the mic by a substring hint called **`MIC_HINT`** (default
`ice`, for the Blue Snowball iCE). If your mic's card name contains `ice` you can
leave the default; otherwise set `MIC_HINT` to a substring of your card name (Phase 9).

Quick capture test (records 5 seconds, then plays nothing — just checks it captures):
```bash
arecord -d 5 -f cd /tmp/mic-test.wav && ls -l /tmp/mic-test.wav
```

**Checkpoint:** the test file is created with non-zero size, and you know your
`MIC_HINT` (or are keeping the default `ice`).

---

## Phase 7 — AWS S3 (storage for the recordings)

Recordings are uploaded to a private S3 bucket (durable, and gives Fireflies a URL to
fetch). You need: a **bucket**, and an **IAM user** with keys scoped to *only* that
bucket. *(Ask me to do this part for you from my AWS access if you'd rather not —
it's a few CLI commands. Otherwise, in the AWS Console:)*

1. **S3 → Create bucket:** a unique name (e.g. `office-recorder-<yourname>`), region
   **eu-west-1**, **Block all public access = ON** (keep it private).
2. On the bucket, **Management → Lifecycle rule:** expire objects after **30 days**,
   and enable **"Delete incomplete multipart uploads after 1 day"** (cleans up
   crash-interrupted uploads).
3. **IAM → Users → Create user** (e.g. `office-recorder`), no console access. Attach an
   **inline policy** granting only put/get on this device's prefix:
   ```json
   {
     "Version": "2012-10-17",
     "Statement": [{
       "Effect": "Allow",
       "Action": ["s3:PutObject", "s3:GetObject"],
       "Resource": "arn:aws:s3:::YOUR_BUCKET/office-recorder-1/*"
     }]
   }
   ```
   (`office-recorder-1` is your `DEVICE_ID` from Phase 9 — keep them matching.)
4. **Create an access key** for that user → copy the **Access key ID** and **Secret
   access key** (you only see the secret once).

**Checkpoint:** you have a bucket name, region (`eu-west-1`), and the two AWS keys.

---

## Phase 8 — Fireflies API key

The Fireflies plan must be **paid** (the free tier can't accept audio uploads — this
is already confirmed for this project). Get the key from the Fireflies dashboard:
**Settings → Developer Settings → API Key** (copy it).

**Checkpoint:** you have a Fireflies API key.

---

## Phase 9 — The secrets file (on the Pi, never in the repo)

All secrets live in **one file at `/etc/office-recorder.env`**, readable only by you
(mode `600`). It is **outside** the git repo and never committed.

**(Pi)** create it:
```bash
sudo nano /etc/office-recorder.env
```
Paste this and fill in your real values:
```bash
FIREFLIES_API_KEY=your-fireflies-key
AWS_ACCESS_KEY_ID=your-aws-access-key
AWS_SECRET_ACCESS_KEY=your-aws-secret
AWS_REGION=eu-west-1
S3_BUCKET=your-bucket-name
DEVICE_ID=office-recorder-1
BUTTON_GLOB=/dev/input/by-id/usb-SomeVendor_SomeModel*-event*
# Optional overrides:
# MIC_HINT=ice
# TITLE_PREFIX=Office discussion
```
Save (Ctrl-O, Enter, Ctrl-X), then lock down permissions:
```bash
sudo chown $USER /etc/office-recorder.env
sudo chmod 600 /etc/office-recorder.env
```

**Checkpoint:** `ls -l /etc/office-recorder.env` shows `-rw-------` owned by you.

---

## Phase 10 — Install & run the app as a service

**(Pi)** Get the code and set up its environment:
```bash
sudo mkdir -p /opt/office-recorder && sudo chown $USER /opt/office-recorder
git clone https://github.com/swarnim-mudaliar/office-recorder.git /opt/office-recorder
cd /opt/office-recorder
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
```

Install the systemd service (it's a **template** unit; `@<user>` runs it as you):
```bash
sudo cp systemd/office-recorder@.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now office-recorder@$USER
```

Watch it start:
```bash
journalctl -u office-recorder@$USER -f
```

**Checkpoint:** the screen shows **READY**, and the journal shows the service running
with no errors. (Ctrl-C stops watching the log; the service keeps running.) It now
starts automatically on every boot.

---

## Phase 11 — Acceptance tests

Two "verify-early" checks the build flagged as the highest-risk:

1. **End-to-end record → transcript (the whole point):**
   - Press the button → screen shows **REC** + a running timer.
   - Speak for ~15 seconds, press again → screen returns to **READY** (or **Awaiting
     transcript**).
   - In the journal you should see `spooled` → `uploaded` → `submitted`, the local
     spool file gone, and an object in your S3 bucket under `office-recorder-1/...`.
   - Within a few minutes the transcript appears in your **Fireflies** account and the
     journal logs `confirmed`.
2. **Screen survives sleep:** leave it idle 15+ minutes → it must stay on (not blank).
   Boot once with the monitor off, then turn it on → an image should appear (if blank,
   the modeline needs tuning — Phase 4).

If both pass, the appliance is done.

---

## Handy commands

```bash
# live logs
journalctl -u office-recorder@$USER -f
# restart after a config change
sudo systemctl restart office-recorder@$USER
# stop / start
sudo systemctl stop office-recorder@$USER
sudo systemctl start office-recorder@$USER
# update to the latest code
cd /opt/office-recorder && git pull && sudo systemctl restart office-recorder@$USER
```
