## v2.1.3 (Web/CLI only; kernel v2.1.0)

- Visualize the real MetaCube top-cover **LED ring**, with conic gradients and mode-dependent ring animations (breath/steady/spin/off).
- Restore spin, multiple colors, direction, cycle and transition to default writable behavior; keep only animation speed fixed to `2` without explicit administrator override.
- Add four read-only system templates sourced from supplied JSON, separate from existing five user presets.
- New read/apply system template API and CLI; `--web-only` installer now ships the bundled catalog.
- Add tests for speed-only safety and system-template isolation.

# Changelog

## 2.1.2 — Firmware LED output incident: experimental RGB safeguard

- Default-lock unverified spin, multicolor, non-default speed/direction/cycle/transition writes for CLI/Web/presets/boot-restore; local opt-in `METACUBE_EXPERIMENTAL_RGB=1`.
- Keep proven single-color breath/steady/off/brightness controls operational.
- Prevent known unsupported OEM keyboard RGB WMI diagnostics by default to reduce ACPI AE_NOT_FOUND probing.
- Web shows guarded controls and explicit firmware-write eligibility, while dry-run remains available.
- No kernel driver changes; DKMS remains at 2.1.0. Physical LEDs had stopped emitting despite valid readback, and recovered only after a complete power disconnect.

## 2.1.1 — LAN Web startup hotfix (DKMS module remains 2.1.0)

- Default `metacube-rgb web` bind address is now `0.0.0.0:8765`, with detected PVE LAN URLs shown on launch.
- Interactive terminal sessions show the full existing Bearer token immediately; systemd/non-TTY logs hide the secret unless `--show-token` is explicitly requested.
- Support explicit `--host <LAN-IP>` for single-interface binding; warn about unencrypted LAN HTTP.
- Add `bash install.sh --web-only` for upgrades that do not rebuild, reload or replace the already working kernel module.
- Add unit tests for default/overridden listeners, LAN address discovery and token output policy.


## 2.1.0 — RGB Studio parity & safety

- Compared original Windows `玄机中枢` ambient lighting IL functions with Linux WMI `0x0F` packet mapping.
- RGB editor: 1–6 colors, per-color RGB and HSV **numeric** inputs and sliders, color ordering, exact hex, 4 modes, brightness, speed, direction, cycle 0–11, transition.
- Mode-distinct browser **simulations** (not firmware timing calibration) and separation between preview draft and actual host LED status.
- Five local presets: save pending draft without firmware writes, load to editor, direct apply, import/export versioned JSON and schema validation.
- Safe firmware workflow: optional raw-state preconditions (HTTP 409 on stale settings), one-step undo, 32-byte WMI SET preview that never sends firmware commands.
- Atomic `metacube-rgb set ... [--dry-run]`; CLI preset import/export.
- Driver WMI failure path frees ACPI output buffers. Driver protocol and safety opt-in unchanged.
- Installer can replace installed v1.0 or v2.0 DKMS on current kernel; does not touch MOK keys or PVE boot config.
- Replaced outdated source-regenerating `build_driver.py` with an immutable build wrapper.
- 25 Python unit/API tests, plus optional mock-Chromium UI interaction smoke test. Compiled against Debian 13 6.12 headers; **PVE 7.0 / MetaCube v2.1 physical effects not verified**.

## 2.0.0

- Initial native Web control center, multi-color 32-byte WMI ambient apply, gated OEM system diagnostics, hardware metrics and DKMS support.
