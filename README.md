# MetaCube RGB v2.4.6 — OEM performance and button lighting enabled by default

The original Windows ControlCenter profile (`WMI 0x08`, Turbo=0 / Balanced=1 / Quiet=2) and independent button-light brightness (`WMI 0x19`, 0–3) are now available whenever **global `allow_writes=1`** is active. The extra `allow_platform_writes` opt-in has been removed from kernel and Web enforcement. Existing `allow_platform_writes` module parameters remain accepted as a deprecated compatibility setting, but no longer restrict OEM commands. Turbo still checks AC power and asks for confirmation in the Web UI, matching Windows. The EC continues to own automatic fan control; no direct fan RPM/PWM writer has been added.

**This release requires a signed DKMS upgrade to 2.3.1** (Web-only updates cannot remove the old driver's write restriction):

```bash
cd /root/metacube-rgb
git pull --ff-only
bash install.sh --enable-writes
metacube-rgb web restart
metacube-rgb profile
```

The existing global `allow_writes` policy is preserved by the installer when flags are omitted. Upgrading does not automatically change the active performance mode or the button-light brightness. As with the original OEM application, the actual effect of performance transitions should be verified on the M11-HPT host.

---

## Previous version v2.4.5 — hardware sensor identification

The System page now identifies temperatures by their actual Linux hwmon device paths, PCI addresses, NVMe controller models, and DDR5 SPD Hub SMBus addresses. It distinguishes Ryzen CPU Tctl, Radeon iGPU edge, ACPI thermal zone, KIOXIA and Solidigm SSDs (including P44 Pro auxiliary sensors), and two RTL8125 PHYs. Original Windows WMI `GET 0x14` main/small fan RPM channels remain read-only. Chinese-first module headings replace the prior all-caps overlines; raw sensor keys are retained in hover diagnostics. Exact physical chassis locations are **not inferred**. See [sensor source map](docs/HARDWARE_SENSOR_MAPPING.md). No driver/EC changes; upgrade with `bash install.sh --web-only`.

---

## v2.4.4 — OEM speed control and durable recovery

The lighting studio and CLI now allow **integer speed 0–10** as in the original Windows control center. Speed **2** is the only hardware-verified value on this HPT device; first Web speed change requires an explicit one-time (per browser session) warning confirmation. Changes still apply only after clicking **Apply**, never while sliding. An earlier unsupported speed operation left the ring dark until a complete AC power cycle; this risk has not been ruled out.

Before each real RGB WMI write, the Linux service atomically saves the current **full 32-byte GET readback plus validated RGB fields** to `/var/lib/metacube-rgb/rgb-history.json` (private mode 0600, latest 10). A backup error prevents the WMI SET. Recovery uses the validated 0x0F field writer, not arbitrary EC packets:

```bash
metacube-rgb history
metacube-rgb restore 1   # newest pre-write state; performs one real firmware write
```

To *opt back into* a locked speed slider, set `METACUBE_LOCK_SPEED_CUSTOMIZATION=1` for the Web service process/CLI. Fan and performance safeguards are unchanged. Hardware readback cannot prove visible LED light or recover a stuck EC; an AC power-cycle may still be required.

---

## Previous releases (historical behavior)

### v2.4.3 — RGB workbench layout

The RGB lighting page now uses a full-height two-row control workbench: lighting modes, OEM brightness/speed/direction/cycle/transition and a larger ring preview above; a wider 1–6 color/HSV editor and tabbed system/user preset center below. The preview always keeps the Apply button visible. Color editing and preset lists scroll only within their panels. Backend APIs, permissions and DKMS 2.3.0 remained unchanged in v2.4.3. Speed locking was subsequently changed in v2.4.4. `bash install.sh --web-only` on PVE.

---

# MetaCube RGB v2.4.2 — Restore full-height dashboard proportions

A layout correction to v2.4.1: the previous approach reduced component sizes while leaving unused space below the console. The new dashboard distributes its available viewport height to the RGB preview, preset library, performance and dual-fan panels, and host/event/resource column. It restores readable heading/button sizes and round preset thumbnails. Desktop dashboard fills from the status ribbon to the bottom edge without document scrolling at 1280×720 through 1920×1080. Other pages and mobile behavior remain unchanged. No firmware/driver/API changes; `bash install.sh --web-only` on PVE.

---

# MetaCube RGB Web v2.4.0 — compact hardware control console

Web/CLI-only visual redesign; kernel WMI DKMS remains **2.3.0**. Based on the selected orange/cyan dense dashboard concept, reuses existing OEM-protocol backend APIs and preserves current access-control gates.

- New overview command console: six live status tiles (device, RGB mode, brightness, main/small fan RPM, performance mode, AC supply); RGB ring simulation, mode/direction/brightness/transition draft controls and 1–6 color readout; system/user preset tiles; live fan charts; OEM performance modes; host/BIOS/system resource indicators and session-only operation history.
- All values on the live page are returned by the host (`/api/status`, `/api/system`, `/api/profile`, `/api/fans`, `/api/templates`, `/api/presets`). No manufactured fan/CPU/power event data. Session history is ephemeral and records only actions confirmed by this browser session, not daemon audit logs.
- Draft-only edits: clicking mode, brightness, direction or transition **never writes WMI automatically**. Only “应用到设备” or existing preset-specific immediate-apply actions send API writes; optimistic WMI readback check and speed=2 protection remain intact.
- No fan PWM controls added. OEM profile writes remain locked unless explicitly authorized on PVE. The full RGB/HSV editor, import/export, system profile controls and diagnostics stay available in their existing tabs.
- Responsive desktop/tablet/mobile layout. No external CSS/JS frameworks or assets.

Upgrade with `cd /root/metacube-rgb && git pull --ff-only && bash install.sh --web-only` (no DKMS rebuild). Restart an existing manually launched foreground Web process; systemd Web service is restarted by the installer if active.

The new console is browser-simulated and does not claim that the RGB display matches LED physical timing. Hardware status and command safety are unchanged.

---

# MetaCube RGB Web v2.3.1 — background service CLI (kernel module stays v2.3.0)

`metacube-rgb web` still starts the server in the foreground. On an installed PVE host, new systemd-backed commands control the existing service without unmanaged PID files or extra daemon processes:

```bash
metacube-rgb web start    # run in background, survive SSH logout; not boot-enabled automatically
metacube-rgb web status   # report active status, PID, boot enablement
metacube-rgb web restart # restart the managed service
metacube-rgb web stop    # stop the managed background service
metacube-rgb web          # previous foreground behavior remains available
```

`start` and `restart` display the existing Web Bearer token **only on an interactive terminal**, not in systemd logs or redirected output. For background service bind address/port, configure `/etc/default/metacube-rgb-web` (`METACUBE_WEB_HOST`, `METACUBE_WEB_PORT`) rather than passing `--host` or `--port` to `web start`. To start automatically **after reboot** as a separate opt-in: `systemctl enable metacube-rgb-web.service`; to cancel boot startup: `systemctl disable metacube-rgb-web.service`. All commands manage the already installed `metacube-rgb-web.service` and make **no RGB firmware writes**.

**Upgrade existing PVE:** `cd /root/metacube-rgb && git pull --ff-only && bash install.sh --web-only`. Stop any manually launched `metacube-rgb web` (Ctrl+C) before `metacube-rgb web start` to avoid port 8765 conflicts. Web/CLI v2.3.1 does not modify or rebuild DKMS v2.3.0.

Four-color `#0033AA / #0088FF / #00E5D4 / #8844FF` physical ring spin at `speed=2`, direction `0`, was confirmed by the owner on their MetaCube M11 after v2.3.0 was installed. Other speed values remain guarded due to the earlier LED output failure.

---

# MetaCube RGB v2.3.0 — OEM RGB brightness, profiles & fan telemetry

This build fixes two OEM parity gaps found in the user's Windows 2024 `玄机中枢.dll` IL: brightness uses a WPF 0..10 slider and encodes `min(level*26,255)`, while Turbo checks OS AC-online state via `GetSystemPowerStatus(LineStatus==1)`, not adapter connector type (`WMI 0x13 == 2`). Quiet/Balance/Turbo mode IDs remain 2/1/0. The Linux module now checks AC-online using `power_supply_is_system_supplied()` and only when explicit platform-write opt-in is enabled. The Web offers native brightness steps, active performance state, AC diagnostics, and non-invasive one-minute fan RPM trends. **No fan SET or PWM override exists in this release**: the original performance page provides only main/small RPM readouts, every 2s. See [OEM evidence and limits](docs/OEM_PERFORMANCE_FAN_PARITY.md).

Existing PVE DKMS 2.2.0 hosts must update the kernel module to 2.3.0 at a maintenance window (`git pull --ff-only && bash install.sh --enable-writes`). Do not enable platform writes by default. Verify with `metacube-rgb fans`, `metacube-rgb profile` and `modinfo -F version metacube_ambient`. Nonbaseline RGB animation speed remains locked by default following a physical LED outage.

---

# MetaCube RGB Web v2.2.0 - OEM speed and fan readout parity

- **RGB speed:** original WPF slider is **0..10** (initial UI value 3, integer step 1), not 0..255. Linux preserves `speed=2` as the default firmware-write safety limit because of the earlier LED freeze.
- **Fan RPM:** the Windows performance page shows **Main Fan** and **Small Fan** RPM, polling once every **2 seconds** using a model-specific read-only **GET 0x14** (two big-endian RPM values). Linux v2.2 adds the same readout to System Settings and `metacube-rgb fans`; if unavailable, it clearly labels a fallback generic `GET 0x0d` reading.
- **No manual fan control:** the supplied original Windows performance UI does not expose a fan PWM slider. This Linux release also performs **zero fan writes**; generic Bitland `0x14/0x15` SET behavior is not assumed safe for this M11 firmware.
- **DKMS module is now 2.2.0** for the OEM fan reader; Web-only updating remains supported with a clearly labeled fallback. See [OEM speed/fan audit](docs/OEM_SPEED_FAN_AUDIT.md).

Existing PVE installation: back up current settings, then `git pull --ff-only` and `bash install.sh --enable-writes` for DKMS 2.2.0, or `bash install.sh --web-only` if you wish to keep the installed 2.1.0 kernel driver (only fallback fan readings available).

## v2.1.3 historical release — LED ring preview, system templates, speed-only guard

Web-only update; DKMS kernel module remains 2.1.0.

- Preview the actual top-cover ring geometry with conic RGB gradients and mode-specific animation. This is a browser approximation.
- Spin, up to six colors, direction, cycle, transitions, and brightness remain available by default. As of v2.4.4, speed 0–10 is allowed by default; only speed 2 has been physically verified on HPT. To enforce a lock use `METACUBE_LOCK_SPEED_CUSTOMIZATION=1`.
- Four bundled immutable system themes, copied verbatim from the user-supplied JSON, are separate from five persistent user-defined preset slots.
- `GET /api/templates`, `POST /api/templates/apply`, `metacube-rgb template list`, `metacube-rgb template apply ID`.
- No hardware WMI changes. Host-only files can be installed with `bash install.sh --web-only`.

## Earlier v2.1.x releases (historical notes)

Independent Linux/PVE WMI RGB control center for **METAPHYUNI MetaCube M11 Series-HPT**, based on static analysis of the user-supplied Windows `ControlCenter` (.NET `玄机中枢`) application. **Not the OEM Windows driver.**

## Screenshots / 界面截图

> The overview screenshot is generated from **v2.4.0** with simulated device status and demo host metrics; other feature screenshots illustrate the still-available detailed editor and settings. No physical RGB hardware was controlled to create these images.

### Dashboard · Device overview

![MetaCube v2.4.0 dense orange-and-cyan command console with OEM RGB ring, presets and fans](docs/screenshots/overview.webp)

[Mobile layout preview](docs/screenshots/overview-mobile.webp)

### Lighting studio · Top-cover RGB ring preview

![Lighting studio showing multi-color rotating RGB ring, effect modes and color editor](docs/screenshots/lighting.webp)

### Built-in themes, user presets and system information

| System templates & user presets | System settings & host details |
| :---: | :---: |
| ![System lighting templates and personal RGB preset slots](docs/screenshots/presets.webp) | ![System settings and host information panel](docs/screenshots/system.webp) |

> The circular LED animation is a **browser simulation**, not a validated recording of the physical light controller. Speed is now adjustable over OEM integer range 0–10 (only 2 hardware-verified).

- **RGB first:** 4 ambient modes, 1–6 editable colors, exact RGB/HSV numeric controls, 0–255 brightness, speed, spin direction, cycle value 0–11, gradient transition, color ordering and mode-specific simulated previews.
- **Web:** `metacube-rgb web`, Bearer-token authentication, LAN access enabled by default (limit firewall exposure); WMI request preview, one-step undo and stale-state write protection.
- **Presets:** 5 local lighting presets, save/preview/apply separately, import/export validated JSON. OEM `.dat` files are **not compatible**.
- **Driver:** one WMI `0x0F` SET per complete RGB profile, GET readback validation, DKMS, existing MOK signing; no PVE kernel image/boot modifications.
- **Other OEM features:** Linux host metrics and explicit diagnostics; unsafe thermal/fan/GPU controls intentionally not writable by default.

**LED output incident (2026-11-04):** The owner observed RGB LEDs stop emitting light after changing rotation-effect speed, even though firmware GET returned valid updated settings. A complete power-down, unplugging AC, and restarting restored the previously saved blue breathing effect. The direct cause is unconfirmed. **Advanced RGB writes are therefore disabled by default in v2.1.2.** Only one-color `breath`, `steady`, `off`, and brightness/one-color changes with `speed=2 direction=0 cycle=0 transition=0` are allowed. Web shows an explicit warning and disables advanced effect controls. Local operators may intentionally opt in via `METACUBE_EXPERIMENTAL_RGB=1`, but this may require another cold power-cycle. OEM keyboard RGB WMI probes that produced `AE_NOT_FOUND` are also skipped by default. This protection is in Python/Web/CLI, not in the kernel driver; direct root sysfs writes remain possible.

## Install / Upgrade on PVE

Read the **[Chinese documentation](README.zh-CN.md)** and **[RGB hardware acceptance plan](docs/RGB_HARDWARE_TEST.md)** before enabling advanced effects.

```bash
apt update
apt install -y git dkms build-essential python3 mokutil proxmox-default-headers "proxmox-headers-$(uname -r)"
git clone https://github.com/heroixinu/metacube-rgb.git
cd metacube-rgb
bash install.sh --enable-writes
metacube-rgb web
```

If already cloned, use `git pull --ff-only` instead of cloning again. Web now listens on `0.0.0.0:8765`, prints detected reachable LAN URLs, and displays the Bearer token in an **interactive terminal**. Systemd output does not include credentials. To expose only your management address: `metacube-rgb web --host <PVE-LAN-IP>`. HTTP has **no transport encryption**: restrict TCP 8765 to trusted clients or use an HTTPS reverse proxy.

### Update only the Web application (existing 2.1.0 DKMS installations)

Stop an existing foreground `metacube-rgb web` with Ctrl+C, then:

```bash
cd /root/metacube-rgb
git pull --ff-only
bash install.sh --web-only
metacube-rgb web
```

The `--web-only` path does not uninstall, reload, rebuild or re-sign the kernel module. It updates Python/Web files and restarts the optional systemd Web service if it was already running. If `/etc/default/metacube-rgb-web` explicitly sets `METACUBE_WEB_HOST=127.0.0.1`, that override still takes priority; change it to `0.0.0.0` or your management IP first. To force displaying the token when stdout is redirected, use `--show-token` (the token may be saved in logs). Do not expose port 8765 to the internet.

```bash
# Creates a 32-byte SET preview but NEVER writes hardware:
metacube-rgb set --mode spin --colors FF0000 00FF00 --brightness 160 --speed 2 --direction 0 --cycle 6 --transition 1 --dry-run
# v2.1.2 deliberately BLOCKS the advanced write unless the host operator explicitly opts in.
# The dry-run preview never writes firmware.
```

**Hardware status:** Single-color, brightness, breathing and steady modes were physically verified. An advanced-effect speed operation was followed by loss of visible light until the machine was completely powered down and AC removed. Multi-color/spin/speed/cycle/transition behaviors are **not safely verified**. Reading firmware settings back does not prove physical LED timing or direction. The web's animation is illustrative only. Don't run experimental firmware writes while important VMs are active.

Project scope: [OEM capability matrix](docs/OEM_FEATURE_MATRIX.md) · [RGB validation](docs/RGB_HARDWARE_TEST.md) · [Changelog](CHANGELOG.md).

## License

Kernel driver: GPL-2.0-only; Python/Web components: MIT (see LICENSE). No proprietary OEM Windows binaries, firmware, images or third-party fonts are redistributed.

### v2.4.1 one-screen layout

Removed redundant page-level hero headings, condensed panels and status tiles, and rearranged RGB Studio and Performance/Fan management into dense modules. Mock Chromium checks confirm the main document fits the viewport (no vertical scroll) at desktop sizes from 1280×720 to 1920×1080; long HSV/preset lists scroll inside their own modules. Narrow/mobile layouts remain scrollable for legibility. Web-only upgrade; DKMS 2.3.0 is unchanged.
