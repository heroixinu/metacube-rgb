"""Read-only Linux host telemetry. No subprocesses or firmware writes."""
from __future__ import annotations
import os
from pathlib import Path
import platform
import re
import shutil
import time


def text(path, default=None):
    try:
        return Path(path).read_text(errors='replace').strip()
    except OSError:
        return default


def cpu_model():
    info = text('/proc/cpuinfo','')
    for line in info.splitlines():
        if line.lower().startswith('model name'):
            return line.split(':', 1)[-1].strip()
    return platform.processor() or None


# Thermal labels are derived from the Linux hwmon driver AND its resolved
# device path. An hwmon index or unqualified "Composite" is not a device ID.
# Do not infer physical chassis locations, RAM slots, fan airflow, or SSD
# controller/NAND placement from these paths.
_PCI_BDF = re.compile(r'0000:([0-9a-fA-F]{2}:[0-9a-fA-F]{2}\.[0-7])')
_I2C_ADDR = re.compile(r'\b[0-9]+-00([0-9a-fA-F]{2})\b')


def _device_identity(chip: Path) -> tuple[Path, str | None]:
    device = chip / 'device'
    if device.exists():
        resolved = device.resolve()
    else:
        resolved = chip.resolve()
    matches = _PCI_BDF.findall(str(resolved))
    return resolved, matches[-1].lower() if matches else None


def _temperature_identity(chip_name: str, raw_label: str, device: Path,
                          pci: str | None) -> tuple[str, str, str, str]:
    """(Chinese title, human-readable source, category, confidence).

    Confidence refers to component identity, not to a precise physical spot.
    Raw kernel labels are kept separately for technical diagnostics.
    """
    raw = raw_label.strip()
    pci_suffix = f' · PCI {pci}' if pci else ''
    if chip_name == 'k10temp':
        if raw.lower() in ('tctl','tdie'):
            return ('CPU 控制温度' if raw.lower() == 'tctl' else 'CPU 芯片温度',
                    f'AMD k10temp · {raw}{pci_suffix}', 'core', 'verified-source')
        return ('CPU 温度', f'AMD k10temp · {raw}{pci_suffix}', 'core', 'verified-source')
    if chip_name == 'amdgpu':
        return ('核显边缘温度' if raw.lower() == 'edge' else '核显温度',
                f'AMD amdgpu · {raw}{pci_suffix}', 'core', 'verified-source')
    if chip_name == 'acpitz':
        return ('平台热区温度', 'ACPI 热区 · 非独立主板测温点', 'core', 'logical-zone')
    if chip_name == 'spd5118':
        address = _I2C_ADDR.search(str(device))
        addr = f'0x{address.group(1).upper()}' if address else '地址未知'
        return (f'内存温度 · {addr}',
                f'DDR5 SPD Hub · SMBus {device.name} · 物理插槽未确认',
                'memory', 'verified-source')
    if chip_name == 'nvme':
        model = text(device / 'model', '') or ''
        model = ' '.join(model.split())
        if model.lower().startswith('solidigm'):
            brand = 'Solidigm'
        elif model.upper().startswith('KIOXIA'):
            brand = 'KIOXIA'
        elif model:
            brand = model.split()[0]
        else:
            brand = 'NVMe'
        if raw.lower() == 'composite':
            title = f'{brand} 硬盘温度'
            sensor_kind = 'NVMe 复合温度'
        else:
            # NVMe Sensor 1/2 does not guarantee controller/NAND location.
            match = re.search(r'(\d+)$', raw)
            index = match.group(1) if match else ''
            title = f'{brand} 内部温度 {index}'.strip()
            sensor_kind = f'NVMe {raw}'
        return (title, f'{model or brand} · {sensor_kind}{pci_suffix}',
                'storage', 'verified-source')
    if chip_name.startswith('r8169'):
        location = pci or '未知'
        return (f'有线网卡温度 · {location}',
                f'Realtek 网卡 PHY · {raw}{pci_suffix} · 非物理网口序号',
                'network', 'verified-source')
    return ('其他硬件温度', f'{chip_name} · {raw}{pci_suffix}', 'other', 'unclassified')


def sensor_info(hwmon_root: Path | None = None):
    """Read temperatures/fans and attach sysfs-grounded component identities."""
    temperatures = []
    fans = []
    hwmon = Path(hwmon_root) if hwmon_root is not None else Path('/sys/class/hwmon')
    for chip in sorted(hwmon.glob('hwmon*')):
        name = text(chip / 'name', 'hwmon')
        device, pci = _device_identity(chip)
        for entry in sorted(chip.glob('temp*_input')):
            val = text(entry)
            try:
                value = round(int(val) / 1000, 1)
            except (TypeError, ValueError):
                continue
            if -30 <= value <= 125:
                raw = text(entry.with_name(entry.name.replace('_input', '_label')),
                           entry.stem)
                label, detail, category, confidence = _temperature_identity(name, raw, device, pci)
                temperatures.append({
                    'name': raw, 'label': label, 'detail': detail,
                    'category': category, 'confidence': confidence,
                    'source': name, 'pci': pci, 'sensor_key': entry.stem,
                    'celsius': value,
                })
        for entry in sorted(chip.glob('fan*_input')):
            value = text(entry)
            try:
                rpm = int(value)
                if 0 <= rpm <= 60000:
                    fans.append({'name': f'{name} {entry.stem}', 'rpm': rpm,
                                 'source': name, 'pci': pci})
            except (TypeError, ValueError):
                pass
    return temperatures[:30], fans[:16]


