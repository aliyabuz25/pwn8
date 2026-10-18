# remed1st

A macOS GTK application that jailbreaks **iPhone 4 GSM** (`iPhone3,1`) on **iOS 5.1.1** (build `9B208`).

Just connect your iPhone and click **Jailbreak** — as easy as evasi0n. remed1st ships its own untether package (`remed1st-untether5`) so no additional downloads or Cydia sources are required.

> Developed by [@aliyabuz25](https://github.com/aliyabuz25) — Special thanks to [@geohot](https://github.com/geohot), creator of limera1n.

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
4. The app handles everything: limera1n exploit → SSH ramdisk → activation patch → Cydia → untether → reboot

The phone is **not** restored or erased. No NOR or baseband is flashed. Cancelling at any point leaves the device in its current mode.

## What it does

- Runs the limera1n BootROM exploit via [ipwnder](https://github.com/dora2ios/ipwnder_lite)
- Boots a temporary SSH ramdisk to patch the system volume
- Applies the iOS 5.1.1 activation patch (lockdownd)
- Installs Cydia, CydiaSubstrate, OpenSSH and the untether
- Installs `remed1st-untether5` (v1.0.1) — the g1lbertJB-based untether package
- Verifies Cydia on the Home screen after reboot
- Sends a completion notification on the device

On an existing jailbreak: backs up affected files, reinstalls Cydia and the untether without touching the package database or installed tweaks.

## Validation

```sh
# Probe connected device (no GTK required)
./START.command --probe-json

# Read-only smoke test
./START.command --smoke-test 7

# Unit tests
python3 -m unittest discover -s tests -v
```

## Project structure

```
remed1st/
├── remed1st/        Python source
├── tests/           Unit tests
├── native/          C/ASM source for on-device helpers
├── assets/          SVG logo, compiled iOS ARM helpers
├── packages/        remed1st-untether5 DEB
├── downloads/       Archived limera1n (provenance only)
├── pyproject.toml
├── SETUP.command    Install dependencies
└── START.command    Launch the app
```

`runtime/` and `backups/` are generated at run time and are not tracked by git.

## Credits

- **[@geohot](https://github.com/geohot)** — limera1n BootROM exploit
- **[ipwnder_lite](https://github.com/dora2ios/ipwnder_lite)** — native Apple Silicon exploit backend
- **[Legacy-iOS-Kit](https://github.com/LukeZGD/Legacy-iOS-Kit)** — firmware tools, ramdisk, Cydia archives
- **[g1lbertJB](https://github.com/g1lbertJB/g1lbertJB)** — iOS 5.1.1 untether

## License

Source code is released as-is for educational and preservation purposes.
The bundled iOS firmware components and Cydia archives are property of their respective owners.
