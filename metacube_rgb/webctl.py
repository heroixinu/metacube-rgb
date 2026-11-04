"""Manage the installed MetaCube Web server as a systemd background service.

The web server itself stays in the foreground under systemd; this module never
forks an unmanaged privileged process and never writes firmware settings.
"""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys

from .core import MetaCubeError
from .web import DEFAULT_TOKEN, token_from_file

SERVICE = 'metacube-rgb-web.service'
UNIT_FILE = Path('/etc/systemd/system') / SERVICE


def _systemctl(*args: str) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(['systemctl', *args, SERVICE],
                              text=True, capture_output=True, timeout=30,
                              check=False)
    except FileNotFoundError as exc:
        raise MetaCubeError('systemctl not installed; background mode requires systemd') from exc
    except subprocess.TimeoutExpired as exc:
        raise MetaCubeError(f'systemctl {args[0]} timed out') from exc


def _service_state() -> dict[str, str]:
    result = _systemctl('show', '--property=LoadState', '--property=ActiveState',
                        '--property=SubState', '--property=UnitFileState',
                        '--property=MainPID')
    if result.returncode:
        raise MetaCubeError(f'Cannot inspect {SERVICE}: {result.stderr.strip() or result.stdout.strip()}')
    data = dict(line.split('=', 1) for line in result.stdout.splitlines() if '=' in line)
    if data.get('LoadState') != 'loaded':
        raise MetaCubeError(f'{SERVICE} not installed; run: bash install.sh --web-only')
    return data


def manage_web_service(operation: str, *, output=None, token_file: Path = DEFAULT_TOKEN) -> None:
    """Start/stop/restart/status via systemd; display token only on an interactive terminal."""
    out = output or sys.stdout
    if operation not in ('start', 'stop', 'restart', 'status'):
        raise MetaCubeError(f'Unsupported Web service operation: {operation}')
    if operation != 'status' and os.geteuid() != 0:
        raise MetaCubeError('Start/stop/restart requires root; run with sudo')
    if not UNIT_FILE.is_file():
        raise MetaCubeError(f'{SERVICE} is not installed; run: bash install.sh --web-only')

    if operation != 'status':
        result = _systemctl(operation)
        if result.returncode:
            detail = (result.stderr or result.stdout).strip() or f'exit status {result.returncode}'
            raise MetaCubeError(f'systemctl {operation} failed: {detail}\n'
                                f'Inspect: journalctl -u {SERVICE} -n 30 --no-pager')

    state = _service_state()
    running = state.get('ActiveState') == 'active'
    enabled = state.get('UnitFileState') == 'enabled'
    pid = state.get('MainPID', '0')
    print(f'MetaCube Web service: {"running" if running else state.get("ActiveState", "unknown")}', file=out)
    print(f'PID: {pid if running else "-"} | start on boot: {"yes" if enabled else "no"}', file=out)
    if operation in ('start', 'restart') and not running:
        raise MetaCubeError(f'{SERVICE} did not become active; inspect: '
                            f'journalctl -u {SERVICE} -n 30 --no-pager')
    if operation in ('start', 'restart'):
        # Unit stdout/stderr is captured by journald, never containing this credential.
        # It is printed only in the operator's interactive session.
        if getattr(out, 'isatty', lambda: False)():
            token = token_from_file(token_file, generate=False)
            print(f'Bearer token: {token}', file=out)
        print(f'Web URL(s): journalctl -u {SERVICE} -n 10 --no-pager', file=out)
        print('Stop: metacube-rgb web stop', file=out)
    elif operation == 'status':
        print(f'Logs: journalctl -u {SERVICE} -n 20 --no-pager', file=out)
