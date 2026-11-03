# MetaCube RGB Web v2.0.0

A Linux/PVE native control center for METAPHYUNI MetaCube M11 Series-HPT, based on static analysis of the user-provided OEM Windows ControlCenter application. Read the **[Chinese README](README.zh-CN.md)** for installation commands and operating instructions. Full OEM-feature comparison: [docs/OEM_FEATURE_MATRIX.md](docs/OEM_FEATURE_MATRIX.md).

## Main features

- `metacube-rgb web` starts a token-authenticated dark-mode local Web UI.
- 4 ambient modes; 1–6 RGB colors; brightness, effect speed, spin direction, cycling level, and transition; single SET + readback validation.
- 5 persistent local lighting presets.
- Read-only Linux hardware telemetry; explicit OEM WMI diagnostics.
- Quiet / Balanced / Turbo and 4-level button backlight behind separate write opt-in; some OEM capabilities deliberately remain read-only for safety.
- DKMS kernel builds, existing Secure Boot MOK signing, optional systemd startup and boot lighting restore.

**Hardware testing status**: OEM RGB mode, single color, brightness and SET/GET readback have been tested on the actual MetaCube using v0.2/v1.0. Newly implemented v2 advanced effects and platform settings are derived from the original program but **NOT yet physically verified**. Do not modify firmware settings while important PVE virtual machines are running.

## Quick install

```sh
apt update
apt install -y dkms build-essential python3 mokutil proxmox-default-headers "proxmox-headers-$(uname -r)"
unzip metacube-rgb-web-v2.0.0.zip
cd metacube-rgb-web-v2.0.0
bash install.sh --enable-writes
metacube-rgb web
```

The web server listens on `127.0.0.1:8765` by default. Read `/etc/metacube-rgb/web.token` locally for authentication; SSH forwarding is recommended. `systemctl enable --now metacube-rgb-web.service` is optional. The web server is never automatically exposed to the Internet.

## License

This independently developed code is provided as source under GPL-2.0-only for the kernel module and MIT for the Python/Web components (see LICENSE). OEM application binaries and proprietary assets are not redistributed.
