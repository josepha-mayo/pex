#!/usr/bin/env python3
"""Native safe-window orchestration only. No DISPLAY/auth injection or provider calls.

Root launches in the reserved clean terminal, then creates START_CAPTURE only
after inspecting its cleared header. STOP_CAPTURE stops owned child handles.
All child logs except the sanitized follower stay private. No PID guessing.
"""
import argparse
import os
from pathlib import Path
import signal
import subprocess
import sys
import time


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--run-prefix', required=True); p.add_argument('--run-id', required=True)
    p.add_argument('--window-id', required=True, type=lambda x: int(x, 0))
    args = p.parse_args()
    os.umask(0o077)
    if not os.environ.get('DISPLAY') or args.window_id <= 0: raise ValueError('native_display_and_window_required')
    root = Path(args.run_prefix).absolute()
    if root.resolve() != root or root.name != args.run_id: raise ValueError('exact_fresh_run_required')
    session = root / 'recording-live'
    session.mkdir(mode=0o700, exist_ok=False)
    support = Path(__file__).with_name('record_support.py')
    children = []; stop = False
    def requested(*_):
        nonlocal stop
        stop = True
    signal.signal(signal.SIGINT, requested); signal.signal(signal.SIGTERM, requested)
    with (session / 'native-private.log').open('x') as log:
        follower = subprocess.Popen([sys.executable, '-B', '-u', str(support), 'follow', '--run-id', args.run_id,
            '--feed', str(root / 'safe-display.jsonl'), '--output-dir', str(session / 'display'),
            '--max-seconds', '1800'], stderr=log)
        children.append(follower)
        try:
            start = time.monotonic()
            receipt = session / 'display/follower-start.json'
            while not receipt.exists() and time.monotonic() - start < 10 and follower.poll() is None:
                time.sleep(.1)
            if not receipt.exists() or follower.poll() is not None: raise ValueError('follower_start_failed')
            while not (session / 'START_CAPTURE').exists():
                if stop or (session / 'STOP_CAPTURE').exists() or follower.poll() is not None:
                    return 2
                if time.monotonic() - start > 300: return 3
                time.sleep(.1)
            capture = subprocess.Popen([sys.executable, '-B', '-u', str(support), 'capture',
                '--window-id', str(args.window_id), '--output-dir', str(session / 'video'),
                '--max-seconds', '1800'], stdout=log, stderr=log)
            children.append(capture)
            while capture.poll() is None and not stop and not (session / 'STOP_CAPTURE').exists():
                time.sleep(.2)
            if capture.poll() is None: capture.send_signal(signal.SIGINT)
            capture.wait(timeout=15)
            print('PRIVATE WINDOW RECORDING ENDED — actual terminal evidence must be checked separately.', flush=True)
            return 0
        finally:
            for child in reversed(children):
                if child.poll() is None:
                    child.send_signal(signal.SIGINT)
                    try: child.wait(timeout=15)
                    except subprocess.TimeoutExpired:
                        child.terminate(); child.wait(timeout=5)


if __name__ == '__main__':
    try: raise SystemExit(main())
    except Exception:
        print('Native recording setup refused or interrupted; no provider execution was started.', flush=True)
        raise SystemExit(2)
