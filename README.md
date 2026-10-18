<div align="center">
  <img src="assets/remed-mark.svg" width="96" height="96" alt="remed1st"/>
  <h1>remed1st</h1>
  <p><strong>iPhone 4 GSM · iOS 5.1.1 jailbreak for macOS &amp; Linux</strong></p>
  <p>
    <img src="https://img.shields.io/badge/iOS-5.1.1-blue" alt="iOS 5.1.1"/>
    <img src="https://img.shields.io/badge/iPhone-3G%20%2F%203GS%20%2F%204%20%2F%204S-lightgrey" alt="Devices"/>
    <img src="https://img.shields.io/badge/macOS-Apple%20Silicon%20%2B%20Intel-black" alt="macOS"/>
    <img src="https://img.shields.io/badge/Linux-x86__64%20%2F%20ARM-orange" alt="Linux"/>
    <img src="https://img.shields.io/badge/exploit-limera1n-red" alt="limera1n"/>
  </p>
</div>

---

Just connect your iPhone and click **Jailbreak** — as easy as evasi0n. remed1st ships its own untether package (`remed1st-untether5`) so no additional downloads or Cydia sources are required.

> Developed by [@aliyabuz25](https://github.com/aliyabuz25) — Special thanks to [@geohot](https://github.com/geohot), creator of limera1n.

---

## Why remed1st

### One click. No configuration.

Other tools (greenpois0n, redsn0w, Sn0wbreeze) require multiple manual steps, Windows-only interfaces or outdated 32-bit binaries that no longer run on modern hardware. remed1st runs natively on Apple Silicon and modern Linux, detects your device automatically and handles the entire pipeline with a single button press.

| | remed1st | greenpois0n | redsn0w | Sn0wbreeze |
|---|---|---|---|---|
| Apple Silicon native | ✅ | ❌ | ❌ | ❌ |
| One-click jailbreak | ✅ | ❌ | ❌ | ❌ |
| Built-in untether | ✅ | ❌ | ❌ | ❌ |
| No IPSW required from user | ✅ | ❌ | ❌ | ❌ |
| Preserves tweaks on reinstall | ✅ | ❌ | ❌ | ❌ |
| Brick protection | ✅ | ❌ | ❌ | ❌ |
| Activation patch included | ✅ | ❌ partial | ❌ | ❌ |
| Live on-device progress screen | ✅ | ❌ | ❌ | ❌ |

### Brick protection

remed1st is designed so that a failure at **any stage cannot brick your device**:

- The system volume is never modified without a verified ramdisk SSH connection
- `lockdownd` is uploaded, checksum-verified, then swapped atomically with `mv` — a failed transfer leaves the original file untouched
- Before any jailbreak files are overwritten on an existing installation, a full backup is saved to `backups/` on your Mac; if the backup fails or is incomplete, reinstallation is blocked
- If the root HFS volume cannot be mounted, `fsck` is run read-only first; repair only proceeds after a full raw disk snapshot is saved
- A failed or partial backup is marked `.incomplete` so it is never mistaken for a clean snapshot
- The device is never flashed at the NOR or baseband level — only the user-accessible iOS volume is modified
- Cancelling at any point leaves the device in its current mode; no partial write is committed

### What it does automatically that others don't

- **Auto recovery exit** — if your device gets stuck in Recovery mode (e.g. after a failed boot), remed1st detects it and sends `irecovery -n` automatically; you don't need to manually exit
- **Activation patch** — applies the iOS 5.1.1 lockdownd activation patch so the phone works without an active carrier contract; greenpois0n skips this on some builds
- **Existing jailbreak detection** — if Cydia is already installed, remed1st backs up your jailbreak files and reinstalls Cydia + the untether without touching your package database or installed tweaks
- **Built-in untether** — `remed1st-untether5` (v1.0.1) is bundled and installed via dpkg after reboot; no Cydia source or internet connection required on the device
- **On-device progress screen** — the remed1st logo and stage captions (Injecting Payload → Preparing Filesystem → Applying Untether → Installing Cydia → Rebooting) are displayed on the iPhone screen during the ramdisk boot
- **Completion notification** — a native iOS system dialog appears on the device after successful Cydia icon verification

---

## How it works

remed1st runs the entire pipeline automatically:

1. **DFU** — guides you through DFU entry with a live countdown timer; detects DFU automatically if already entered
2. **limera1n** — fires the BootROM exploit via [ipwnder](https://github.com/dora2ios/ipwnder_lite) (native Apple Silicon binary)
3. **gaster reset** — resets to clean pwned DFU so the boot chain starts fresh every time
4. **iBSS → iBEC** — loads patched bootloaders; iBEC is sent without the ECID selector to avoid a known USB drop on A4
5. **Ramdisk boot** — boots a temporary SSH ramdisk with on-device progress screen
6. **Activation patch** — applies the iOS 5.1.1 lockdownd patch with checksum verification; original is backed up
7. **Cydia bootstrap** — installs Cydia, CydiaSubstrate, OpenSSH and the untether over SSH
8. **remed1st-untether5** — installs the built-in untether package via dpkg after normal reboot
9. **Verification** — checks Cydia's real SpringBoard icon; runs `uicache` as mobile if needed
10. **Notification** — sends a native iOS system dialog confirming completion

### Stability features

- **ECID guard** — every irecovery command targets the exact device ECID; a swapped device is rejected immediately
- **Dual-path pwn verification** — after limera1n, confirmed via both ipwnder log (`pwned!`) and `irecovery -q PWND`; either alone is sufficient
- **No ECID selector in Recovery** — `irecovery -i ECID -f iBEC` drops the USB connection mid-transfer on A4; remed1st detects and avoids this
- **USB re-enumeration** — a bundled macOS/Linux IOKit helper attempts target-only re-enumeration; never resets a hub
- **Idempotent reinstall** — on an existing jailbreak, database and tweaks are preserved

---

## Requirements

- macOS (Apple Silicon or Intel) or Linux (x86\_64 / ARM)
- [Legacy-iOS-Kit](https://github.com/LukeZGD/Legacy-iOS-Kit) installed as a **sibling directory**:
  ```
  iPhone4Downgrade/
  ├── remed1st/        ← this repo
  └── Legacy-iOS-Kit/  ← required sibling
  ```
- Legacy-iOS-Kit must have the iOS 5.1.1 IPSW and firmware keys for `iPhone3,1 / 9B208` already downloaded
- iPhone 4 GSM connected via USB

## Setup

```sh
# 1. Clone both repos side by side
git clone https://github.com/LukeZGD/Legacy-iOS-Kit
git clone https://github.com/aliyabuz25/pwn8

# 2. Install dependencies
cd remed1st
./SETUP.command

# 3. Launch
./START.command
```

`KUR.command` and `BASLA.command` are Turkish aliases for the above.

## Usage

1. Connect iPhone 4 via USB
2. Click **Jailbreak**
3. Follow the on-screen DFU instructions when prompted
4. Done — Cydia will be on your Home screen

The phone is **not** restored or erased. No NOR or baseband is flashed. Cancelling at any point leaves the device in its current mode.

---

## Project structure

```
remed1st/
├── remed1st/        Python source
├── tests/           Unit tests (38 tests)
├── native/          C/ASM source for on-device helpers
├── assets/          SVG logo, compiled iOS ARM helpers
├── packages/        remed1st-untether5 DEB
├── downloads/       Archived limera1n (provenance only)
├── pyproject.toml
├── SETUP.command    Install dependencies
└── START.command    Launch the app
```

`runtime/` and `backups/` are generated at run time and are not tracked by git.

## Validation

```sh
./START.command --probe-json   # probe connected device (no GTK)
./START.command --smoke-test 7 # read-only UI smoke test
python3 -m unittest discover -s tests -v
```

---

## Credits

- **[@aliyabuz25](https://github.com/aliyabuz25)** — stabilized and toolized the entire pipeline into a single reliable application; designed the GUI, device detection, boot asset pipeline, SSH ramdisk integration, activation patch, untether packaging, on-device progress screen, Cydia setup and completion notification
- **[@geohot](https://github.com/geohot)** — limera1n BootROM exploit
- **[ipwnder_lite](https://github.com/dora2ios/ipwnder_lite)** — native Apple Silicon exploit backend

## License

Source code is released as-is for educational and preservation purposes.
The bundled iOS firmware components and Cydia archives are property of their respective owners.
