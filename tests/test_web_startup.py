"""Web startup policy tests: demo/mock only, no host WMI calls."""
import io
import json
import os
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from metacube_rgb import cli, web

TOKEN = 'dummy-token-for-tests-' + 'x' * 48


class Capture(io.StringIO):
    def __init__(self, tty):
        super().__init__()
        self._tty = tty

    def isatty(self):
        return self._tty


class FakeServer:
    server_port = 8765
    daemon_threads = False

    def __init__(self):
        self.served = False
        self.closed = False

    def serve_forever(self, **kwargs):
        self.served = True

    def server_close(self):
        self.closed = True


class StartupTests(unittest.TestCase):
    def test_cli_default_binds_all_ipv4(self):
        with patch.dict(os.environ, {}, clear=True), patch.object(cli, 'serve') as serve:
            self.assertEqual(cli.main(['web', '--demo']), 0)
            args, kwargs = serve.call_args
            self.assertEqual(args[0], '0.0.0.0')
            self.assertEqual(args[1], 8765)
            self.assertFalse(kwargs['show_token'])

    def test_cli_explicit_host_and_force_token(self):
        with patch.dict(os.environ, {}, clear=True), patch.object(cli, 'serve') as serve:
            self.assertEqual(cli.main(['web', '--demo', '--host', '192.168.18.99',
                                       '--port', '9876', '--show-token']), 0)
            self.assertEqual(serve.call_args.args[:2], ('192.168.18.99', 9876))
            self.assertTrue(serve.call_args.kwargs['show_token'])

    def test_lan_detection_prefers_proxmox_management_bridge(self):
        result = SimpleNamespace(returncode=0, stdout=json.dumps([
            {'ifname': 'tap101i0', 'addr_info': [
                {'family': 'inet', 'scope': 'global', 'local': '10.0.0.50'}]},
            {'ifname': 'enp4s0', 'addr_info': [
                {'family': 'inet', 'scope': 'global', 'local': '10.10.0.11'}]},
            {'ifname': 'vmbr0', 'addr_info': [
                {'family': 'inet', 'scope': 'global', 'local': '192.168.18.99'}]},
            {'ifname': 'lo', 'addr_info': [
                {'family': 'inet', 'scope': 'host', 'local': '127.0.0.1'}]},
        ]))
        with patch.object(web.subprocess, 'run', return_value=result):
            self.assertEqual(web._lan_ipv4_addresses(), ['192.168.18.99', '10.10.0.11'])

    def test_displays_real_lan_url(self):
        with patch.object(web, '_lan_ipv4_addresses', return_value=['192.168.18.99']):
            message='\n'.join(web.startup_lines('0.0.0.0', 8765, TOKEN, interactive=True))
        self.assertIn('http://192.168.18.99:8765', message)
        self.assertNotIn('Web URL: http://0.0.0.0', message)
        self.assertIn('Bearer token: ' + TOKEN, message)

    def test_service_logs_hide_token(self):
        for tty,force,should_show in [(True,False,True), (False,False,False), (False,True,True)]:
            with self.subTest(tty=tty,force=force):
                stream=Capture(tty)
                fake=FakeServer()
                with patch.object(web, 'token_from_file', return_value=TOKEN), \
                     patch.object(web, 'ThreadingHTTPServer', return_value=fake), \
                     patch.object(web, '_lan_ipv4_addresses', return_value=['192.168.18.99']), \
                     patch.object(web.sys, 'stdout', stream):
                    web.serve('0.0.0.0', 8765, Path('/unused/token'), demo=True,
                              show_token=force)
                output=stream.getvalue()
                self.assertEqual(TOKEN in output, should_show)
                self.assertIn('http://192.168.18.99:8765', output)
                self.assertTrue(fake.served and fake.closed)


if __name__ == '__main__':
    unittest.main()
