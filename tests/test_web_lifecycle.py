"""Background lifecycle CLI tests; mock systemctl, never touch firmware or real services."""
from __future__ import annotations

import io
import subprocess
from unittest.mock import patch
from types import SimpleNamespace
import unittest

from metacube_rgb import cli, webctl
from metacube_rgb.core import MetaCubeError


class FakeTTY(io.StringIO):
    def __init__(self, tty):
        super().__init__()
        self.tty = tty

    def isatty(self):
        return self.tty


class LifecycleTests(unittest.TestCase):
    @staticmethod
    def fake_systemctl(*args):
        if args[0] == 'show':
            return subprocess.CompletedProcess(args, 0,
                'LoadState=loaded\nActiveState=active\nSubState=running\n'
                'UnitFileState=disabled\nMainPID=1284\n', '')
        return subprocess.CompletedProcess(args, 0, '', '')

    def test_cli_foreground_unchanged(self):
        with patch.object(cli, 'serve') as serve:
            self.assertEqual(cli.main(['web', '--demo', '--host', '127.0.0.1','--port','8766']),0)
        self.assertEqual(serve.call_args.args[:2], ('127.0.0.1',8766))

    def test_cli_lifecycle_dispatch(self):
        for action in ('start','stop','restart','status'):
            with self.subTest(action=action), patch.object(cli,'manage_web_service') as manage:
                self.assertEqual(cli.main(['web',action]),0)
                manage.assert_called_once_with(action)

    def test_cli_rejects_foreground_flags_in_background(self):
        for flag in (['--host=127.0.0.1'],['--port=8766'],['--demo'],['--show-token'],
                     ['--token-file=/tmp/token']):
            with self.subTest(flag=flag), patch.object(cli,'manage_web_service') as manage, \
                 patch('sys.stderr',new=io.StringIO()) as errors:
                self.assertEqual(cli.main(['web','start',*flag]),1)
                self.assertIn('foreground only',errors.getvalue())
                manage.assert_not_called()

    def test_start_shows_token_only_in_terminal(self):
        for tty in (True,False):
            out=FakeTTY(tty)
            with patch.object(webctl.os,'geteuid',return_value=0), \
                 patch.object(webctl,'UNIT_FILE',SimpleNamespace(is_file=lambda: True)), \
                 patch.object(webctl,'_systemctl',side_effect=self.fake_systemctl) as ctl, \
                 patch.object(webctl,'token_from_file',return_value='secret-will-not-enter-journal') as token:
                webctl.manage_web_service('start',output=out)
            self.assertEqual('secret-will-not-enter-journal' in out.getvalue(),tty)
            self.assertIn('service: running',out.getvalue())
            self.assertIn('start on boot: no',out.getvalue())
            self.assertEqual(token.called,tty)
            self.assertTrue(any(c.args[0]=='start' for c in ctl.call_args_list))

    def test_status_does_not_print_token(self):
        out=FakeTTY(True)
        with patch.object(webctl,'UNIT_FILE',SimpleNamespace(is_file=lambda: True)), \
             patch.object(webctl,'_systemctl',side_effect=self.fake_systemctl), \
             patch.object(webctl,'token_from_file') as token:
            webctl.manage_web_service('status',output=out)
        self.assertIn('service: running',out.getvalue())
        token.assert_not_called()

    def test_stop_never_prints_token(self):
        out=FakeTTY(True)
        with patch.object(webctl.os,'geteuid',return_value=0), \
             patch.object(webctl,'UNIT_FILE',SimpleNamespace(is_file=lambda: True)), \
             patch.object(webctl,'_systemctl',side_effect=self.fake_systemctl), \
             patch.object(webctl,'token_from_file') as token:
            webctl.manage_web_service('stop',output=out)
        token.assert_not_called()

    def test_missing_service_unit_is_reported(self):
        with patch.object(webctl,'UNIT_FILE',SimpleNamespace(is_file=lambda: False)):
            with self.assertRaisesRegex(MetaCubeError,'install.sh --web-only'):
                webctl.manage_web_service('status')

    def test_service_failure_is_reported(self):
        out=FakeTTY(True)
        def failing(*args):
            return subprocess.CompletedProcess(args, 1, '', 'unit failed')
        with patch.object(webctl.os,'geteuid',return_value=0), \
             patch.object(webctl,'UNIT_FILE',SimpleNamespace(is_file=lambda: True)), \
             patch.object(webctl,'_systemctl',side_effect=failing):
            with self.assertRaisesRegex(MetaCubeError,'unit failed'):
                webctl.manage_web_service('start',output=out)

    def test_nonroot_start_rejected(self):
        with patch.object(webctl.os,'geteuid',return_value=1000):
            with self.assertRaisesRegex(MetaCubeError,'root'):
                webctl.manage_web_service('start')


if __name__ == '__main__':
    unittest.main()
