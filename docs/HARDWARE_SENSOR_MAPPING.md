# MetaCube M11 Series-HPT · 硬件温度与风扇来源对照

本表依据机主在 **2026-11-04** 提供的 `sensors -j`、`/sys/class/hwmon/*/device`、`lspci -nn`，以及已有原厂 Windows `玄机中枢.dll` 的 WMI 方法核对。温度来源于 Linux `hwmon`，风扇主/小通道来自原厂 WMI `GET 0x14`，**不是** Windows 原厂曾给出全部 Linux 传感器的物理安装图。

应用采用设备的 **sysfs 驱动、解析后的 PCI 地址、NVMe model、SMBus 地址**进行运行时识别，避免依赖可能随重启改变的 `hwmonN` 序号。

| 页面主标签 | Linux 原始来源 | 设备身份 / 位置能确认到什么程度 |
| --- | --- | --- |
| CPU 控制温度 | `k10temp-pci-00c3 / Tctl`，`00:18.3` | Ryzen 7 8845HS 的 CPU 热控制温度；**不是某一个核心温度** |
| 核显边缘温度 | `amdgpu-pci-c500 / edge`，`c5:00.0` | AMD Radeon 780M / 集成 GPU 边缘温度 |
| 平台热区温度 | `acpitz-acpi-0 / temp1` | ACPI `thermal_zone0` 的逻辑热区；不能据此叫“主板某一测温点” |
| 内存温度 · 0x50 | `spd5118-i2c-0-50 / temp1` | DDR5 SPD Hub，SMBus `0-0050`；实际插槽/方位未知 |
| 内存温度 · 0x51 | `spd5118-i2c-0-51 / temp1` | DDR5 SPD Hub，SMBus `0-0051`；实际插槽/方位未知 |
| KIOXIA 硬盘温度 | `nvme-pci-0200 / Composite` | PCI `02:00.0`，NVMe0，KIOXIA NVMe SSD 的复合温度 |
| Solidigm 硬盘温度 | `nvme-pci-0600 / Composite` | PCI `06:00.0`，NVMe1，Solidigm P44 Pro 的复合温度 |
| Solidigm 内部温度 1 | `nvme-pci-0600 / Sensor 1` | **同一块 P44 Pro** 内部 NVMe 温度探头 1；未确定是控制器还是 NAND |
| Solidigm 内部温度 2 | `nvme-pci-0600 / Sensor 2` | **同一块 P44 Pro** 内部 NVMe 温度探头 2；未确定是控制器还是 NAND |
| 有线网卡温度 · 03:00.0 | `r8169_0_300:00 / temp1` | PCI `03:00.0` Realtek RTL8125 2.5GbE，MDIO PHY 温度；**不等于物理网口 1** |
| 有线网卡温度 · 05:00.0 | `r8169_0_500:00 / temp1` | PCI `05:00.0` Realtek RTL8125 2.5GbE，MDIO PHY 温度；**不等于物理网口 2** |
| 主风扇 / 小风扇 | 原厂 Windows `SetUI_FanSpeed()`，WMI `GET 0x14` | 字节 4/5、6/7 大端，约 2 秒刷新；对应 **原厂固件通道名**，没有风扇机械位置或进出风方向的证据 |

## 界面展示规则

- 主标题优先展示 **中文的硬件类型 / 设备身份**，而不是 `Composite`、`Tctl`、`temp1_input` 等裸字符串。
- 芯片实际可定位到 PCI 设备、NVMe 型号、SMBus 地址，但**不能**凭总线地址推导机箱中的上下、前后、左右或第几号实体端口。
- 原始 `hwmon` 名称、传感器键与总线位置保留在 API 中，并在网页悬停详情中显示，以便排查驱动识别问题。
- 首屏先显示 CPU、核显、平台热区，后显示内存 / NVMe / 网卡等扩展指标。
- 风扇 RPM 坚持 OEM `GET 0x14` 优先，只读；**不增加风扇 PWM 写入**。若固件回退到 `GET 0x0D`，会明确提示通道不等同于原厂主/小风扇。

## 安全与兼容性

其他 HPT 或 PHX 主机的盘位、内存和网卡可能不同，页面应根据本机真实 sysfs 解析，不能写死 `hwmon4=KIOXIA`、`nvme1=Solidigm` 等规则。若 sysfs 无法确认型号，显示泛化名称和技术来源，不猜测。温度读数仅为监测，不因 UI 更新改变 EC 散热控制、RGB 或性能档位。
