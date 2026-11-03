"""Safe, allowlisted access to the MetaCube OEM WMI sysfs kernel module.

No direct ACPI method access or arbitrary-packet writing exists in this layer.
"""
from __future__ import annotations

import configparser
import hmac
import json
import os
from pathlib import Path
import re
import tempfile
import threading
from typing import Any

GUID = 'B60BFB48-3E5B-49E4-A0E9-8CFFE1B3434B'
WMI_DIR = Path('/sys/bus/wmi/devices') / GUID
MODULE_DIR = Path('/sys/module/metacube_ambient/parameters')
CONFIG = Path('/etc/metacube-rgb.conf')
PRESETS = Path('/var/lib/metacube-rgb/presets.json')
MODES = {'breath': 2, 'steady': 3, 'spin': 4, 'off': 5}
REV_MODES = {v: k for k, v in MODES.items()}
PERFORMANCE_MODES = {'turbo': 0, 'balanced': 1, 'quiet': 2}
OEM_READS = {
    'system_mode': ('oem_system_mode', {0:'turbo',1:'balanced',2:'quiet'}),
    'button_brightness': ('oem_button_brightness', None),
    'fans_rpm': ('oem_fan_rpm', None),
    'gpu_mode': ('oem_gpu_mode', {0:'hybrid',1:'discrete'}),
    'fn_lock': ('oem_fn_lock', {0:'off',1:'on'}),
    'touchpad_lock': ('oem_touchpad_lock', {0:'off',1:'on'}),
    'keyboard_mode': ('oem_keyboard_mode', {0:'off',1:'auto-cycle',2:'fixed',3:'custom'}),
    'keyboard_brightness': ('oem_keyboard_brightness', None),
    'ac_type': ('oem_ac_type', {1:'usb-c',2:'barrel'}),
    'cpu_temperature_raw': ('oem_cpu_temperature', None),
}
HEX = re.compile(r'^[0-9A-F]{6}$')
RAW = re.compile(r'^[0-9a-fA-F]{64}$')
LOCK = threading.RLock()

class MetaCubeError(Exception):
    pass


def number(value: Any, minimum: int, maximum: int, title: str) -> int:
    if isinstance(value, bool) or (isinstance(value, str) and not value.isascii()):
        raise MetaCubeError(f'{title} must be an integer {minimum}..{maximum}')
    try:
        result = int(value)
    except (TypeError, ValueError, OverflowError):
        raise MetaCubeError(f'{title} must be an integer {minimum}..{maximum}') from None
    if isinstance(value, float) and value != result:
        raise MetaCubeError(f'{title} must be an integer')
    if result < minimum or result > maximum:
        raise MetaCubeError(f'{title} must be {minimum}..{maximum}')
    return result


def color(value: str) -> str:
    if not isinstance(value, str):
        raise MetaCubeError('Color must be an RRGGBB hex string')
    value = value.removeprefix('#').upper()
    if not HEX.fullmatch(value):
        raise MetaCubeError('Color must be six hex digits, e.g. FF0000')
    return value


def normalize_lighting(payload: dict[str, Any], current: dict | None = None) -> dict:
    if not isinstance(payload, dict):
        raise MetaCubeError('Lighting parameters must be an object')
    allowed = {'mode', 'colors', 'color', 'brightness', 'speed',
               'direction', 'cycle', 'transition'}
    if set(payload) - allowed:
        raise MetaCubeError(f'Unknown lighting keys: {sorted(set(payload) - allowed)}')
    if 'colors' in payload and 'color' in payload:
        raise MetaCubeError('Specify colors or color, not both')
    baseline = current or {'mode':'breath', 'colors':['50DCFA'], 'brightness':160,
                           'speed':2, 'direction':0, 'cycle':0, 'transition':0}
    result = {key: baseline[key] for key in (
        'mode', 'colors', 'brightness', 'speed', 'direction', 'cycle', 'transition')}
    if 'mode' in payload:
        if payload['mode'] not in MODES:
            raise MetaCubeError('Mode must be breath, steady, spin or off')
        result['mode'] = payload['mode']
    if 'colors' in payload or 'color' in payload:
        colors = payload.get('colors', [payload['color']] if 'color' in payload else None)
        if not isinstance(colors, list) or not 1 <= len(colors) <= 6:
            raise MetaCubeError('Supply 1..6 colors')
        result['colors'] = [color(c) for c in colors]
    for key, maximum in [('brightness',255),('speed',255),('direction',1),
                         ('cycle',11),('transition',1)]:
        if key in payload:
            result[key] = number(payload[key], 0, maximum, key)
    return result


