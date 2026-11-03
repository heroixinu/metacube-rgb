"""Authenticated MetaCube control panel for a trusted LAN (stdlib only)."""
from __future__ import annotations
from dataclasses import dataclass
import hmac
import ipaddress
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import threading
import time
from urllib.parse import urlsplit
from . import __version__
from .core import (Device, MetaCubeError, MetaCubeConflict, Presets, normalize_lighting,
                   build_ambient_set_packet, rgb_experimental_reasons, experimental_rgb_enabled)
from .metrics import Sampler
from .templates import system_templates, system_template

WEB_FILES = {
    '/': ('index.html','text/html; charset=utf-8'),
    '/styles.css': ('styles.css','text/css; charset=utf-8'),
    '/app.js': ('app.js','text/javascript; charset=utf-8'),
}
WEB_ROOT = Path(__file__).resolve().parent.parent/'web'
DEFAULT_TOKEN = Path('/etc/metacube-rgb/web.token')


class DemoDevice(Device):
    def __init__(self):
        self._current = {'mode':'breath','colors':['50DCFA','8057FF','FF548B'],
                         'brightness':160,'speed':2,'direction':0,'cycle':5,'transition':1}

    def flag(self, name):
        return name == 'allow_writes'

    def state(self):
        from .core import MODES
        data = dict(self._current)
        return {**data,'color': data['colors'][0],
                'color_count':len(data['colors']),
                'mode_number': MODES[data['mode']],
                'writable':True,'platform_writable':False,
                'rgb_experimental_enabled':True,
                'speed_customization_enabled':True,
                 'extended':True,'raw':self._raw()}

    def _raw(self):
        from .core import MODES
        data = bytearray(32)
        data[:4] = bytes.fromhex('0080000f')
        data[4] = MODES[self._current['mode']]
        data[5] = len(self._current['colors'])
        data[6:24] = bytes.fromhex(''.join(self._current['colors'])).ljust(18,b'\0')
        data[24:29] = bytes(self._current[k] for k in ('brightness','speed','direction','cycle','transition'))
        return data.hex()

    def lighting(self, changes, expected_raw=None):
        if expected_raw is not None and self.state()['raw'] != expected_raw:
            raise MetaCubeConflict('Firmware RGB settings changed after editing began. Refresh before applying.')
        self._current = normalize_lighting(changes, self._current)
        return self.state()

    def fans(self):
        return {'available':True, 'main_rpm':2380, 'small_rpm':1740,
                'source':'demo', 'poll_seconds':2, 'manual_control':False,
                'note':'Simulated fan telemetry, no WMI access'}

    def read_oem(self, selected=None):
        from .core import OEM_READS
        return {name:{'unsupported':True,'reason':'Demo mode: no OEM WMI call made'}
                for name in (selected or list(OEM_READS))}

    def platform(self, control, value):
        raise MetaCubeError('OEM platform writes are disabled in demo mode')


