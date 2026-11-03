# Changelog

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
