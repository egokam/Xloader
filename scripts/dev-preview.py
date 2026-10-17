#!/usr/bin/env python3
"""Run Xloader with CSS live reload and automatic Python restarts."""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import time


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "xloader"
POLL_INTERVAL = 0.3


def source_snapshot() -> dict[Path, tuple[int, int, int]]:
    snapshot = {}
    for path in SOURCE.rglob("*.py"):
        try:
            stat = path.stat()
        except FileNotFoundError:
            continue
        snapshot[path] = (stat.st_mtime_ns, stat.st_size, stat.st_ino)
    return snapshot


def stop_process(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=3)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()


def wait_for_source_change(baseline: dict[Path, tuple[int, int, int]]) -> None:
    while source_snapshot() == baseline:
        time.sleep(POLL_INTERVAL)


def main() -> int:
    environment = os.environ.copy()
    environment["XLOADER_DEV_PREVIEW"] = "1"
    print("Xloader preview: CSS reloads live; Python edits restart the window.", flush=True)
    print("Load a reference image, drag the split line, and adjust its opacity in the window.", flush=True)
    print("Close the app to stop. Press Ctrl+C here to stop the preview.", flush=True)

    try:
        while True:
            baseline = source_snapshot()
            process = subprocess.Popen(
                [sys.executable, "-m", "xloader"],
                cwd=ROOT,
                env=environment,
            )
            print("[preview] Xloader started", flush=True)

            while True:
                time.sleep(POLL_INTERVAL)
                if source_snapshot() != baseline:
                    print("[preview] Python change detected; restarting…", flush=True)
                    stop_process(process)
                    break

                return_code = process.poll()
                if return_code is not None:
                    if return_code == 0:
                        return 0
                    print(
                        f"[preview] App exited with code {return_code}; waiting for a Python edit…",
                        file=sys.stderr,
                        flush=True,
                    )
                    wait_for_source_change(baseline)
                    break
    except KeyboardInterrupt:
        print("\n[preview] Stopping…", flush=True)
        if "process" in locals():
            stop_process(process)
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
