# Original ControlCenter vs Linux MetaCube Web v2.0

Scope: files were inspected from the user-provided **ControlCenter.zip** installer (`玄机中枢.dll`, .NET IL), not inferred solely from the UI design. The device in the conversation identifies as `METAPHYUNI MetaCube / M11 Series-HPT`, and its WMI control GUID is `B60BFB48-3E5B-49E4-A0E9-8CFFE1B3434B`.

**Important**: this project is a functional Linux reimplementation. It does not run or package the OEM Windows service, WPF UI, OEM firmware, copyrighted image assets, or fonts.

## UI features in the OEM MainWindow

| OEM capability | Original program evidence | Linux Web v2.0 | Validation |
|---|---|---|---|
| Ambient light 4 modes | `WMIAmbientLightMode`, WMI `0x0F`, byte 4 | Web buttons + CLI `mode` | Single-mode WMI writes tested with v0.2/v1 |
| Ambient RGB | six color slots, byte 5 is count, bytes 6–23 colors | 1–6 editable colors, atomic apply | Single RGB tested; multi RGB not yet tested on real hardware |
| Brightness | byte 24 | slider and CLI | Tested on real hardware |
| Rotation speed | byte 25 | slider and CLI | Packet mapping inspected; not yet hardware tested |
| Spin direction | byte 26 (`0` clockwise, `1` counterclockwise) | segmented buttons + CLI | Packet mapping inspected; not yet hardware tested |
| Cyclic color | byte 27 (`0..11`) | slider and CLI | Packet mapping inspected; not yet hardware tested |
| Smooth transition | byte 28 (`0/1`) | toggle + CLI | Packet mapping inspected; not yet hardware tested |
| Color presets | five selectable, stored by OEM in local `dat` | five local saved slots, JSON in `/var/lib/metacube-rgb/presets.json` | Programmatically tested; OEM binary `.dat` is not imported |
| Quiet / Balance / Turbo | WMI `0x08`, values `2 / 1 / 0` | read/status, gated write buttons | Actual WMI write untested, disabled by default |
| Button backlight 0–3 | WMI `0x19`, values `0..3` | read/status, gated write buttons | Actual WMI write untested, disabled by default |
| CPU/GPU fan monitoring | `CPUGPUFanSpeed` WMI `0x0D` | Linux hwmon; OEM read-only probe | OEM read untested on this device |
| Hardware status | CPU, GPU, RAM, disk, network in OEM information library | CPU load, memory, system disk, CPU temperature, fans, host/DMI | Linux system metrics (not exact Windows hardware sensor bindings) |

## Additional function numbers in the OEM WMI library

These are present as enums or sample code; that is **not proof they are exposed as visible UI controls** in the installed OEM build:

| Function | OEM function | Linux Web v2.0 |
|---|---|---|
| `0x09` | Hybrid / discrete GPU mode | Read-only optional OEM probe; no GPU switching |
| `0x0B` | Fn Lock | Read-only optional probe |
| `0x0C` | Touchpad Lock | Read-only optional probe |
| `0x10` | RGB keyboard mode | Read-only optional probe |
| `0x11` | RGB keyboard color | Not queried; binary payload can vary across keyboards |
| `0x12` | RGB keyboard brightness | Read-only optional probe |
| `0x13` | AC adapter type | Read-only optional probe; required to positively confirm barrel adapter before Turbo |
| `0x14/0x15` | Max fan mode and maximum speed | Intentionally not exposed: safety-sensitive |
| `0x16` | OEM CPU thermometer | Read-only optional raw byte; scale not fully validated |
| `0x17` | CPU power limits / modes | Intentionally not exposed: safety-sensitive |

## WMI ambient packet (32 bytes)

| Offset | Meaning |
|---|---|
| 0..1 | operation, `00 FA` GET / `00 FB` SET |
| 2..3 | function, `00 0F` ambient |
| 4 | mode (2 Breath, 3 Steady, 4 Spin, 5 Off) |
| 5 | color count (1–6) |
| 6..23 | up to six RGB triples |
| 24 | brightness 0–255 |
| 25 | spin speed 0–255 |
| 26 | spin direction 0/1 |
| 27 | cycle 0–11 |
| 28 | gradient transition 0/1 |
| 29..31 | OEM-reserved / unmodified |

**SET ACK quirk:** On the tested machine, successful SET calls can return a zero-filled `00000000` header. The driver therefore sends one SET only and uses a separate GET to confirm the requested field. It never blindly assumes a zero ACK is a successful write.

**Hardware precautions:** Any new WMI command might have firmware side effects. Unlike a Windows application, this Linux package runs on the PVE host, potentially alongside business-critical VMs. Advanced RGB parameters are derived from OEM IL but not yet confirmed on this physical unit; platform controls require a *second* explicit opt-in. All GPU switching, manual fan, thermal and CPU power writes are intentionally unavailable.