def gpu_info():
    """Best-effort DRM metrics. A vfio-pci-passed GPU may be absent on the PVE host."""
    results=[]
    for card in sorted(Path('/sys/class/drm').glob('card[0-9]*')):
        device=card/'device'
        vendor=text(device/'vendor')
        if not vendor:
            continue
        driver_link=device/'driver'
        driver=driver_link.resolve().name if driver_link.exists() else None
        busy=text(device/'gpu_busy_percent')
        try:
            busy_pct=float(busy) if busy is not None else None
            if busy_pct is not None and not 0 <= busy_pct <= 100:
                busy_pct=None
        except ValueError:
            busy_pct=None
        vram=text(device/'mem_info_vram_total')
        try:
            vram_total=int(vram) if vram is not None else None
        except ValueError:
            vram_total=None
        results.append({'device':card.name, 'vendor':vendor,
                        'pci_device':text(device/'device'), 'driver':driver,
                        'utilization_percent':busy_pct,'vram_total':vram_total})
    return results[:8]


def physical_network():
    """Only NICs with a physical device; excludes PVE tap/veth/vmbr interfaces."""
    items=[]
    for nic in sorted(Path('/sys/class/net').iterdir()):
        if nic.name == 'lo' or not (nic/'device').exists():
            continue
        status=text(nic/'operstate','unknown')
        if status not in ('up','unknown'):
            continue
        try:
            rx=int(text(nic/'statistics/rx_bytes','0'))
            tx=int(text(nic/'statistics/tx_bytes','0'))
        except ValueError:
            continue
        speed=text(nic/'speed')
        try:
            speed_mbps=int(speed)
            if not 0 < speed_mbps <= 800000:
                speed_mbps=None
        except (TypeError, ValueError):
            speed_mbps=None
        items.append({'interface':nic.name,'rx_bytes':rx,'tx_bytes':tx,
                      'speed_mbps':speed_mbps,'operstate':status})
    return items


class Sampler:
    def __init__(self):
        self._previous=None
        self._previous_net=None

    def cpu_percent(self):
        line = text('/proc/stat','').splitlines()[0:1]
        if not line:
            return None
        try:
            nums = [int(x) for x in line[0].split()[1:]]
            idle = nums[3] + (nums[4] if len(nums)>4 else 0)
            total = sum(nums)
        except (ValueError, IndexError):
            return None
        current=(idle,total)
        prev=self._previous
        self._previous=current
        if not prev or total <= prev[1]:
            return None
        return round(max(0,min(100,100*(1-(idle-prev[0])/(total-prev[1])))),1)

    def snapshot(self):
        cpu = self.cpu_percent()
        mem = {}
        for line in text('/proc/meminfo','').splitlines():
            if ':' in line:
                name,raw = line.split(':',1)
                try:
                    mem[name] = int(raw.strip().split()[0])*1024
                except (ValueError,IndexError):
                    pass
        mem_total=mem.get('MemTotal',0)
        mem_available=mem.get('MemAvailable',0)
        try:
            root=shutil.disk_usage('/')
            disk={'used':root.used,'total':root.total,'percent':round(root.used*100/root.total,1)}
        except OSError:
            disk=None
        temperatures,fans=sensor_info()
        load=text('/proc/loadavg','').split()
        try:
            uptime=int(float(text('/proc/uptime','0').split()[0]))
        except ValueError:
            uptime=0
        freq=None
        for path in ['/sys/devices/system/cpu/cpu0/cpufreq/scaling_cur_freq',
                     '/sys/devices/system/cpu/cpu0/cpufreq/cpuinfo_cur_freq']:
            value=text(path)
            if value and value.isdigit():
                freq=round(int(value)/1000000,2)
                break
        network_interfaces=physical_network()
        total_rx=sum(n['rx_bytes'] for n in network_interfaces)
        total_tx=sum(n['tx_bytes'] for n in network_interfaces)
        ts=time.monotonic()
        rx_rate=tx_rate=None
        if self._previous_net is not None:
            prior_ts, prior_rx, prior_tx=self._previous_net
            delta=ts-prior_ts
            if delta>0 and total_rx>=prior_rx and total_tx>=prior_tx:
                rx_rate=round((total_rx-prior_rx)/delta,1)
                tx_rate=round((total_tx-prior_tx)/delta,1)
        self._previous_net=(ts,total_rx,total_tx)
        cap_mbps=sum(n['speed_mbps'] or 0 for n in network_interfaces)
        network_percent=(round(min(100,8*(rx_rate+tx_rate)/1000000/cap_mbps*100),1)
                         if rx_rate is not None and tx_rate is not None and cap_mbps else None)
        gpus=gpu_info()
        gpu_percent=next((g['utilization_percent'] for g in gpus
                          if g['utilization_percent'] is not None),None)
        return {
            'timestamp':int(time.time()),
            'host':os.uname().nodename,
            'kernel':platform.release(),
            'dmi':{
                key:text('/sys/class/dmi/id/'+key) for key in
                ('sys_vendor','product_name','board_name','bios_version')},
            'cpu':{'model':cpu_model(), 'percent':cpu,'count':os.cpu_count(),
                   'frequency_ghz':freq, 'load':load[:3]},
            'memory':{'total':mem_total,'used':max(0,mem_total-mem_available),
                      'percent':round((1-mem_available/mem_total)*100,1) if mem_total else None},
            'disk':disk,
            'uptime_seconds':uptime,
            'temperatures':temperatures,
            'fans':fans,
            'gpu':{'devices':gpus, 'percent':gpu_percent},
            'network':{'interfaces':network_interfaces,'rx_bytes_per_second':rx_rate,
                       'tx_bytes_per_second':tx_rate, 'link_capacity_mbps':cap_mbps or None,
                       'percent':network_percent},
        }
