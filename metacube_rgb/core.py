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

# The unit recovered after an AC power cycle when changing the experimental
# animation speed caused the LEDs to go dark. Keep default speed=2 for firmware
# writes. Other RGB controls are user-requested but not all hardware-validated.
# METACUBE_EXPERIMENTAL_RGB=1 remains as a backwards-compatible local override.
SAFE_RGB_SPEED = 2
UNSAFE_OEM_READS = {'keyboard_mode', 'keyboard_brightness'}


def experimental_rgb_enabled() -> bool:
    """Only the local service administrator may unlock custom speed values."""
    return (os.environ.get('METACUBE_ALLOW_SPEED_CUSTOMIZATION') == '1' or
            os.environ.get('METACUBE_EXPERIMENTAL_RGB') == '1')


def rgb_experimental_reasons(target: dict) -> list[str]:
    """Only nonbaseline animation speed is gated. Spin/multicolor remain usable."""
    return ([f'speed={target["speed"]} (default locked to {SAFE_RGB_SPEED})']
            if target['speed'] != SAFE_RGB_SPEED else [])


def enforce_rgb_safety(target: dict):
    reasons = rgb_experimental_reasons(target)
    if reasons and not experimental_rgb_enabled():
        raise MetaCubeError(
            'Custom RGB animation speed is locked: ' + ', '.join(reasons) +
            '. Restore speed=2, or opt in locally with '
            'METACUBE_ALLOW_SPEED_CUSTOMIZATION=1. '
            'Changing speed previously left LEDs dark until an AC power cycle.'
        )
    return reasons

class MetaCubeError(Exception):
    pass


class MetaCubeConflict(MetaCubeError):
    """The WMI configuration changed since the editor loaded its baseline."""
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
    for key, maximum in [('brightness',255),('speed',10),('direction',1),
                         ('cycle',11),('transition',1)]:
        if key in payload:
            result[key] = number(payload[key], 0, maximum, key)
    return result


