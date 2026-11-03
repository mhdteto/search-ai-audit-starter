#!/usr/bin/env python3
"""Explicitly separate the frozen fictional demo from live public observations."""
import argparse
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parent
DEMO=ROOT/'examples/fictional-workflow'

def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest='mode',required=True)
    sub.add_parser('demo',help='Replay five tools on fully fictional inputs; no target network requests')
    live=sub.add_parser('live',help='Observe one authorized public page; no live LLM queries')
    live.add_argument('url')
    live.add_argument('--output-dir',default='reports/live')
    args=parser.parse_args(argv)
    try:
        if args.mode=='demo':
            return subprocess.run([sys.executable,str(DEMO/'run_demo.py')],cwd=ROOT).returncode
        relative=Path(args.output_dir)
        if (relative.is_absolute() or '..' in relative.parts or len(relative.parts)<2
                or relative.parts[0]!='reports' or any(ord(c)<32 or ord(c)==127 for c in args.output_dir)):
            raise ValueError('Live output must be a relative reports/ subdirectory')
        current=ROOT
        for part in relative.parts:
            current=current/part
            if current.is_symlink():raise ValueError('Live output symlinks are forbidden')
        current.resolve().relative_to(ROOT)
        # Arguments are passed directly; the URL is never shell source.
        return subprocess.run([sys.executable,str(DEMO/'tools/search-ai-discoverability-checker/check.py'),args.url,'--output-dir',str(current)],cwd=ROOT).returncode
    except (OSError,ValueError) as exc:
        print('Audit failed: '+str(exc),file=sys.stderr)
        return 2

if __name__=='__main__':sys.exit(main())
