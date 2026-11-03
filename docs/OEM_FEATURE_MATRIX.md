# Windows「玄机中枢」与 Linux MetaCube RGB Web v2.2 功能矩阵

本表基于用户上传的 Windows `ControlCenter.zip`（程序中的 .NET IL / WMI 调用）与 Linux 项目源码核对。设备为 `METAPHYUNI MetaCube / M11 Series-HPT`，ACPI/WMI GUID 为 `B60BFB48-3E5B-49E4-A0E9-8CFFE1B3434B`。

**三个不同的完成标准**：① 原厂协议字段已识别；② Linux 驱动/API/Web 已实现并经模拟环境测试；③ 用户的 PVE/MetaCube 实机物理灯效已经验收。前两者不能代替第三者。

## RGB 灯效：当前开发重点

| Windows OEM 控件或功能 | WMI 协议 | Linux v2.2 实现 | MetaCube 实机验证 |
|---|---|---|---|
| 机身氛围灯状态读取 | `0x0F` GET，32 字节 | 驱动、CLI、Web 状态显示、可重读 | **通过**：返回 `0080000f...` |
| 单色 RRGGBB | 颜色数 1，字节 6–8 | 颜色取色器、HEX、RGB/HSV 数值；`metacube-rgb color` | **通过**：原机颜色修改可见 |
| 呼吸模式 | 字节 4 = 2 | 模式按钮和 CLI | **通过**：已有机上模式设置反馈 |
| 常亮模式 | 字节 4 = 3 | 模式按钮和 CLI | **通过**：已有机上模式设置反馈 |
| 旋转模式 | 字节 4 = 4 | 模式按钮和 CLI | 待按方向、速度实机验收 |
| 关闭模式 | 字节 4 = 5 | 模式按钮和 CLI | 待单独实机验收 |
| 亮度 | 字节 24，0–255 | 拖动条、数值和 CLI；同时显示原厂界面近似档位 | **通过**：128 → 160，回读成功，需对照物理亮度 |
| 1–6 个颜色槽 | 字节 5 / 6–23 | 增删、排序、逐通道编辑，一次性 32 字节 SET | **单色通过，多色待实机验收** |
| 旋转速度 | 字节 25，原厂界面限制 0–10 | Web 滑块/数值和 CLI | 待实机验收速度与快慢方向 |
| 旋转方向 | 字节 26，0/1 | Web 顺/逆时针和 CLI | 待实机验收 |
| 颜色循环等级 | 字节 27，0–11 | Web 数值/下一级与 CLI | 待实机验收 12 档实际含义 |
| 渐变 / 平滑切换 | 字节 28，0/1 | Web 开关和 CLI | 待实机验收 |
| 五组预设 | 原厂本地数据文件 | Linux JSON 5 槽：保存草稿、载入编辑器、直接应用、导入导出 | 模拟 API/UI 测试通过；实机待验 |
| 设置预览 | 原厂 UI 光效视觉指示 | 浏览器本地模拟动画（旋转/呼吸等）和 WMI SET 数据包预检 | **模拟效果不能证明真实灯带运动速度** |
| RGB / HSV 输入 | OEM RGB/HSV 编辑 | HTML 色轮、HEX、RGB 0–255 与 HSV H0–360 S/V0–100 数值和滑块 | 浏览器模拟测试通过 |
| 开机光效恢复 | 原厂 Windows 服务/设备固件 | systemd 可选 + 文本预设 | 尚未在本机完整重启验收 |
| 多进程编辑冲突保护 | OEM 未确证 | Web `expected_raw` 冲突返回 409；可撤销上一次 Web 应用 | 模拟 API 测试通过 |

**已完成的含义**：Linux 侧覆盖原厂氛围灯编辑所需的已知协议字段与常用 UI 工作流；**没有声称高级光效通过实机验证**，也没有实现/导入 Windows 原厂二进制 `.dat` 预设。

## Windows 主页面的非 RGB 功能

| OEM 项目 | Linux v2.2 | 实机状态 |
|---|---|---|
| 静音 / 均衡 / Turbo | OEM `0x08` 读状态、二次解锁后允许写；Turbo 还要求确认圆口电源 | 写入未验，默认锁定 |
| 按键背光 0–3 | OEM `0x19` 读状态、二次解锁后允许写 | 写入未验，默认锁定 |
| 主风扇 / 小风扇 RPM | Web 系统页 2 秒只读刷新；优先 OEM GET `0x14` 大端解码，失败时标记通用 GET `0x0D` 回退 | 新增 Linux 实现；真实硬件读数待验 |
| CPU、GPU、内存、磁盘、网络、温度信息 | Linux 主机信息页面（并非 Windows OEM 所有传感器的逐项对应） | Linux 监测逻辑已实现 |

## Windows WMI 库存在、但未证实是本机 UI 能力的函数