class Api:
    def __init__(self, device, presets, sampler=None, demo=False):
        self.device = device
        self.presets = presets
        self.sampler = sampler or Sampler()
        self.demo = demo
        self._lock = threading.RLock()
        self._undo_before = None
        self._undo_after = None
        self._fan_last = None
        self._fan_last_at = 0.0

    def read(self, path):
        if path == '/api/health':
            return {'version': __version__, 'service':'ready'}
        if path == '/api/status':
            return {'lighting':self.device.state(), 'version':__version__, 'demo':self.demo, 'undo_available':self._undo_before is not None}
        if path == '/api/fans':
            # At most one physical ACPI probe every two seconds per Web server,
            # even when multiple browsers are watching the performance page.
            with self._lock:
                now = time.monotonic()
                if self._fan_last is None or now - self._fan_last_at >= 2.0:
                    self._fan_last = self.device.fans()
                    self._fan_last_at = now
                return self._fan_last
        if path == '/api/system':
            with self._lock:
                return self.sampler.snapshot()
        if path == '/api/presets':
            return {'slots':self.presets.read()}
        if path == '/api/templates':
            return {'templates': system_templates()}
        if path == '/api/presets/export':
            return self.presets.export()
        if path == '/api/oem-basic':
            return {'functions':self.device.read_oem(['system_mode','button_brightness'])}
        if path == '/api/oem':
            return {'functions':self.device.read_oem(), 'note':'Explicit read-only WMI diagnostic; unsupported devices may return errors.'}
        raise KeyError(path)

    def write(self, path, obj):
        if not isinstance(obj, dict):
            raise MetaCubeError('Expected a JSON object')
        if path == '/api/lighting/plan':
            changes=dict(obj)
            expected=changes.pop('expected_raw',None)
            with self._lock:
                before=self.device.state()
                if expected is not None and before['raw'] != expected:
                    raise MetaCubeConflict('RGB configuration changed; reload before generating a new plan')
                target=normalize_lighting(changes,before)
                fields=['mode','colors','brightness','speed','direction','cycle','transition']
                return {'current':{k:before[k] for k in fields},
                        'target':target,
                        'changes':{k:{'from':before[k], 'to':target[k]} for k in fields if before[k] != target[k]},
                        'set_packet':build_ambient_set_packet(before['raw'],target),
                        'experimental_reasons':rgb_experimental_reasons(target),
                        'can_apply':self.demo or experimental_rgb_enabled() or not rgb_experimental_reasons(target),
                        'note':'Dry run only; no WMI SET is issued. Physical LED output cannot be confirmed by WMI GET.'}
        if path == '/api/lighting':
            changes=dict(obj)
            expected=changes.pop('expected_raw',None)
            with self._lock:
                before=self.device.state()
                after=self.device.lighting(changes,expected_raw=expected)
                if before['raw'] != after['raw']:
                    self._undo_before=before
                    self._undo_after=after
                return {'lighting':after,'undo_available':self._undo_before is not None}
        if path == '/api/lighting/undo':
            if obj:
                raise MetaCubeError('Undo accepts an empty object only')
            with self._lock:
                if self._undo_before is None:
                    raise MetaCubeError('No previous RGB setting is available for undo')
                now=self.device.state()
                if now['raw'] != self._undo_after['raw']:
                    raise MetaCubeConflict('Cannot undo: hardware RGB state changed after last apply')
                fields=('mode','colors','brightness','speed','direction','cycle','transition')
                desired={k:self._undo_before[k] for k in fields}
                updated=self.device.lighting(desired,expected_raw=now['raw'])
                self._undo_before = self._undo_after = None
                return {'lighting':updated,'undo_available':False}
        if path == '/api/platform':
            if set(obj) != {'control','value'}:
                raise MetaCubeError('Expected control and value')
            return {'result':self.device.platform(obj['control'], obj['value'])}
        if path == '/api/presets/save':
            if set(obj) - {'slot','name','lighting'}:
                raise MetaCubeError('Unknown preset fields')
            slot=obj.get('slot')
            # Saving a draft does NOT write the firmware; only an explicit apply does.
            state=obj['lighting'] if 'lighting' in obj else self.device.state()
            return {'slots':self.presets.update(slot,state,obj.get('name',''))}
        if path == '/api/presets/import':
            return {'slots':self.presets.replace(obj)}
        if path == '/api/presets/delete':
            if set(obj) != {'slot'}:
                raise MetaCubeError('Expected slot')
            return {'slots':self.presets.update(obj['slot'],None)}
        if path == '/api/templates/apply':
            if set(obj) - {'id','expected_raw'} or 'id' not in obj:
                raise MetaCubeError('Expected system template id and optional expected_raw')
            with self._lock:
                desired = system_template(obj['id'])
                before = self.device.state()
                after = self.device.lighting(desired,expected_raw=obj.get('expected_raw'))
                if after['raw'] != before['raw']:
                    self._undo_before = before
                    self._undo_after = after
                return {'lighting':after,'undo_available':self._undo_before is not None}
        if path == '/api/presets/apply':
            if set(obj) - {'slot','expected_raw'} or 'slot' not in obj:
                raise MetaCubeError('Expected slot and optional expected_raw')
            with self._lock:
                before=self.device.state()
                after=self.device.lighting(self.presets.get(obj['slot']),expected_raw=obj.get('expected_raw'))
                if after['raw'] != before['raw']:
                    self._undo_before = before
                    self._undo_after = after
                return {'lighting':after,'undo_available':self._undo_before is not None}
        raise KeyError(path)


