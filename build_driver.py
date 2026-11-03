#!/usr/bin/env python3
"""Build (or clean) the checked-in kernel source; never rewrite C source.

The previous v2.0 helper was a one-off source generator. Replaced with a safe
build wrapper to avoid accidentally re-generating an outdated driver.
"""
from __future__ import annotations
import argparse
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parent


def main():
    parser=argparse.ArgumentParser(description='Build MetaCube WMI driver from checked-in source')
    parser.add_argument('--headers',type=Path,help='Linux headers tree (default: running kernel)')
    parser.add_argument('--clean',action='store_true',help='Remove build artifacts')
    args=parser.parse_args()
    headers=args.headers or Path('/lib/modules') / subprocess.check_output(['uname','-r'],text=True).strip() / 'build'
    if not headers.exists():
        parser.error(f'Kernel headers not found: {headers}')
    cmd=['make','-C',str(headers),'M='+str(ROOT/'driver'),'clean' if args.clean else 'modules']
    subprocess.run(cmd,check=True)


if __name__=='__main__':main()