def _atomic_write(path: Path, content: str, mode=0o600):
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix='.metacube-', dir=path.parent)
    try:
        os.fchmod(fd, mode)
        with os.fdopen(fd, 'w', encoding='utf-8') as fh:
            fh.write(content)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


class Device:
    def __init__(self, wmi_dir: Path = WMI_DIR, module_dir: Path = MODULE_DIR):
        self.wmi_dir = Path(wmi_dir)
        self.module_dir = Path(module_dir)

    def _read(self, attr: str) -> str:
        try:
            return (self.wmi_dir / attr).read_text(encoding='ascii').strip()
        except OSError as exc:
            raise MetaCubeError(f'WMI read {attr} failed: {exc.strerror or exc}') from exc

    def _write(self, attr: str, value: str):
        try:
            (self.wmi_dir / attr).write_text(value+'\n', encoding='ascii')
        except OSError as exc:
            raise MetaCubeError(f'WMI write {attr} failed: {exc.strerror or exc}') from exc

    def flag(self, name: str) -> bool:
        try:
            return (self.module_dir / name).read_text().strip().upper() in ('Y','1')
        except OSError:
            return False

    def state(self) -> dict:
        raw = self._read('ambient_raw')
        if not RAW.fullmatch(raw):
            raise MetaCubeError('Unexpected WMI response length/format')
        data = bytes.fromhex(raw)
        if data[:4] != b'\x00\x80\x00\x0f':
            raise MetaCubeError('Unexpected WMI ambient response status')
        n = data[5]
        if n > 6:
            raise MetaCubeError(f'Unexpected RGB color count: {n}')
        return {
            'mode': REV_MODES.get(data[4], 'unknown'),
            'mode_number': data[4],
            'colors': [data[6+3*i:9+3*i].hex().upper() for i in range(n)],
            'color': data[6:9].hex().upper() if n else None,
            'color_count': n,
            'brightness': data[24],
            'speed': data[25],
            'direction': data[26],
            'cycle': data[27],
            'transition': data[28],
            'writable': self.flag('allow_writes'),
            'platform_writable': self.flag('allow_platform_writes'),
            'extended': (self.wmi_dir / 'ambient_apply').exists(),
            'raw': raw.lower(),
        }

    def lighting(self, changes: dict[str, Any]) -> dict:
        with LOCK:
            before = self.state()
            if not before['writable']:
                raise MetaCubeError('The WMI driver is read-only (allow_writes=N)')
            target = normalize_lighting(changes, before)
            if all(target[k] == before[k] for k in target):
                return before
            if before['extended']:
                line = ' '.join([
                    str(MODES[target['mode']]), str(target['brightness']),
                    str(target['speed']), str(target['direction']),
                    str(target['cycle']), str(target['transition']),
                    ','.join(target['colors']),
                ])
                self._write('ambient_apply', line)
            else:
                if (target['speed'] != before['speed'] or
                    target['direction'] != before['direction'] or
                    target['cycle'] != before['cycle'] or
                    target['transition'] != before['transition'] or
                    len(target['colors']) != 1):
                    raise MetaCubeError('Advanced effects require the v2.0 kernel module')
                if target['colors'] != before['colors']:
                    self._write('ambient_color', target['colors'][0])
                if target['brightness'] != before['brightness']:
                    self._write('ambient_brightness', str(target['brightness']))
                if target['mode'] != before['mode']:
                    self._write('ambient_mode', str(MODES[target['mode']]))
            after = self.state()
            mismatch = [key for key in target if after[key] != target[key]]
            if mismatch:
                raise MetaCubeError(f'Firmware readback mismatch: {", ".join(mismatch)}')
            return after

    def read_oem(self, selected=None) -> dict:
        # Explicit user request only. Never poll these WMI functions in the background.
        names = selected if selected is not None else list(OEM_READS)
        result = {}
        with LOCK:
            for name in names:
                if name not in OEM_READS:
                    raise MetaCubeError('Unknown OEM diagnostic')
                attr, mapping = OEM_READS[name]
                try:
                    value = self._read(attr)
                    if name == 'fans_rpm':
                        parts = value.split()
                        result[name] = {'cpu': int(parts[0]), 'gpu': int(parts[1])}
                    else:
                        parsed = int(value)
                        result[name] = {'value': parsed, 'label': mapping.get(parsed, 'unknown') if mapping else str(parsed)}
                except (MetaCubeError, ValueError, IndexError) as exc:
                    result[name] = {'unsupported': True, 'reason': str(exc)}
        return result

    def platform(self, control: str, value: Any) -> dict:
        mapping = {'system_mode': ('oem_system_mode', 2),
                   'button_brightness': ('oem_button_brightness', 3)}
        if control not in mapping:
            raise MetaCubeError('Only OEM system mode and button brightness are writable')
        attr, maximum = mapping[control]
        val = number(value, 0, maximum, control)
        if not (self.flag('allow_platform_writes') and self.flag('allow_writes')):
            raise MetaCubeError('OEM platform writes are locked; explicit driver opt-in required')
        with LOCK:
            self._write(attr, str(val))
            data = self.read_oem([control])[control]
            if data.get('value') != val:
                raise MetaCubeError(f'OEM {control} readback mismatch')
            return data