def token_from_file(path: Path, generate=True):
    path = Path(path)
    if not path.is_file():
        if not generate:
            raise MetaCubeError(f'Missing web authentication token: {path}')
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        try:
            fd = os.open(path, os.O_WRONLY|os.O_CREAT|os.O_EXCL, 0o600)
        except FileExistsError:
            pass
        else:
            with os.fdopen(fd, 'w', encoding='ascii') as f:
                f.write(secrets.token_urlsafe(36)+'\n')
    stat=path.stat()
    if (stat.st_mode & 0o077) != 0:
        raise MetaCubeError(f'Web token file must be private (chmod 600): {path}')
    token=path.read_text(encoding='ascii').strip()
    if len(token)<32 or len(token)>256:
        raise MetaCubeError('Web token must be 32..256 characters')
    return token


def make_handler(api: Api, token: str):
    class Handler(BaseHTTPRequestHandler):
        server_version = 'MetaCube-Web/2.1'
        sys_version = ''
        protocol_version = 'HTTP/1.1'

        def log_message(self, fmt, *args):
            # Exclude auth headers and request bodies from journald output.
            sys.stderr.write('[metacube-web] %s %s\n' % (self.address_string(), fmt % args))

        def _send(self, code: int, body: bytes, content_type: str='application/json; charset=utf-8'):
            self.send_response(code)
            self.send_header('Content-Type',content_type)
            self.send_header('Content-Length',str(len(body)))
            self.send_header('Cache-Control','no-store')
            self.send_header('X-Content-Type-Options','nosniff')
            self.send_header('X-Frame-Options','DENY')
            self.send_header('Referrer-Policy','no-referrer')
            self.send_header('Content-Security-Policy',
                             "default-src 'none'; script-src 'self'; style-src 'self'; "
                             "connect-src 'self'; img-src 'self' data:; "
                             "base-uri 'none'; form-action 'none'; frame-ancestors 'none'")
            self.end_headers()
            self.wfile.write(body)

        def _json(self, code, data):
            self._send(code,json.dumps(data,ensure_ascii=False,allow_nan=False).encode('utf-8'))

        def _authenticated(self):
            provided=self.headers.get('Authorization','')
            if not provided.startswith('Bearer '):
                self._json(401,{'error':'需要访问令牌'})
                return False
            received=provided[7:]
            if not hmac.compare_digest(received,token):
                self._json(401,{'error':'访问令牌不正确'})
                return False
            return True

        def do_GET(self):
            path=urlsplit(self.path).path
            if path in WEB_FILES:
                filename,content_type=WEB_FILES[path]
                try:
                    data=(WEB_ROOT / filename).read_bytes()
                except OSError:
                    self._json(500,{'error':'Web assets unavailable'})
                    return
                self._send(200,data,content_type)
                return
            if not path.startswith('/api/'):
                self._json(404,{'error':'Not found'})
                return
            if path != '/api/health' and not self._authenticated():
                return
            try:
                self._json(200,api.read(path))
            except KeyError:
                self._json(404,{'error':'API endpoint not found'})
            except (MetaCubeError, OSError, ValueError) as exc:
                self._json(503,{'error':str(exc)})

        def do_POST(self):
            path=urlsplit(self.path).path
            if not self._authenticated():
                return
            origin=self.headers.get('Origin')
            # Block cross-origin form/script requests. Same-origin browsers
            # may omit Origin, e.g. certain local tools.
            if origin:
                try:
                    host=urlsplit(origin).netloc
                    if host != self.headers.get('Host','') or urlsplit(origin).scheme not in ('http','https'):
                        self._json(403,{'error':'Cross-origin requests are forbidden'})
                        return
                except ValueError:
                    self._json(403,{'error':'Invalid Origin'})
                    return
            if self.headers.get('Content-Type','').split(';')[0].strip().lower() != 'application/json':
                self._json(415,{'error':'Content-Type must be application/json'})
                return
            try:
                size=int(self.headers.get('Content-Length','0'))
            except ValueError:
                self._json(400,{'error':'Bad Content-Length'})
                return
            if not (2<=size<=4096):
                self._json(413,{'error':'JSON request must be 2..4096 bytes'})
                return
            try:
                payload=json.loads(self.rfile.read(size).decode('utf-8'))
                self._json(200,api.write(path,payload))
            except KeyError:
                self._json(404,{'error':'API endpoint not found'})
            except MetaCubeConflict as exc:
                self._json(409,{'error':str(exc)})
            except (MetaCubeError, OSError, ValueError, UnicodeError, json.JSONDecodeError) as exc:
                self._json(400,{'error':str(exc)})

    return Handler


