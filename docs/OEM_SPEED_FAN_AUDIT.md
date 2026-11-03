# MetaCube M11 OEM RGB speed and fan-speed implementation audit

Evidence: the owner-supplied Windows `ControlCenter.zip`, unpacked `玄机中枢.dll` (.NET WPF program dated 2024-11-14), its embedded WPF BAML resources, and Linux Bitland MIFS documentation. This is a behavioral compatibility analysis, not a redistribution of OEM source or binaries.

## RGB animation speed: the exact OEM UI

| Feature | Decompiled OEM behavior | Linux v2.2.0 |
| --- | --- | --- |
| Speed widget | WPF `SpinSpeedSlider` | HTML range input |
| Minimum / maximum | WPF BAML `Minimum=0`, `Maximum=10` | `min=0`, `max=10` |
| Initial UI value | WPF BAML `Value=3` (not necessarily actual hardware state) | Reads firmware value, defaults to known-safe speed `2` if locked |
| Step | WPF BAML `SmallChange=1` and mouse-up rounds to integer | `step=1` |
| Apply semantics | `SpinSpeedSlider_MouseLeftButtonUp` calls `SetData_SpinSpeed`; this only updates byte 25 of `_ambient_prams`. `SetLightModify_Sure` later sends one WMI SET | Browser edits draft only; explicit Apply issues WMI SET |
| Wire value | Direct byte, no multiplying/dividing or PWM conversion | Direct byte, 0..10 in app; firmware still accepts a byte |
| Safety | OEM UI has no special protection for this PVE failure | Only speed 2 writable by default; administrator opt-in required for 0..10 alternatives |

The WPF speed widget initially displays **3**, while the user's working physical device was read back at **2**. These are two different facts. The browser prioritizes the actual firmware value and the known-safe setting, not the designer's initial WPF value.

**Incident:** changing speed with the previous Linux 0..255 slider was followed by the LEDs turning dark, although GET echoed the configured data. An AC power disconnect and full reboot restored light. The cause is not proven to be the numeric speed alone. An HTTP/browser preview must not be treated as physical firmware validation.

## Fan RPM: what the actual Windows program does

`MainWindow.SetUI_FanSpeed` starts an asynchronous monitor while `_PerfPageIsChecked`. The async code:

1. Invokes `WMIUnKnow.GetValue` with numeric method ID **20 (0x14)**.
2. Decodes the main fan RPM as `(OutData[4] << 8) | OutData[5]`.
3. Decodes the small fan RPM as `(OutData[6] << 8) | OutData[7]`.
4. Updates the WPF text fields `MainFanSpeed` and `SmallFanSpeed` with the `RPM` suffix.
5. Waits **2000 ms**, then repeats until cancellation or the performance page is no longer active.

This version of the original UI displays **two fan RPM readouts**. No user-facing manual fan speed slider or PWM duty-cycle writer was found in this program's performance-page path. The mere presence of enum `MaxFanSpeed = 21` does **not** prove there is a UI that writes it. An additional Windows `SystemUsage.getFanusage` method observes NVIDIA GPU fan RPM through LibreHardwareMonitor, which is not the same thing as controlling the EC fans.

## Difference from the generic Bitland protocol

Linux kernel documentation describes a generic `GET 0x0d` method returning CPU/GPU/SYS fan speeds in little-endian format; it describes `0x14` as the max-fan switch and `0x15` as a manual duty control for some models. Therefore, **the same command ID may have different read semantics on different OEM firmware**. The supplied Windows program is the primary basis for the MetaCube M11 compatibility path.

- Linux v2.2.0 adds a **read-only** DKMS sysfs attribute `oem_fan_rpm_oem` using **GET 0x14**, big-endian main/small decoding, with no SET counterpart.
- `GET /api/fans`, `metacube-rgb fans` and the Web System Settings page prefer it when plausible, refreshing every 2 seconds only while that page is open.
- When unsupported (method failure, non-RPM flag response), the app falls back to existing **GET 0x0d** little-endian CPU/GPU readings and prominently labels them as a *generic fallback*, not exact OEM main/small channels.
- If an OEM reader is unsupported, the Web process caches the failure instead of invoking the same failing ACPI method every 2 seconds. Restarting the service retries discovery.
- There is **no EC fan control writer, no automatic PWM override and no fan policy modification** in this release. The original application's fan monitor does not justify sending generic `0x14/0x15` SET calls on a Proxmox host.

References:
- https://docs.kernel.org/wmi/devices/bitland-mifs-wmi.html
- https://www.spinics.net/lists/platform-driver-x86/msg62277.html (proposed Linux thermal-control patch; not proof of MetaCube M11 support)
- https://github.com/torvalds/linux/blob/master/drivers/platform/x86/bitland-mifs-wmi.c

## Other differences that remain

- Windows uses local `.dat` preset files; Linux has five portable JSON user slots and four immutable bundled system themes.
- The WPF UI displays custom performance and monitoring data; Linux displays host metrics, which cannot access a PCIe GPU passed through to a VM.
- Original Windows WMI uses an OEM-specific performance-mode enumeration: Turbo=0, Balance=1, Quiet=2. Generic Bitland documentation describes other mode enumerations for other machines; do not transplant generic values onto the M11 blindly.
- The LED ring is a browser simulation; true physical gradient profile/timing/direction remains to be checked on the MetaCube hardware.
- Only the known-safe animation speed=2 is writable by default. Browser/admin opt-in can unlock numeric 0..10; this is an explicit divergence from the unprotected OEM WPF UI due to the observed hardware incident.

## Safe PVE acceptance steps

First update Web only (no DKMS change) to see fallback generic fan readings:

```bash
cd /root/metacube-rgb
git pull --ff-only
bash install.sh --web-only
metacube-rgb fans
```

For the exact OEM reader, use a maintenance window to upgrade DKMS from 2.1.0 to 2.2.0 (still **read only** for fans):

```bash
cd /root/metacube-rgb
bash install.sh --enable-writes
dkms status -m metacube-ambient
modinfo -F version metacube_ambient
modinfo -F signer metacube_ambient
metacube-rgb fans
```

If `source` is `metacube_oem_0x14`, the OEM read command returned plausible values. Physical fan RPM agreement is still unverified. If the firmware returns `bitland_0x0d_fallback`, do not present it as exact OEM parity. The UI must never offer PWM controls based on this readback alone.

No command in this document writes a fan setting or asks the user to disable Secure Boot.
