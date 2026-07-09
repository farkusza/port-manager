"""port_manager._port_owner
========================
Cross-platform helper: given a listening TCP port on localhost, return
"process-name (pid N)".

Enhanced: for generic processes (node.exe, python.exe, etc.), includes
the script or command they are running.
"""
from __future__ import annotations

import re
import shutil
import subprocess
import sys

_GENERIC_NAMES = {"node.exe", "python.exe", "pythonw.exe", "powershell.exe", "cmd.exe"}
_NETSTAT_RE = re.compile(
    r"^\s*(TCP|UDP)\s+\S*:(\d+)\s+\S*:0\s+\S+\s+(\d+)", re.IGNORECASE
)


def _extract_script(cmdline: str) -> str | None:
    """Extract the meaningful script/command from a command line string."""
    if not cmdline:
        return None
    parts = cmdline.strip().split()
    if len(parts) < 2:
        return None
    extras = parts[1:]
    while extras and extras[0].startswith("-"):
        extras.pop(0)
    if extras:
        # ponytail: strip surrounding quotes from MS-style quoted paths, drop prefix dirs
        script = extras[0].strip('"').rsplit("\\", 1)[-1].rsplit("/", 1)[-1]
        if len(script) > 40:
            script = script[:37] + "..."
        return script
    return None


def _format(name: str, pid: int, cmdline: str | None = None) -> str:
    base = f"{name} (pid {pid})"
    if not cmdline or name.lower() not in _GENERIC_NAMES:
        return base
    script = _extract_script(cmdline)
    if script:
        return f"{name} -> {script} (pid {pid})"
    return base


def _get_cmdline_win(pid: int) -> str | None:
    try:
        r = subprocess.run(
            [
                "powershell.exe", "-NoProfile", "-Command",
                f"(Get-CimInstance Win32_Process -Filter 'ProcessId={pid}').CommandLine"
            ],
            capture_output=True, timeout=5,
        )
        if r.returncode == 0:
            return r.stdout.decode("utf-8", errors="replace").strip() or None
    except (OSError, subprocess.TimeoutExpired):
        pass
    return None


def _get_cmdline_unix(pid: int) -> str | None:
    try:
        with open(f"/proc/{pid}/cmdline", "rb") as f:
            data = f.read()
        parts = [p for p in data.split(b"\x00") if p]
        return b" ".join(parts).decode("utf-8", errors="replace").strip() or None
    except OSError:
        return None


def _port_owner_windows(port: int) -> str | None:
    try:
        out = subprocess.run(
            ["netstat", "-ano", "-p", "TCP"],
            capture_output=True, text=True, timeout=15,
        )
        for line in out.stdout.splitlines():
            m = _NETSTAT_RE.match(line)
            if m and int(m.group(2)) == port and "LISTENING" in line.split():
                pid = int(m.group(3))
                try:
                    r = subprocess.run(
                        ["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
                        capture_output=True, timeout=5,
                    )
                    parts = r.stdout.decode("utf-8", errors="replace").split(",")
                    name = parts[0].strip().strip('"') if parts else None
                    if not name:
                        return str(pid)
                    cmdline = _get_cmdline_win(pid) if name.lower() in _GENERIC_NAMES else None
                    return _format(name, pid, cmdline)
                except (OSError, subprocess.TimeoutExpired):
                    return str(pid)
    except (OSError, subprocess.TimeoutExpired, FileNotFoundError):
        pass
    return None


def _port_owner_unix(port: int) -> str | None:
    lsof = shutil.which("lsof")
    if not lsof:
        return None
    try:
        out = subprocess.run(
            [lsof, "-nP", "-iTCP", "-sTCP:LISTEN", "-F", "pn"],
            capture_output=True, text=True, timeout=10,
        )
        cur_pid = None
        for line in out.stdout.splitlines():
            if line.startswith("p"):
                try:
                    cur_pid = int(line[1:])
                except ValueError:
                    cur_pid = None
            elif line.startswith("n") and cur_pid is not None:
                m = re.search(r":(\d+)$", line[1:])
                if m and int(m.group(1)) == port:
                    try:
                        with open(f"/proc/{cur_pid}/comm") as f:
                            name = f.read().strip()
                    except OSError:
                        return str(cur_pid)
                    if not name:
                        return str(cur_pid)
                    cmdline = _get_cmdline_unix(cur_pid) if name.lower() in _GENERIC_NAMES else None
                    return _format(name, cur_pid, cmdline)
    except (OSError, subprocess.TimeoutExpired, FileNotFoundError):
        pass
    return None


def port_owner(port: int) -> str | None:
    if sys.platform == "win32":
        return _port_owner_windows(port)
    return _port_owner_unix(port)