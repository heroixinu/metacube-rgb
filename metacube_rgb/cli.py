"""metacube-rgb CLI; v1 commands remain compatible."""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import sys
from .core import (Device, MODES, PERFORMANCE_MODES, MetaCubeError,
                   Presets, read_boot_config, save_boot_config,
                   normalize_lighting, build_ambient_set_packet, _atomic_write,
                   rgb_experimental_reasons, experimental_rgb_enabled)
from .web import DEFAULT_TOKEN, serve
from .templates import system_templates, system_template


def main(argv=None):
    p=argparse.ArgumentParser(prog='metacube-rgb',description='MetaCube WMI control center for Linux')
    sub=p.add_subparsers(dest='command',required=True)
    status=sub.add_parser('status',help='Read lighting status')
    status.add_argument('--json',action='store_true')
    for cmd,label in [('mode','breath/steady/spin/off'),('color','RRGGBB'),('brightness','0..255'),
                      ('speed','0..10 (OEM slider)'),('direction','0/1'),('cycle','0..11'),('transition','0/1')]:
        sp=sub.add_parser(cmd,help=f'Set {label}')
        sp.add_argument('value')
    atomic=sub.add_parser('set',help='Atomic RGB update; up to 6 colors and all OEM effect fields')
    atomic.add_argument('--mode',choices=tuple(MODES))
    atomic.add_argument('--colors',nargs='+',help='1..6 RRGGBB hex values')
    for field in ('brightness','speed','direction','cycle','transition'):
        atomic.add_argument('--'+field,type=int)
    atomic.add_argument('--expected-raw',help='Optional optimistic WMI state check (64 hex characters)')
    atomic.add_argument('--dry-run',action='store_true',help='Show full 32-byte SET packet without writing the firmware')
    colors=sub.add_parser('colors',help='Set 1..6 RGB colors')
    colors.add_argument('values',nargs='+',help='RRGGBB colors')
    sub.add_parser('system',help='Display Linux host telemetry')
    sub.add_parser('fans',help='Read-only OEM main/small fan RPM with source fallback')
    sub.add_parser('oem',help='Read optional OEM WMI status (explicit query)')
    platform=sub.add_parser('platform',help='Optional OEM platform control')
    platform.add_argument('kind',choices=('system_mode','button_brightness'))
    platform.add_argument('value')
    presets=sub.add_parser('preset',help='Five OEM-style local lighting presets')
    presets.add_argument('action',choices=('list','save','apply','delete','export','import'))
    presets.add_argument('slot',nargs='?',type=int)
    presets.add_argument('--name',default='')
    presets.add_argument('--file',type=Path,help='JSON file for import/export')
    templates=sub.add_parser('template',help='Built-in read-only system RGB templates')
    templates.add_argument('action',choices=('list','apply'))
    templates.add_argument('id',nargs='?',type=int)
    sub.add_parser('save',help='Save boot restore configuration')
    apply_cmd=sub.add_parser('apply',help='Apply saved boot restore configuration')
    apply_cmd.add_argument('--dry-run',action='store_true')
    web=sub.add_parser('web',help='Launch authenticated Web UI')
    web.add_argument('--host',default=os.environ.get('METACUBE_WEB_HOST','0.0.0.0'),
                     help='IPv4 bind address (default: 0.0.0.0, accessible via LAN IP)')
    web.add_argument('--port',type=int,default=int(os.environ.get('METACUBE_WEB_PORT','8765')))
    web.add_argument('--token-file',type=Path,default=Path(os.environ.get('METACUBE_WEB_TOKEN_FILE',str(DEFAULT_TOKEN))))
    web.add_argument('--demo',action='store_true',help='UI demonstration; no firmware access')
    web.add_argument('--show-token',action='store_true',
                     help='Print Bearer token even when stdout is redirected (may expose credentials in logs)')
    args=p.parse_args(argv)
    dev=Device()
    try:
        if args.command=='web':
            if not 1<=args.port<=65535:
                raise MetaCubeError('Port must be 1..65535')
            serve(args.host,args.port,args.token_file,demo=args.demo,show_token=args.show_token)
        elif args.command=='status':
            state=dev.state()
            if args.json:
                print(json.dumps(state,indent=2,ensure_ascii=False))
            else:
                print(f'Mode: {state["mode"]} ({state["mode_number"]})')
                print(f'Colors: {", ".join("#"+c for c in state["colors"])}')
                print(f'Brightness: {state["brightness"]}/255')
                print(f'Speed: {state["speed"]} | Direction: {state["direction"]}')
                print(f'Cycle: {state["cycle"]} | Transition: {state["transition"]}')
                print(f'Writable: {state["writable"]} | Platform writes: {state["platform_writable"]}')
                print(f'Custom animation speed unlocked: {state["speed_customization_enabled"]}')
                print(f'Raw: {state["raw"]}')
        elif args.command in ('mode','color','brightness','speed','direction','cycle','transition'):
            payload={'colors':[args.value]} if args.command=='color' else {args.command:args.value}
            print(json.dumps(dev.lighting(payload),indent=2))
        elif args.command=='set':
            fields=('mode','brightness','speed','direction','cycle','transition')
            changes={field:getattr(args,field) for field in fields if getattr(args,field) is not None}
            if args.colors is not None:changes['colors']=args.colors
            if not changes:
                raise MetaCubeError('Specify at least one RGB field for set')
            if args.dry_run:
                before=dev.state()
                if args.expected_raw is not None and args.expected_raw != before['raw']:
                    raise MetaCubeError('Firmware changed since the expected raw state')
                target=normalize_lighting(changes,before)
                print(json.dumps({'current':{k:before[k] for k in target},
                                  'target':target,
                                  'set_packet':build_ambient_set_packet(before['raw'],target),
                                  'experimental_reasons':rgb_experimental_reasons(target),
                                  'can_apply':experimental_rgb_enabled() or not rgb_experimental_reasons(target),
                                  'dry_run':True},indent=2,ensure_ascii=False))
            else:
                print(json.dumps(dev.lighting(changes,expected_raw=args.expected_raw),indent=2))
        elif args.command=='colors':
            print(json.dumps(dev.lighting({'colors':args.values}),indent=2))
        elif args.command=='fans':
            print(json.dumps(dev.fans(),indent=2,ensure_ascii=False))
        elif args.command=='system':
            from .metrics import Sampler
            print(json.dumps(Sampler().snapshot(),indent=2,ensure_ascii=False))
        elif args.command=='oem':
            print(json.dumps(dev.read_oem(),indent=2,ensure_ascii=False))
        elif args.command=='platform':
            value=PERFORMANCE_MODES[args.value] if args.kind=='system_mode' and args.value in PERFORMANCE_MODES else args.value
            print(json.dumps(dev.platform(args.kind,value),indent=2))
        elif args.command=='preset':
            storage=Presets()
            if args.action=='list':
                print(json.dumps(storage.read(),indent=2,ensure_ascii=False))
            elif args.action=='export':
                data=json.dumps(storage.export(),indent=2,ensure_ascii=False)+'\n'
                if args.file:
                    _atomic_write(args.file,data)
                    print('Exported:',args.file)
                else:
                    print(data,end='')
            elif args.action=='import':
                if not args.file:
                    raise MetaCubeError('preset import requires --file PATH')
                if args.file.stat().st_size>65536:
                    raise MetaCubeError('Preset import file exceeds 64 KB')
                print(json.dumps(storage.replace(json.loads(args.file.read_text(encoding='utf-8'))),ensure_ascii=False))
            else:
                if args.slot is None:
                    raise MetaCubeError('Specify preset slot 1..5')
                if args.action=='save':
                    print(json.dumps(storage.update(args.slot,dev.state(),args.name),ensure_ascii=False))
                elif args.action=='apply':
                    print(json.dumps(dev.lighting(storage.get(args.slot)),ensure_ascii=False))
                else:
                    print(json.dumps(storage.update(args.slot,None),ensure_ascii=False))
        elif args.command=='template':
            if args.action=='list':
                print(json.dumps(system_templates(),indent=2,ensure_ascii=False))
            else:
                if args.id is None:
                    raise MetaCubeError('template apply requires an id (1..4)')
                print(json.dumps(dev.lighting(system_template(args.id)),indent=2,ensure_ascii=False))
        elif args.command=='save':
            print('Saved:',save_boot_config(dev))
        elif args.command=='apply':
            target=read_boot_config()
            if args.dry_run:
                print('Current:',json.dumps(dev.state(),ensure_ascii=False))
                print('Preset:',json.dumps(target,ensure_ascii=False))
                print('Dry run; no firmware writes')
            else:
                print(json.dumps(dev.lighting(target),indent=2))
    except (MetaCubeError,OSError,ValueError) as exc:
        print(f'metacube-rgb: {exc}',file=sys.stderr)
        return 1
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
