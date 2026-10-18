<div align="center">
  <img src="assets/remed-mark.svg" width="96" height="96" alt="remed1st"/>
  <h1>remed1st</h1>
  <p><strong>iPhone 4 GSM · iOS 5.1.1 jailbreak for macOS</strong></p>
  <p>
    <img src="https://img.shields.io/badge/iOS-5.1.1-blue" alt="iOS 5.1.1"/>
    <img src="https://img.shields.io/badge/iPhone-3G%20%2F%203GS%20%2F%204%20%2F%204S-lightgrey" alt="Devices"/>
    <img src="https://img.shields.io/badge/macOS-Apple%20Silicon%20%2B%20Intel-black" alt="macOS"/>
    <img src="https://img.shields.io/badge/exploit-limera1n-red" alt="limera1n"/>
  </p>
</div>

---

Just connect your iPhone and click **Jailbreak** — as easy as evasi0n. remed1st ships its own untether package (`remed1st-untether5`) so no additional downloads or Cydia sources are required.

> Developed by [@aliyabuz25](https://github.com/aliyabuz25) — Special thanks to [@geohot](https://github.com/geohot), creator of limera1n.

---

## How it works

remed1st runs the entire jailbreak pipeline automatically in one click:

1. **DFU** — guides you through DFU entry with a live countdown timer
2. **limera1n** — fires the BootROM exploit via [ipwnder](https://github.com/dora2ios/ipwnder_lite) (native Apple Silicon binary)
3. **gaster reset** — resets to clean pwned DFU so the boot chain starts fresh
4. **iBSS → iBEC** — loads patched bootloaders; iBEC is sent without the ECID selector to avoid a known USB drop on A4
5. **Ramdisk boot** — boots a temporary SSH ramdisk with an on-device progress screen (remed1st logo + stage captions)
6. **Activation patch** — applies the iOS 5.1.1 lockdownd patch atomically with checksum verification; the original is backed up
7. **Cydia bootstrap** — installs Cydia, CydiaSubstrate, OpenSSH and the untether to the system volume over SSH
8. **remed1st-untether5** — installs the built-in g1lbertJB-based untether package via dpkg after normal reboot
9. **Verification** — checks Cydia's real SpringBoard icon state; runs `uicache` as mobile if needed
10. **Notification** — sends a native iOS system dialog on the device confirming completion

### Stability features

- **ECID guard** — every irecovery command targets the exact device ECID; a swapped device is rejected immediately
- **Dual-path verification** — after limera1n, pwned status is confirmed via both ipwnder log (`pwned!`) and irecovery `PWND:` field; either alone is sufficient (mirrors Legacy-iOS-Kit logic)
- **No ECID selector in Recovery** — `irecovery -i ECID -f iBEC` drops the USB connection mid-transfer on A4; remed1st sends Recovery-mode files without the selector
- **USB re-enumeration** — a bundled macOS IOKit helper attempts target-only re-enumeration; never resets a hub or touches a different device
- **HFS integrity** — if the system volume cannot be mounted, fsck is run non-destructively first; repair only proceeds after a full raw snapshot is saved to `backups/`
- **Atomic patch** — lockdownd is uploaded, checksum-verified, then swapped in one `mv`; a failed checksum leaves the original untouched
- **Idempotent reinstall** — on an existing jailbreak, Cydia files and the package database are backed up before reinstall; the database and installed tweaks are preserved
- **Auto recovery exit** — if the device is detected in Recovery or DFU mode at idle (outside an active jailbreak), `irecovery -n` is sent automatically

---

## Requirements

- macOS (Apple Silicon or Intel)
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
git clone https://github.com/aliyabuz25/remed1st

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

The phone is **not** restored or erased. No NOR or baseband is flashed.

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
# Probe connected device (no GTK required)
./START.command --probe-json

# Read-only smoke test
./START.command --smoke-test 7

# Unit tests
python3 -m unittest discover -s tests -v
```

---

## Credits

- **[@geohot](https://github.com/geohot)** — limera1n BootROM exploit
- **[ipwnder_lite](https://github.com/dora2ios/ipwnder_lite)** — native Apple Silicon exploit backend
- **[Legacy-iOS-Kit](https://github.com/LukeZGD/Legacy-iOS-Kit)** — firmware tools, ramdisk, Cydia archives
- **[g1lbertJB](https://github.com/g1lbertJB/g1lbertJB)** — iOS 5.1.1 untether

## License

Source code is released as-is for educational and preservation purposes.
The bundled iOS firmware components and Cydia archives are property of their respective owners.
