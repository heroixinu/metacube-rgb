# Changelog

## 2.4.5 — source-aware hardware sensor labels and Chinese-first monitoring UI

- Categorize Linux hwmon temperatures by resolved PCI/sysfs paths and device drivers, not changing `hwmonN` indices; identify KIOXIA/Solidigm NVMe SSDs from the actual controller `model`, DDR5 SPD hubs from SMBus addresses, and both Realtek NIC PHYs by PCI address.
- Display human-readable Chinese names for CPU control temperature, AMD iGPU edge, ACPI thermal zone, memory modules, NVMe composite/internal sensors and network PHY; preserve original Linux key and device path as hover diagnostics. Do not guess physical port, RAM slot, or NVMe sensor element position.
- Match original Windows firmware `main/small` dual-fan names and read-only GET 0x14 behavior; replace the system page’s all-caps English overlines and English fan-source note with concise Chinese while keeping protocol details available.
- Keep full-screen console height; internal hardware-sensor region scrolls on shorter displays without introducing document scrolling. No WMI writes, fan controls or DKMS changes.
- Add sysfs simulator unit tests and Chromium hardware monitor layout checks. See `docs/HARDWARE_SENSOR_MAPPING.md`.


## 2.4.4 — Original OEM 0–10 speed control and durable RGB history

- Speed customization is enabled by default with validated OEM integer bounds 0–10; speed 2 remains the only known-good physical setting.
- First speed change in Web requires a session-scoped warning confirmation. Sliders still stage drafts; WMI is only written when Apply is requested. Admin override `METACUBE_LOCK_SPEED_CUSTOMIZATION=1` retains the old lock if desired.
- Write-ahead backup of complete 32-byte firmware GET state and normalized fields for every RGB change (up to 10 snapshots, private persistent JSON), with `metacube-rgb history` and `metacube-rgb restore [1..10]` CLI commands.
- No changes to the DKMS driver, fan-control restrictions, or platform-mode safeguards.

## v2.4.3 — 2026-11-04 · RGB full-height workbench layout

- Reorganize the RGB tab into a two-row layout: mode / OEM parameters / larger ring preview on top, wide color editor / tabbed presets below. Unlike earlier attempts to force one-screen content, allocate the viewport to the modules and scroll only expanding color/HSV rows and preset lists internally.
- Consolidate the speed safety notice, draft state, discard/undo and WMI packet inspector into one compact toolbar. The Apply button remains visible inside the preview panel, with a four-field draft summary (mode, color count, brightness, firmware speed).
- Merge immutable system templates and five user presets into an accessible tabbed library, preserving every existing ID, preview/import/export/save/delete/apply action, backend route and firmware-write guard. Switching tabs does not write firmware.
- Add Chromium mock-only interaction and layout tests at six desktop resolutions, including checks for a visible Apply button, color editor, WMI inspector, active preset pane, and zero WMI writes until explicit Apply.
- No hardware protocol / EC control / DKMS modifications. Install using `bash install.sh --web-only`; WMI driver remains 2.3.0.

## v2.4.2 — 2026-11-04

- Fix v2.4.1 dashboard over-compression: first viewport now fully utilized rather than stopping at ~80% height and leaving large empty space below.
- Preserve the selected orange/cyan visual design and existing card grouping. Restore legible KPI, module header, mode, palette, and performance control sizing; dynamically allocate screen height across dashboard sections.
- Preset thumbnail ring remains circular on shorter desktop viewports; session event empty state is centered instead of floating at the top of an empty box.
- Add Chromium regression assertions for bottom-edge coverage, non-clipped main apply action, readable headings, and circular preset rings at desktop sizes. Firmware, DKMS, WMI protocol and API unchanged.

## 2.4.0 — compact orange/cyan MetaCube control console

- Redesign overview as a high-information-density hardware command center with circular RGB lighting simulation, synchronized draft inputs, user/system presets, dual-fan RPM trends, OEM mode readout and real host resource / firmware info.
- Session-local event log shows only successful interactions; no fabricated metrics or historical events.
- Existing Web APIs and device protocol remain unchanged. All edits stage as draft until explicit apply; speed=2 default guard, EC auto-fan control, and OEM performance-write opt-in remain enforced.
- Add desktop/mobile Chromium console smoke test (mock WMI) and preserve legacy RGB editor tests.
- Web/Python v2.4.0; DKMS remains 2.3.0. Upgrade using `bash install.sh --web-only`.

## 2.3.1 — systemd-backed Web lifecycle commands

- Add `metacube-rgb web start / stop / restart / status`, backed by the installed `metacube-rgb-web.service` instead of forking a root-owned ad-hoc process. Existing `metacube-rgb web` foreground invocation is unchanged.
- Show the existing token only in the operator's interactive terminal on start/restart; omit credentials from service logs, redirected output, and status.
- Prevent using foreground-only `--host`, `--port`, `--demo`, `--token-file`, `--show-token` options for managed background actions; configure `/etc/default/metacube-rgb-web` instead.
- Add mocked systemctl unit tests. `bash install.sh --web-only` deploys the extra Python module without rebuilding DKMS v2.3.0.
- Owner confirms physical four-color ring rotation at `speed=2` in v2.3.0; keep speed customization locked by default.