class Presets:
    def __init__(self, path: Path = PRESETS):
        self.path = Path(path)

    def read(self) -> list:
        if not self.path.exists():
            return [None] * 5
        try:
            data = json.loads(self.path.read_text(encoding='utf-8'))
            if not isinstance(data, dict) or not isinstance(data.get('slots'), list):
                raise ValueError('bad preset format')
            values = data['slots']
            if len(values) != 5:
                raise ValueError('bad preset count')
            return values
        except (OSError, ValueError) as exc:
            raise MetaCubeError(f'Invalid presets file: {exc}') from exc

    def update(self, slot: int, state: dict | None, name: str='') -> list:
        slot = number(slot, 1, 5, 'preset slot')
        if not isinstance(name, str) or len(name) > 36 or any(ord(c) < 32 for c in name):
            raise MetaCubeError('Invalid preset name (max 36 characters)')
        with LOCK:
            values = self.read()
            values[slot-1] = None if state is None else {
                'name': name or f'预设 {slot}',
                'lighting': normalize_lighting({key:state[key] for key in ('mode','colors','brightness','speed','direction','cycle','transition')}),
            }
            _atomic_write(self.path, json.dumps({'version': 1, 'slots': values}, ensure_ascii=False, indent=2)+'\n')
            return values

    def get(self, slot: int) -> dict:
        slot = number(slot, 1, 5, 'preset slot')
        found = self.read()[slot-1]
        if not found or 'lighting' not in found:
            raise MetaCubeError(f'Preset {slot} is empty')
        return normalize_lighting(found['lighting'])


def read_boot_config(path: Path = CONFIG) -> dict:
    if not path.is_file():
        raise MetaCubeError(f'Boot preset not found: {path}')
    config = configparser.ConfigParser(interpolation=None)
    config.read(path, encoding='utf-8')
    if not config.has_section('lighting'):
        raise MetaCubeError('Missing [lighting] section')
    sect = config['lighting']
    params = {'mode': sect.get('mode', 'breath'),
              'colors': [x for x in sect.get('colors', sect.get('color','50DCFA')).split(',')],
              'brightness': sect.get('brightness','160'),
              'speed': sect.get('speed','2'),
              'direction': sect.get('direction','0'),
              'cycle': sect.get('cycle','0'),
              'transition': sect.get('transition','0')}
    return normalize_lighting(params)


def save_boot_config(device: Device, path: Path = CONFIG):
    if os.geteuid() != 0:
        raise MetaCubeError('Saving the boot preset requires root')
    state = device.state()
    if state['mode'] not in MODES or not state['colors']:
        raise MetaCubeError('Cannot save unknown mode or empty color list')
    content = ('[lighting]\n'
               f'mode = {state["mode"]}\n'
               f'colors = {",".join(state["colors"])}\n'
               f'brightness = {state["brightness"]}\n'
               f'speed = {state["speed"]}\n'
               f'direction = {state["direction"]}\n'
               f'cycle = {state["cycle"]}\n'
               f'transition = {state["transition"]}\n')
    _atomic_write(path, content)
    return path
