#!/usr/bin/env python3
"""TradeDoctor dev restart script — cross-platform (Windows / Linux).

Usage: python restart.py

Prerequisites (both platforms):
    - Python 3.10+ with backend/.venv
    - Node.js 18+ (npx available in PATH)
    - PostgreSQL (or SQLite for dev)
"""

from __future__ import annotations

import os
import sys
import time
import signal
import shutil
import platform
import subprocess
from pathlib import Path
import urllib.request

ROOT = Path(__file__).resolve().parent
BACKEND_DIR = ROOT / "backend"
FRONTEND_DIR = ROOT / "frontend"
LOG_DIR = ROOT / ".tmp"

BACKEND_PORT = 8000
FRONTEND_PORT = 5173

IS_WINDOWS = platform.system() == "Windows"

LOG_DIR.mkdir(parents=True, exist_ok=True)


def ok(msg: str) -> None:
    print(f"  [ok] {msg}")


def fail(msg: str) -> None:
    print(f"  [fail] {msg}")


# ── Step 0: Clean pycache ───────────────────────────────────────────────

def clean_pycache() -> None:
    """Remove all __pycache__ dirs so stale .pyc never shadows new .py code."""
    removed = 0
    for d in BACKEND_DIR.rglob("__pycache__"):
        try:
            shutil.rmtree(d, ignore_errors=True)
            removed += 1
        except OSError:
            pass
    if removed:
        ok(f"Cleared {removed} __pycache__ dir(s)")


# ── Step 1: Free ports ──────────────────────────────────────────────────

def _pid_listening(port: int) -> str | None:
    """Return PID (as string) of process listening on `port`, or None."""
    if IS_WINDOWS:
        try:
            # Only query the specific port, not ALL connections
            out = subprocess.check_output(
                f'netstat -ano | findstr ":{port} " | findstr "LISTENING"',
                shell=True, text=True, timeout=5,
            )
            line = out.strip().splitlines()[0] if out.strip() else ""
            if line:
                parts = line.strip().split()
                return parts[-1]  # PID is last column
        except Exception:
            pass
    else:
        try:
            out = subprocess.check_output(
                ["lsof", "-ti", f":{port}"], text=True, timeout=5
            )
            return out.strip() or None
        except Exception:
            pass
    return None


def _kill_pid(pid: str) -> bool:
    """Kill a process by PID. Returns True on success."""
    try:
        if IS_WINDOWS:
            subprocess.run(
                ["taskkill", "/F", "/PID", pid],
                capture_output=True, timeout=5,
            )
        else:
            os.kill(int(pid), signal.SIGKILL)
        return True
    except Exception:
        return False


def free_ports() -> None:
    print(f"[1/4] Freeing ports {BACKEND_PORT} {FRONTEND_PORT} ...")
    for port in (BACKEND_PORT, FRONTEND_PORT):
        pid = _pid_listening(port)
        if pid:
            _kill_pid(pid)
            time.sleep(0.3)
            # Double-check
            if not _pid_listening(port):
                ok(f":{port} freed (was PID={pid})")
            else:
                fail(f":{port} could not free PID={pid}")
        else:
            ok(f":{port} already free")


# ── Step 2 & 3: Start servers ───────────────────────────────────────────

def _detach_popen(cmd: list[str], log_path: Path, cwd: Path) -> subprocess.Popen:
    """Start a process detached from the terminal, output → log file."""
    log_fh = open(log_path, "w", encoding="utf-8", errors="replace")
    kwargs: dict = dict(
        stdout=log_fh,
        stderr=subprocess.STDOUT,
        cwd=str(cwd),
    )
    if IS_WINDOWS:
        # CREATE_NO_WINDOW only — no CREATE_NEW_PROCESS_GROUP which
        # can cause the parent PowerShell window to hang.
        kwargs["creationflags"] = 0x08000000  # CREATE_NO_WINDOW
    else:
        kwargs["start_new_session"] = True
    return subprocess.Popen(cmd, **kwargs)


def start_backend() -> int:
    print(f"[2/4] Starting backend :{BACKEND_PORT} ...")
    # Use the venv's uvicorn explicitly. A bare `uvicorn` on PATH resolves
    # to whichever interpreter is first on PATH, which may be a system
    # Python that lacks slowapi/etc. and crashes with ModuleNotFoundError.
    uvicorn_bin = BACKEND_DIR / ".venv" / ("Scripts" if IS_WINDOWS else "bin") / (
        "uvicorn.exe" if IS_WINDOWS else "uvicorn"
    )
    cmd = [
        str(uvicorn_bin), "app.main:app",
        "--host", "0.0.0.0", "--port", str(BACKEND_PORT),
        "--reload",
    ]
    proc = _detach_popen(cmd, LOG_DIR / "backend.log", BACKEND_DIR)
    ok(f"PID={proc.pid}  log: {LOG_DIR / 'backend.log'}")
    return proc.pid


def start_frontend() -> int:
    print(f"[3/4] Starting frontend :{FRONTEND_PORT} ...")
    if IS_WINDOWS:
        cmd = ["cmd.exe", "/c", "npx", "vite", "--port", str(FRONTEND_PORT)]
    else:
        cmd = ["npx", "vite", "--port", str(FRONTEND_PORT)]
    proc = _detach_popen(cmd, LOG_DIR / "frontend.log", FRONTEND_DIR)
    ok(f"PID={proc.pid}  log: {LOG_DIR / 'frontend.log'}")
    return proc.pid


# ── Step 4: Health check ─────────────────────────────────────────────────

def wait_backend(timeout: float = 15.0) -> bool:
    print()
    print("  Waiting for backend", end="", flush=True)
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            req = urllib.request.Request(
                f"http://localhost:{BACKEND_PORT}/api/health"
            )
            with urllib.request.urlopen(req, timeout=1) as resp:
                if resp.status == 200:
                    print()
                    ok("Backend ready")
                    return True
        except Exception:
            pass
        print(".", end="", flush=True)
        time.sleep(0.5)
    print()
    fail(f"Backend did not start within {timeout:.0f}s, check log: {LOG_DIR / 'backend.log'}")
    return False


# ── Main ─────────────────────────────────────────────────────────────────

def main() -> None:
    print("=== Restarting TradeDoctor (dev) ===")

    clean_pycache()
    free_ports()
    start_backend()
    start_frontend()

    if not wait_backend():
        sys.exit(1)

    print()
    print(f"  http://localhost:{FRONTEND_PORT}  <- Frontend")
    print(f"  http://localhost:{BACKEND_PORT}/api/health  <- Backend health")
    print(f"  Logs: {LOG_DIR}")
    print("=== Done ===")


if __name__ == "__main__":
    main()