## 2.3.0 — Windows WPF OEM alignment (RGB / performance / fans)

- True WPF brightness 0–10 slider, byte mapping `min(level*26,255)`; preserve existing precise raw brightness if no slider input.
- Re-align Turbo's AC check from WMI adapter connector type to Windows `LineStatus == 1` / Linux supplied state.
- Add read-only `metacube-rgb profile` and `/api/profile` (current mode / AC status / write-gate information).
- Active mode + AC status in Web; Quiet/Balance direct like OEM; Turbo requires AC and confirmation; opt-in writes remain gated at kernel level.
- One-minute in-memory fan RPM sparklines using the existing 2-second GET; no fan PWM commands or extra WMI calls.
- Fix installer predecessor detection for 2.2.0 and uninstall target version; add source-based OEM profile audit.
- Hardware acceptance pending. DKMS 2.3.0 build required for updated Turbo gate.

# Changelog

## 2.4.5 — source-aware hardware sensor labels and Chinese-first monitoring UI

- Categorize Linux hwmon temperatures by resolved PCI/sysfs paths and device drivers, not changing `hwmonN` indices; identify KIOXIA/Solidigm NVMe SSDs from the actual controller `model`, DDR5 SPD hubs from SMBus addresses, and both Realtek NIC PHYs by PCI address.
- Display human-readable Chinese names for CPU control temperature, AMD iGPU edge, ACPI thermal zone, memory modules, NVMe composite/internal sensors and network PHY; preserve original Linux key and device path as hover diagnostics. Do not guess physical port, RAM slot, or NVMe sensor element position.
- Match original Windows firmware `main/small` dual-fan names and read-only GET 0x14 behavior; replace the system page’s all-caps English overlines and English fan-source note with concise Chinese while keeping protocol details available.
- Keep full-screen console height; internal hardware-sensor region scrolls on shorter displays without introducing document scrolling. No WMI writes, fan controls or DKMS changes.
- Add sysfs simulator unit tests and Chromium hardware monitor layout checks. See `docs/HARDWARE_SENSOR_MAPPING.md`.


## 2.2.0 - OEM speed & two-fan monitor alignment

- Reverse-inspected the supplied Windows WPF BAML and IL: animation-speed slider is **0..10**, initial UI value 3, integer step 1. Updates a draft on mouse-up; actual WMI SET is performed only on explicit Apply.
- Match browser/CLI input range 0..10 while keeping **speed=2** as the default firmware-write limit following the owner's LED failure incident.
- Implement original Windows *read-only* main/small fan RPM monitor: 2 second polling on the system/performance page, WMI **GET 0x14** with big-endian two-channel decoding (DKMS 2.2.0).
- Retain safe fallback to earlier `GET 0x0d` little-endian readings; label its source and stop retrying an OEM ACPI method after an unsupported response.
- Add `GET /api/fans` and `metacube-rgb fans`, zero fan SET/PWM controls.
- Keep previous five user presets intact; out-of-range legacy speed values are represented as safe speed 2 in memory without silently rewriting the original JSON file.
- Source comparison and hardware limitations in [OEM_SPEED_FAN_AUDIT.md](docs/OEM_SPEED_FAN_AUDIT.md).

## v2.1.3 (Web/CLI only; kernel v2.1.0)

- Visualize the real MetaCube top-cover **LED ring**, with conic gradients and mode-dependent ring animations (breath/steady/spin/off).
- Restore spin, multiple colors, direction, cycle and transition to default writable behavior; keep only animation speed fixed to `2` without explicit administrator override.
- Add four read-only system templates sourced from supplied JSON, separate from existing five user presets.
- New read/apply system template API and CLI; `--web-only` installer now ships the bundled catalog.
- Add tests for speed-only safety and system-template isolation.


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

## v2.4.1 — One-screen compact control pages

- Removed repeated oversized hero/heading copy from Dashboard, RGB Studio, Performance/Fans and OEM Diagnostics. The top bar now holds the live connection/sync status and a diagnostics shortcut.
- Reduced UI padding, panel headers, metric tiles and RGB preview chrome; reorganized Performance/Fans into a compact two-column grid and split the advanced RGB Studio into concise color, effect, preview, and preset modules.
- Targeted zero **document** vertical/horizontal scrolling at desktop viewports 1920×1080, 1672×941, 1440×900, 1366×768, and 1280×720; long color/preset lists retain their own bounded scrollbars to keep every action accessible. Mobile/narrow screens remain naturally scrollable for readability.
- Made the optional raw WMI packet inspector a floating panel to avoid growing the page height.
- UI and CLI-only update; DKMS driver remains 2.3.0. No new WMI write operations or fan-control changes.