def _lan_ipv4_addresses():
    """Find useful host IPv4 addresses to print; never sends network traffic.

    Prefer PVE bridges and physical network devices, and skip temporary
    containers/taps. Detection is display-only: the --host bind still controls
    the actual listening interface.
    """
    entries=[]
    try:
        result=subprocess.run(['ip','-j','-4','address','show','up'],capture_output=True,
                              text=True,timeout=3,check=False)
        if result.returncode == 0:
            for iface in json.loads(result.stdout):
                name=iface.get('ifname','')
                if name.startswith(('lo','tap','veth','fwbr','fwln','fwpr','docker','virbr','br-')):
                    continue
                for item in iface.get('addr_info',[]):
                    if item.get('family')!='inet' or item.get('scope')!='global':
                        continue
                    value=item.get('local','')
                    try:
                        ip=ipaddress.IPv4Address(value)
                    except ipaddress.AddressValueError:
                        continue
                    if ip.is_loopback or ip.is_link_local or ip.is_unspecified or ip.is_multicast:
                        continue
                    # IPv4 RFC1918 private addresses are preferred in the UI.
                    private = (ip in ipaddress.ip_network('10.0.0.0/8') or
                               ip in ipaddress.ip_network('172.16.0.0/12') or
                               ip in ipaddress.ip_network('192.168.0.0/16'))
                    priority=(0 if name.startswith('vmbr') else 1,
                              0 if private else 1,name,value)
                    entries.append((priority,value))
    except (OSError,ValueError,TypeError,subprocess.TimeoutExpired):
        pass
    if not entries:
        # A UDP connect only inspects local routing; no packets are sent.
        try:
            with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as sock:
                sock.connect(('192.0.2.1',9))
                value=sock.getsockname()[0]
                if not ipaddress.IPv4Address(value).is_loopback:
                    entries.append(((0,0,'',value),value))
        except (OSError,ValueError):
            pass
    ordered=[]
    for _,value in sorted(entries):
        if value not in ordered:
            ordered.append(value)
    return ordered[:8]


def startup_lines(host: str, port: int, token: str, *, show_token=False, interactive=False):
    """Render startup details without logging tokens for systemd by default."""
    listening=f'{host}:{port}'
    lines=[f'MetaCube Web v{__version__} listening on {listening}']
    if host == '0.0.0.0':
        addresses=_lan_ipv4_addresses()
        if addresses:
            lines.extend(f'Web URL: http://{address}:{port}' for address in addresses)
        else:
            lines.append(f'Web URL: http://<PVE-LAN-IP>:{port}')
        lines.append(f'Local URL: http://127.0.0.1:{port}')
    elif host in ('127.0.0.1','localhost'):
        lines.append(f'Web URL: http://127.0.0.1:{port}')
    else:
        lines.append(f'Web URL: http://{host}:{port}')
    if interactive or show_token:
        lines.append(f'Bearer token: {token}')
    else:
        lines.append('Bearer token: hidden from service logs (use an interactive terminal)')
    if host not in ('127.0.0.1','localhost'):
        lines.append('WARNING: HTTP is unencrypted. Limit TCP 8765 to trusted LAN clients or use HTTPS.')
    return lines


def serve(host: str, port: int, token_path: Path, demo=False, show_token=False):
    if os.geteuid() != 0 and not demo:
        raise MetaCubeError('The host WMI interface is root-owned; run the web server as root')
    token=token_from_file(token_path)
    api=Api(DemoDevice() if demo else Device(), Presets(), demo=demo)
    server=ThreadingHTTPServer((host,port),make_handler(api,token))
    server.daemon_threads=True
    try:
        for line in startup_lines(host,server.server_port,token,show_token=show_token,
                                  interactive=sys.stdout.isatty()):
            print(line,flush=True)
        server.serve_forever(poll_interval=0.5)
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