| 编号 | 作用 | Linux 方案 |
|---|---|---|
| `0x09` | 独显/混显切换 | 只读可选探测，禁止切换 |
| `0x0B`, `0x0C` | Fn Lock / 触摸板 | 只读探测 |
| `0x10..0x12` | RGB 键盘模式/颜色/亮度 | 只读有限探测，未确认 MetaCube M11 存在相应硬件；不属于机身 RGB |
| `0x13` | 电源类型 | 只读，用于 Turbo 保护 |
| `0x14`, `0x15` | 通用 Bitland 文档将其用于风扇模式/手动控制；本机 Windows 原厂用 **GET 0x14** 读取主/小风扇 RPM | 本机仅允许 GET 0x14 读数，所有风扇写入仍禁止 |
| `0x16` | CPU 温度原始值 | 只读探测，缩放未校准 |
| `0x17` | CPU 功耗 | 禁止写入 |

## 32 字节机身氛围灯协议（WMI 0x0F）

| 偏移 | 含义 |
|---|---|
| 0..1 | `00 FA` GET / `00 FB` SET |
| 2..3 | `00 0F` 机身氛围灯 |
| 4 | 模式 2 呼吸、3 常亮、4 旋转、5 关闭 |
| 5 | 颜色数量 1..6 |
| 6..23 | 1..6 组 RGB，各 3 字节 |
| 24 | 亮度 0..255 |
| 25 | 旋转速度字段为单字节；**原厂 WPF 界面限制 0..10**，物理已知安全值 2 |
| 26 | 旋转方向 0/1 |
| 27 | 循环 0..11 |
| 28 | 渐变 0/1 |
| 29..31 | 原厂保留位；基于 GET 保存，不盲目写零 |

**固件 ACK 差异**：实机的 WMI SET 可能返回 `00000000` 非标准 ACK，但随后 GET 已证明部分属性的设置值生效。驱动仅发送一次 SET，并使用 GET 核对用户目标字段，不会因为非标准 ACK 就重复写入。

**安全边界**：面向 PVE 物理宿主机，不提供任意 WMI 数据包写入 API。性能和风扇/功率类操作不是 RGB 复刻的一部分，也没有因 UI 存在按钮就视为实机可用。详细手工测试请参见 [RGB_HARDWARE_TEST.md](RGB_HARDWARE_TEST.md)。

## v2.2 OEM speed / fan source correction

- The Windows WPF `SpinSpeedSlider` resource explicitly defines `Minimum=0`, `Maximum=10`, initial designer `Value=3`, `SmallChange=1`. The actual firmware still reports the speed byte directly (the tested working value was 2). The prior Linux UI 0..255 was **not OEM-parity** and has been corrected.
- Windows OEM performance-page `SetUI_FanSpeed` reads **GET 0x14**, interprets bytes 4/5 and 6/7 as **big-endian** main/small RPM, and refreshes every **2000 ms** only while the performance page is active.
- Generic upstream Bitland documentation instead describes **GET 0x0d** little-endian CPU/GPU/SYS RPM and `0x14/0x15` fan overrides on some models. Linux now exposes both variants read-only, marks which one actually supplied data, and does not assume generic write commands are safe for MetaCube M11.
- No manual fan PWM controls were identified in the supplied OEM performance UI. Fan control remains intentionally read-only; see [detailed investigation](OEM_SPEED_FAN_AUDIT.md).

## v2.3 OEM original source audit — RGB, fans and profiles

The following values come from the user-supplied `玄机中枢.dll` IL. They must not be extrapolated from other Bitland hardware.

| Original UI/control method | Windows original | Linux v2.3.0 | Remaining gap / risk |
|---|---|---|---|
| `SpinSpeedSlider` | 0–10 integer, initial *UI* default 3, writes OEM byte 25 only after commit | 0–10 preview, speed 2 default write lock | Other speed values previously followed by physical LED outage; not revalidated |
| `OverLightSlider` | 0–10 levels; `SetData_OverLight` multiplies by 26 and caps at 255 | Web now same 0–10 levels; CLI still 0–255 | Non-slider CLI values remain intentionally editable; preserved when editing other properties |
| Ambient modes | Breath 2, Steady 3, Spin 4, Off 5 | Matching WMI 0x0f flags | Multi-color rotational fidelity needs hardware acceptance |
| `SetUI_FanSpeed` | GET 0x14, main/small big-endian RPM, ~2s active-performance-page refresh | OEM GET preferred; generic fallback labeled; Web RPM trend based on same reads | M11 0x14 output not yet independently confirmed on PVE |
| Manual fan RPM/PWM | Not a visible user control in provided original WPF performance page | **Not exposed** | Generic Bitland 0x14/0x15 write semantics not hardware-proven for M11; do not send arbitrary SET |
| `QuietMode_Click` | mode 2, directly writes WMI 0x08 | mode 2, direct click after explicit authorization | Physical cooling response pending verification |
| `BalanceMode_Click` | mode 1, directly writes WMI 0x08 | mode 1, direct click after explicit authorization | Physical cooling response pending verification |
| `TurboMode_Click` | mode 0, AC online check + original confirmation | mode 0, Linux power_supply AC online + confirmation + explicit opt-in | More conservative than original by design |
| Button LED | WMI 0x19, levels 0–3 | Gated read/write and readback | Whether M11 has an independently controlled LED still unverified |

Full evidence and safe handling: [OEM performance and fan investigation](OEM_PERFORMANCE_FAN_PARITY.md).