def build_ambient_set_packet(raw: str, payload: dict) -> str:
    """Deterministic 32-byte OEM SET preview; never sent to hardware here.

    Generated from a current GET, preserving OEM-reserved bytes 29..31.
    The kernel driver independently constructs the actual WMI request.
    """
    if not isinstance(raw, str) or not RAW.fullmatch(raw):
        raise MetaCubeError('Expected a 32-byte WMI GET response')
    packet = bytearray.fromhex(raw)
    if packet[:4] != bytes.fromhex('0080000f'):
        raise MetaCubeError('Unexpected WMI GET header')
    lighting = normalize_lighting(payload)
    packet[0:4] = bytes.fromhex('00fb000f')
    packet[4] = MODES[lighting['mode']]
    packet[5] = len(lighting['colors'])
    packet[6:24] = bytes.fromhex(''.join(lighting['colors'])).ljust(18, b'\0')
    packet[24:29] = bytes(lighting[field] for field in ('brightness','speed','direction','cycle','transition'))
    return packet.hex()


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
    def __init__(self, wmi_dir: Path = WMI_DIR, module_dir: Path = MODULE_DIR,
                 power_root: Path = Path('/sys/class/power_supply')):
        self.wmi_dir = Path(wmi_dir)
        self.module_dir = Path(module_dir)
        self.power_root = Path(power_root)
        self._fan_oem_probe_failed = False  # avoid repeated unsupported ACPI calls
        self._fan_generic_probe_failed = False

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
            'rgb_experimental_enabled': experimental_rgb_enabled(),
            'speed_customization_enabled': experimental_rgb_enabled(),
            'raw': raw.lower(),
        }

    def lighting(self, changes: dict[str, Any], expected_raw: str | None = None) -> dict:
        with LOCK:
            before = self.state()
            if expected_raw is not None and before['raw'] != expected_raw:
                raise MetaCubeConflict('Firmware RGB settings changed after editing began. Refresh before applying.')
            if not before['writable']:
                raise MetaCubeError('The WMI driver is read-only (allow_writes=N)')
            target = normalize_lighting(changes, before)
            if all(target[k] == before[k] for k in target):
                return before
            enforce_rgb_safety(target)
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
                    raise MetaCubeError('Advanced effects require the v2+ kernel module')
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

    @staticmethod
    def _decode_fan_pair(value: str):
        parts = value.strip().split()
        if len(parts) != 2:
            raise ValueError('Expected two OEM fan RPM readings')
        values = [int(x) for x in parts]
        # An unsupported fan-control switch may return 0/1 rather than RPM.
        # Never display these as real fan rotations; try the generic reader.
        if not all((v == 0 or 200 <= v <= 18000) for v in values) or max(values) < 200:
            raise ValueError('Invalid/ambiguous fan RPM values (possible firmware flags)')
        return values

    def fans(self) -> dict:
        """Read-only OEM fan telemetry, preserving model-specific provenance.

        WMI GET 0x14 on this model uses big-endian main/small values (driver
        handles this). Generic Bitland WMI GET 0x0d is a fallback, using
        little-endian CPU/GPU channels. Never issue a fan WMI SET.
        """
        with LOCK:
            warning = ''
            oem = self.wmi_dir / 'oem_fan_rpm_oem'
            if oem.exists() and not self._fan_oem_probe_failed:
                try:
                    main, small = self._decode_fan_pair(self._read('oem_fan_rpm_oem'))
                    return {'available':True, 'main_rpm':main, 'small_rpm':small,
                            'source':'metacube_oem_0x14', 'poll_seconds':2,
                            'manual_control':False,
                            'note':'OEM GET 0x14 / big-endian, original Windows main/small channels'}
                except (MetaCubeError, ValueError) as exc:
                    self._fan_oem_probe_failed = True
                    warning = f'OEM 0x14 unavailable: {exc}; '
            elif self._fan_oem_probe_failed:
                warning = 'OEM 0x14 probe failed earlier; skipped future ACPI calls; '
            else:
                warning = 'OEM 0x14 reader requires DKMS 2.2.0; '
            if self._fan_generic_probe_failed:
                return {'available':False, 'main_rpm':None, 'small_rpm':None,
                        'source':'unavailable', 'poll_seconds':2,
                        'manual_control':False,
                        'note':warning+'Generic 0x0d probe also failed; skipped further ACPI calls until restart'}
            try:
                main, small = self._decode_fan_pair(self._read('oem_fan_rpm'))
                return {'available':True, 'main_rpm':main, 'small_rpm':small,
                        'source':'bitland_0x0d_fallback', 'poll_seconds':2,
                        'manual_control':False,
                        'note':warning+'Generic GET 0x0d CPU/GPU values; labels are not verified as OEM main/small'}
            except (MetaCubeError, ValueError) as exc:
                self._fan_generic_probe_failed = True
                return {'available':False, 'main_rpm':None, 'small_rpm':None,
                        'source':'unavailable', 'poll_seconds':2,
                        'manual_control':False,
                        'note':warning+f'Generic GET 0x0d unavailable: {exc}'}

    def read_oem(self, selected=None) -> dict:
        # Explicit user request only. Never poll these WMI functions in the background.
        names = selected if selected is not None else list(OEM_READS)
        result = {}
        with LOCK:
            for name in names:
                if name not in OEM_READS:
                    raise MetaCubeError('Unknown OEM diagnostic')
                if name in UNSAFE_OEM_READS and os.environ.get('METACUBE_EXPERIMENTAL_OEM_READS') != '1':
                    result[name] = {'unsupported': True, 'reason': 'Firmware ACPI AE_NOT_FOUND observed for OEM RGB diagnostics; read disabled by default'}
                    continue
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

    def ac_status(self) -> dict:
        """OEM Windows GetSystemPowerStatus(LineStatus == 1) equivalent.

        Only adapter 'Mains' and 'USB' power supplies exposing online=0/1
        are counted; missing/ambiguous sysfs status stays UNKNOWN. No WMI.
        """
        found = []
        try:
            supplies = sorted(self.power_root.iterdir())
        except OSError:
            supplies = []
        for supply in supplies:
            try:
                kind = (supply / 'type').read_text(encoding='ascii').strip()
                if kind not in ('Mains', 'USB', 'USB_C', 'USB_PD', 'USB_PD_DRP'):
                    continue
                status = (supply / 'online').read_text(encoding='ascii').strip()
                if status not in ('0','1'):
                    continue
                found.append({'name':supply.name,'type':kind,'online':status=='1'})
            except OSError:
                continue
        if not found:
            return {'ac_online':None, 'source':'linux_power_supply',
                    'adapters':[], 'note':'AC online state unavailable; Turbo blocked'}
        return {'ac_online':any(x['online'] for x in found),
                'source':'linux_power_supply', 'adapters':found,
                'note':'Matches OEM LineStatus == 1 check; current firmware mode remains authoritative'}

    def profile_status(self) -> dict:
        """OEM performance selection and AC precondition; no WMI writes."""
        profile = self.read_oem(['system_mode'])['system_mode']
        ac = self.ac_status()
        return {'profile':profile, 'power':ac,
                'write_enabled':self.flag('allow_platform_writes') and self.flag('allow_writes'),
                'available_modes':PERFORMANCE_MODES,
                'turbo_available': ac['ac_online'] is True,
                'manual_fan_speed_supported':False}

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
            if control == 'system_mode' and val == PERFORMANCE_MODES['turbo']:
                if self.ac_status()['ac_online'] is not True:
                    raise MetaCubeError('Turbo requires AC online (OEM GetSystemPowerStatus LineStatus == 1)')
            self._write(attr, str(val))
            data = self.read_oem([control])[control]
            if data.get('value') != val:
                raise MetaCubeError(f'OEM {control} readback mismatch')
            return data


