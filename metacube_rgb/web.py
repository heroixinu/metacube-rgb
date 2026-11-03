"""Authenticated, LAN-safe-by-default MetaCube control panel (stdlib only)."""
from __future__ import annotations
from dataclasses import dataclass
import hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import secrets
import sys
import threading
from urllib.parse import urlsplit
from . import __version__
from .core import Device, MetaCubeError, Presets, normalize_lighting
from .metrics import Sampler

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
                         'brightness':160,'speed':45,'direction':0,'cycle':5,'transition':1}

    def flag(self, name):
        return name == 'allow_writes'

    def state(self):
        from .core import MODES
        data = dict(self._current)
        return {**data,'color': data['colors'][0],
                'color_count':len(data['colors']),
                'mode_number': MODES[data['mode']],
                'writable':True,'platform_writable':False,
                'extended':True,'raw':'(demo - no WMI operations)'}

    def lighting(self, changes):
        self._current = normalize_lighting(changes, self._current)
        return self.state()

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

    def read(self, path):
        if path == '/api/health':
            return {'version': __version__, 'service':'ready'}
        if path == '/api/status':
            return {'lighting':self.device.state(), 'version':__version__, 'demo':self.demo}
        if path == '/api/system':
            with self._lock:
                return self.sampler.snapshot()
        if path == '/api/presets':
            return {'slots':self.presets.read()}
        if path == '/api/oem-basic':
            return {'functions':self.device.read_oem(['system_mode','button_brightness'])}
        if path == '/api/oem':
            return {'functions':self.device.read_oem(), 'note':'Explicit read-only WMI diagnostic; unsupported devices may return errors.'}
        raise KeyError(path)

    def write(self, path, obj):
        if not isinstance(obj, dict):
            raise MetaCubeError('Expected a JSON object')
        if path == '/api/lighting':
            return {'lighting':self.device.lighting(obj)}
        if path == '/api/platform':
            if set(obj) != {'control','value'}:
                raise MetaCubeError('Expected control and value')
            return {'result':self.device.platform(obj['control'], obj['value'])}
        if path == '/api/presets/save':
            if set(obj) - {'slot','name'}:
                raise MetaCubeError('Unknown preset fields')
            slot=obj.get('slot')
            state=self.device.state()
            return {'slots':self.presets.update(slot,state,obj.get('name',''))}
        if path == '/api/presets/delete':
            if set(obj) != {'slot'}:
                raise MetaCubeError('Expected slot')
            return {'slots':self.presets.update(obj['slot'],None)}
        if path == '/api/presets/apply':
            if set(obj) != {'slot'}:
                raise MetaCubeError('Expected slot')
            return {'lighting':self.device.lighting(self.presets.get(obj['slot']))}
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
        server_version = 'MetaCube-Web/2.0'
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
            except (MetaCubeError, OSError, ValueError, UnicodeError, json.JSONDecodeError) as exc:
                self._json(400,{'error':str(exc)})

    return Handler


def serve(host: str, port: int, token_path: Path, demo=False):
    if os.geteuid() != 0 and not demo:
        raise MetaCubeError('The host WMI interface is root-owned; run the web server as root')
    token=token_from_file(token_path)
    api=Api(DemoDevice() if demo else Device(), Presets(), demo=demo)
    server=ThreadingHTTPServer((host,port),make_handler(api,token))
    server.daemon_threads=True
    try:
        print(f'MetaCube Web v{__version__}: http://{host}:{server.server_port}',flush=True)
        print(f'Bearer token: read locally with: sudo cat {token_path}',flush=True)
        if host not in ('127.0.0.1','::1','localhost'):
            print('WARNING: Remote HTTP is unencrypted. Restrict with firewall or use HTTPS reverse proxy.',flush=True)
        server.serve_forever(poll_interval=0.5)
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
