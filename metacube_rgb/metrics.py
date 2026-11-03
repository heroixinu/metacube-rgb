"""Read-only Linux host telemetry. No subprocesses or firmware writes."""
from __future__ import annotations
import os
from pathlib import Path
import platform
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


def sensor_info():
    temperatures = []
    fans = []
    hwmon = Path('/sys/class/hwmon')
    for chip in sorted(hwmon.glob('hwmon*')):
        name = text(chip/'name','hwmon')
        for entry in sorted(chip.glob('temp*_input')):
            val = text(entry)
            try:
                value = round(int(val)/1000, 1)
            except (TypeError, ValueError):
                continue
            if -30 <= value <= 125:
                label = text(entry.with_name(entry.name.replace('_input','_label')),
                             f'{name} {entry.stem}')
                temperatures.append({'name': label, 'celsius': value})
        for entry in sorted(chip.glob('fan*_input')):
            value = text(entry)
            try:
                rpm = int(value)
                if 0 <= rpm <= 60000:
                    fans.append({'name':f'{name} {entry.stem}', 'rpm':rpm})
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