class Presets:
    """Five OEM-style local preset slots; data only, never executable packets."""
    KEYS = {'mode', 'colors', 'brightness', 'speed', 'direction', 'cycle', 'transition'}

    def __init__(self, path: Path = PRESETS):
        self.path = Path(path)

    @classmethod
    def validate_slots(cls, slots: Any, allow_legacy_speed=False) -> list:
        if not isinstance(slots, list) or len(slots) != 5:
            raise MetaCubeError('Exactly 5 preset slots are required')
        verified = []
        for i, slot in enumerate(slots, 1):
            if slot is None:
                verified.append(None)
                continue
            if not isinstance(slot, dict) or set(slot) != {'name', 'lighting'}:
                raise MetaCubeError(f'Preset {i} must contain only name and lighting')
            name = slot['name']
            if not isinstance(name, str) or not name or len(name) > 36 or any(ord(c) < 32 for c in name):
                raise MetaCubeError(f'Invalid preset {i} name (1..36 characters)')
            lighting = slot['lighting']
            if not isinstance(lighting, dict) or set(lighting) != cls.KEYS:
                raise MetaCubeError(f'Preset {i} must contain all 7 lighting fields')
            # Older v2.1 builds allowed speed 11..255. Existing user JSON
            # stays untouched on disk; in-memory views use safe speed=2.
            # New imports and saves always enforce the genuine OEM 0..10 range.
            if allow_legacy_speed and type(lighting['speed']) is int and 11 <= lighting['speed'] <= 255:
                lighting = {**lighting, 'speed': SAFE_RGB_SPEED}
            verified.append({'name': name, 'lighting': normalize_lighting(lighting)})
        return verified

    def read(self) -> list:
        if not self.path.exists():
            return [None] * 5
        try:
            if self.path.stat().st_size > 65536:
                raise MetaCubeError('Presets file exceeds safe size limit')
            data = json.loads(self.path.read_text(encoding='utf-8'))
        except (OSError, ValueError) as exc:
            raise MetaCubeError(f'Invalid presets file: {exc}') from exc
        if not isinstance(data, dict) or data.get('version') != 1 or set(data) != {'version', 'slots'}:
            raise MetaCubeError('Unsupported presets file format')
        return self.validate_slots(data['slots'], allow_legacy_speed=True)

    def export(self) -> dict:
        return {'version': 1, 'slots': self.read()}

    def replace(self, document: dict) -> list:
        """Import all presets atomically without touching the physical LEDs."""
        if not isinstance(document, dict) or set(document) != {'version', 'slots'} or document['version'] != 1:
            raise MetaCubeError('Preset import requires version 1 and slots')
        slots = self.validate_slots(document['slots'])
        with LOCK:
            _atomic_write(self.path, json.dumps({'version': 1, 'slots': slots}, ensure_ascii=False, indent=2) + '\n')
        return slots

    def update(self, slot: int, state: dict | None, name: str = '') -> list:
        slot = number(slot, 1, 5, 'preset slot')
        if not isinstance(name, str) or len(name) > 36 or any(ord(c) < 32 for c in name):
            raise MetaCubeError('Invalid preset name (max 36 characters)')
        lighting = None
        if state is not None:
            if not isinstance(state, dict) or not self.KEYS.issubset(state):
                raise MetaCubeError('Cannot save incomplete lighting settings')
            lighting = normalize_lighting({key: state[key] for key in self.KEYS})
        with LOCK:
            values = self.read()
            values[slot-1] = None if lighting is None else {
                'name': name or f'预设 {slot}',
                'lighting': lighting,
            }
            self.replace({'version': 1, 'slots': values})
            return values

    def get(self, slot: int) -> dict:
        slot = number(slot, 1, 5, 'preset slot')
        found = self.read()[slot-1]
        if not found:
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
