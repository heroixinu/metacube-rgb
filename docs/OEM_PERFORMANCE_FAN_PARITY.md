# MetaCube M11 Original Performance + Fan Behavior (2026-11-04)

Primary evidence: user-supplied 2024 `ControlCenter.zip` -> `玄机中枢.dll`, .NET IL method disassembly. This file describes observed OEM *behavior*, not copied source code or proof that other Bitland models share the same firmware.

| Windows method | Observed operation | Linux v2.3.0 |
|---|---|---|
| `QuietMode_Click` | `SetUI_SystemPerMode(2)` then `SetData_SystemPerMode(2)` | Quiet value 2; active selection read back |
| `BalanceMode_Click` | `SetUI_SystemPerMode(1)` then `SetData_SystemPerMode(1)` | Balance value 1; active selection read back |
| `TurboMode_Click` | `GetSP_IsAC()` checks Windows `GetSystemPowerStatus().LineStatus == 1`; absent AC -> `PowerTips` dialog; otherwise `FastestTipsDialog` confirmation unless `NeverTips` | AC status read via Linux `power_supply` class; confirm in Web; **separately requires module platform-write opt-in** |
| `SetData_SystemPerMode` | asynchronous `WMIUnKnow.SetValue(0x08, mode)` | kernel 0x08 SET (read-back checked) |
| `SetUI_FanSpeed` | asynchronous monitor on performance page; GET 0x14, big-endian main/small RPM, every 2000 ms | GET 0x14 or clearly labeled GET 0x0d fallback; refresh 2s on system page |
| Fan PWM edit | **No editable fan duty/speed widget or its call chain identified in the OEM main window** | No PWM/fan SET exposed: automatic EC fan control retained |
| `SetData_ButtonLightBrightness` | asynchronous WMI SET 0x19, byte 0..3 and saves current setting | gated WMI 0x19, 0..3; readback checked |

## Key fix relative to v2.2

v2.2 required `GET 0x13 == 2` (circular DC jack) for Turbo. That is **not what the M11 original Windows UI checks**; it checks only whether the OS considers external/AC power online. v2.3 checks Linux AC-online (`power_supply_is_system_supplied() == 1` in the kernel) and rejects unknown/offline supplies; Web separately previews AC state. This remains more conservative than the OEM because host operator must explicitly enable all platform writes through `--enable-platform-writes`.

### Why no manual fan sliders?

Bitland generic command `0x14` is also called `MaxFanSpeedSwitch` in common upstream documentation, and `0x15` can change manual duty on **some** models. This M11 OEM app instead **reads 0x14 as fan RPM**. Assuming the generic write semantics on this machine would be especially hazardous on a PVE host; making fan RPM user-editable without a proven hardware-specific safe transition back to automatic control is not OEM fidelity. Keep the M11's EC fan curve autonomous.

No hardware WMI commands are emitted by tests. Performance profile SET is opt-in only. `metacube-rgb profile` and `/api/profile` are read-only.

Upstream reference: https://docs.kernel.org/wmi/devices/bitland-mifs-wmi.html

## v2.4.6 current policy (supersedes earlier opt-in description)

The standalone `allow_platform_writes` gate was removed for Windows-confirmed `0x08` performance and `0x19` button-light controls. These writes now require the same global `allow_writes=1` permission as RGB. The legacy module option remains accepted for compatibility but has no effect on these writes. Turbo retains its original AC-online precondition and Web confirmation. No fan PWM write support is added. The 2.3.1 DKMS module must be installed; a Web-only update does not change the older kernel gate.
