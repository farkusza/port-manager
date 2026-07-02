"""Ports Registry CLI — single-file local port tracking for developers.

Philosophy: no daemon, no OS-level port locking, just a SQLite registry
plus a live scanner. The registry is a bookkeeping layer; the scanner
is a read-only truth check against netstat/ss.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import subprocess
import sys
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator, List, Optional


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

def default_registry_path() -> Path:
    if sys.platform == "win32":
        local = Path.home() / "AppData" / "Local" / "ports-registry"
    else:
        local = Path.home() / ".local" / "share" / "ports-registry"
    local.mkdir(parents=True, exist_ok=True)
    return local / "registry.db"


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class RegistryEntry:
    id: int
    port: int
    project: str
    description: str
    project_path: str
    registered_at: str


@dataclass
class LiveListener:
    port: int
    pid: int
    namespace: str       # "windows" | "wsl"
    process_name: str = ""


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

class ConflictError(Exception):
    """Raised when registering a port already owned by a different project."""


class Registry:
    """SQLite-backed port registry. Thread-unsafe (single CLI process)."""

    SCHEMA = """
    CREATE TABLE IF NOT EXISTS ports (
        id            INTEGER PRIMARY KEY AUTOINCREMENT,
        port          INTEGER UNIQUE NOT NULL,
        project       TEXT    NOT NULL,
        description   TEXT    NOT NULL DEFAULT '',
        project_path  TEXT    NOT NULL,
        registered_at TEXT    NOT NULL
            DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
    );
    CREATE INDEX IF NOT EXISTS idx_ports_port    ON ports(port);
    CREATE INDEX IF NOT EXISTS idx_ports_project ON ports(project);
    """

    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._con = sqlite3.connect(str(db_path))
        self._con.executescript(self.SCHEMA)
        self._con.commit()

    # ---- CRUD ----

    def register(
        self,
        port: int,
        project: str,
        description: str = "",
        project_path: Path | str | None = None,
    ) -> RegistryEntry:
        """Register a port.

        * Same project re-registering the same port → update description/path, return entry.
        * Different project → ConflictError.
        * Brand-new port → insert, return entry.
        """
        project_path = str(project_path or Path.cwd())

        existing = self.get(port)
        if existing is not None:
            if existing.project == project:
                # Idempotent re-registration: refresh metadata
                self._con.execute(
                    "UPDATE ports SET description=?, project_path=?, "
                    "registered_at=strftime('%Y-%m-%dT%H:%M:%fZ','now') "
                    "WHERE port=?",
                    (description, project_path, port),
                )
                self._con.commit()
                return self.get(port)
            raise ConflictError(
                f"Port {port} is already registered to: "
                f"{existing.project} ({existing.project_path})"
            )

        cur = self._con.execute(
            "INSERT INTO ports (port, project, description, project_path) "
            "VALUES (?, ?, ?, ?)",
            (port, project, description, project_path),
        )
        self._con.commit()
        return self.get(port)

    def release(self, port: int) -> bool:
        """Remove a port from the registry. Returns True if something was deleted."""
        cur = self._con.execute("DELETE FROM ports WHERE port=?", (port,))
        self._con.commit()
        return cur.rowcount > 0

    def get(self, port: int) -> Optional[RegistryEntry]:
        row = self._con.execute(
            "SELECT id, port, project, description, project_path, registered_at "
            "FROM ports WHERE port=?",
            (port,),
        ).fetchone()
        if row is None:
            return None
        return RegistryEntry(
            id=row[0], port=row[1], project=row[2],
            description=row[3], project_path=row[4], registered_at=row[5],
        )

    def list_all(self) -> List[RegistryEntry]:
        rows = self._con.execute(
            "SELECT id, port, project, description, project_path, registered_at "
            "FROM ports ORDER BY port"
        ).fetchall()
        return [
            RegistryEntry(id=r[0], port=r[1], project=r[2],
                          description=r[3], project_path=r[4], registered_at=r[5])
            for r in rows
        ]

    def find_by_project(self, project: str) -> List[RegistryEntry]:
        rows = self._con.execute(
            "SELECT id, port, project, description, project_path, registered_at "
            "FROM ports WHERE project=? ORDER BY port",
            (project,),
        ).fetchall()
        return [
            RegistryEntry(id=r[0], port=r[1], project=r[2],
                          description=r[3], project_path=r[4], registered_at=r[5])
            for r in rows
        ]

    def close(self) -> None:
        self._con.close()


# ---------------------------------------------------------------------------
# Scanner (read-only — never mutates registry)
# ---------------------------------------------------------------------------

class Scanner:
    """Live port scanner: Windows netstat + WSL ss, merged."""

    @staticmethod
    def _runcmd(cmd: List[str], timeout: int = 10) -> subprocess.CompletedObject:
        try:
            return subprocess.run(
                cmd, capture_output=True, text=True, timeout=timeout,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return subprocess.CompletedProcess(cmd, 1, "", "")

    @staticmethod
    def parse_netstat_line(line: str) -> List[LiveListener]:
        line = line.strip()
        if "LISTENING" not in line:
            return []
        parts = line.split()
        if len(parts) < 5:
            return []
        local = parts[1]
        if ":" not in local:
            return []
        try:
            port = int(local.rsplit(":", 1)[1])
            pid = int(parts[4])
        except (ValueError, IndexError):
            return []
        return [LiveListener(port=port, pid=pid, namespace="windows")]

    @staticmethod
    def parse_ss_line(line: str) -> List[LiveListener]:
        line = line.strip()
        if not line.startswith("LISTEN"):
            return []
        parts = line.split()
        if len(parts) < 4:
            return []
        local_addr = parts[3]
        if ":" not in local_addr:
            return []
        try:
            port = int(local_addr.rsplit(":", 1)[1])
        except (ValueError, IndexError):
            return []
        import re
        m = re.search(r'users:\(\("([^"]+)",pid=(\d+),', line)
        process_name = m.group(1) if m else ""
        pid = int(m.group(2)) if m else 0
        return [LiveListener(port=port, pid=pid, namespace="wsl", process_name=process_name)]

    def scan_windows(self) -> List[LiveListener]:
        result = self._runcmd(["netstat", "-ano"])
        listeners: List[LiveListener] = []
        for line in result.stdout.splitlines():
            listeners.extend(self.parse_netstat_line(line))
        return listeners

    def scan_wsl(self) -> List[LiveListener]:
        result = self._runcmd(
            ["wsl", "-d", "Ubuntu", "-e", "ss", "-tlnp"]
        )
        listeners: List[LiveListener] = []
        for line in result.stdout.splitlines():
            listeners.extend(self.parse_ss_line(line))
        return listeners

    def scan(self) -> List[LiveListener]:
        listeners = self.scan_windows()
        listeners.extend(self.scan_wsl())
        return listeners

    def conflicts_with(self, entries: List[RegistryEntry]) -> List[dict]:
        """Return registry entries whose ports appear in the live scan."""
        live_ports = {l.port for l in self.scan()}
        return [
            {
                "port":     e.port,
                "project":  e.project,
                "registry": True,
                "live":     e.port in live_ports,
                "pid":      next((l.pid for l in self.scan() if l.port == e.port), None),
            }
            for e in entries
        ]


# ---------------------------------------------------------------------------
# Project file (.ports)
# ---------------------------------------------------------------------------

def load_project_file(project_root: Path) -> List[dict]:
    path = project_root / ".ports"
    if not path.exists():
        return []
    return json.loads(path.read_text())


def save_project_file(project_root: Path, entries: List[dict]) -> None:
    path = project_root / ".ports"
    path.write_text(json.dumps(entries, indent=2))


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def cmd_init(args: argparse.Namespace) -> int:
    path = Path(args.project_dir) / ".ports"
    if path.exists():
        print(f".ports already exists: {path}")
        return 0
    save_project_file(Path(args.project_dir), [])
    print(f"Created {path}")
    return 0


def cmd_register(args: argparse.Namespace) -> int:
    reg = Registry(Path(args.registry))
    try:
        entry = reg.register(
            port=args.port,
            project=args.project,
            description=args.description or "",
            project_path=args.project_dir,
        )
    except ConflictError as exc:
        print(f"CONFLICT: {exc}", file=sys.stderr)
        return 1
    print(f"Registered port {entry.port} → {entry.project} ({entry.registered_at})")

    # Keep .ports file in sync
    pf = load_project_file(Path(args.project_dir))
    pf = [e for e in pf if e["port"] != args.port]
    pf.append({
        "port": entry.port,
        "description": entry.description,
        "project_path": entry.project_path,
        "registered_at": entry.registered_at,
    })
    save_project_file(Path(args.project_dir), pf)
    reg.close()
    return 0


def cmd_release(args: argparse.Namespace) -> int:
    reg = Registry(Path(args.registry))
    entry = reg.get(args.port)
    if entry is None:
        print(f"Port {args.port} is not registered.")
        reg.close()
        return 1
    if entry.project != args.project:
        print(
            f"Port {args.port} is registered to {entry.project}, not {args.project}.",
            file=sys.stderr,
        )
        reg.close()
        return 1
    reg.release(args.port)
    pf = load_project_file(Path(args.project_dir))
    pf = [e for e in pf if e["port"] != args.port]
    save_project_file(Path(args.project_dir), pf)
    print(f"Released port {args.port}")
    reg.close()
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    reg = Registry(Path(args.registry))
    entries = reg.list_all()
    if not entries:
        print("No ports registered.")
        reg.close()
        return 0

    scanner = Scanner()
    conflicts = scanner.conflicts_with(entries)
    conflict_map = {c["port"]: c for c in conflicts}

    print(f"{'PORT':>6}  {'PROJECT':<30}  {'DESCRIPTION':<20}  {'LIVE':5}  {'PID':>6}")
    print("-" * 80)
    for e in entries:
        c = conflict_map.get(e.port, {})
        live = "YES" if c.get("live") else "no"
        pid = str(c.get("pid") or "—")
        print(f"{e.port:>6}  {e.project:<30}  {e.description:<20}  {live:5}  {pid:>6}")
    reg.close()
    return 0


def cmd_check(args: argparse.Namespace) -> int:
    reg = Registry(Path(args.registry))
    entries = reg.list_all()
    scanner = Scanner()
    conflicts = scanner.conflicts_with(entries)

    live = [c for c in conflicts if c["live"]]
    if live:
        for c in live:
            pid = c.get("pid") or "?"
            print(
                f"CONFLICT: port {c['port']} registered to {c['project']} "
                f"but live as PID {pid}",
                file=sys.stderr,
            )
        reg.close()
        return 1

    if not entries:
        print("No registered ports to check.")
    else:
        print(f"All {len(entries)} registered port(s) clear.")
    reg.close()
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="ports",
        description="Local port registry — bookkeeping + live scanner, no OS locks.",
    )
    p.add_argument(
        "--registry", default=None,
        help="Path to registry.db (default: %(default)s)",
    )
    sub = p.add_subparsers(dest="command")

    # init
    sp = sub.add_parser("init", help="Create .ports file in project dir")
    sp.add_argument("--project-dir", default=".", help="Project root (default: cwd)")

    # register
    sp = sub.add_parser("register", help="Claim a port for a project")
    sp.add_argument("port", type=int)
    sp.add_argument("project")
    sp.add_argument("--description", default="", help="What uses this port")
    sp.add_argument("--project-dir", default=".", help="Project root")
    sp.add_argument("--registry", default=None)

    # release
    sp = sub.add_parser("release", help="Release a port back to the pool")
    sp.add_argument("port", type=int)
    sp.add_argument("project")
    sp.add_argument("--project-dir", default=".", help="Project root")
    sp.add_argument("--registry", default=None)

    # list
    sp = sub.add_parser("list", help="List all registered ports with live status")
    sp.add_argument("--registry", default=None)

    # check
    sp = sub.add_parser("check", help="Verify registered ports vs live listeners")
    sp.add_argument("--registry", default=None)

    return p


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    # Resolve registry path once, attach to namespace for every subcommand
    default = str(default_registry_path())
    registry_path = getattr(args, "registry", None) or default
    args.registry = registry_path

    dispatch = {
        "init": cmd_init,
        "register": cmd_register,
        "release": cmd_release,
        "list": cmd_list,
        "check": cmd_check,
    }
    fn = dispatch.get(args.command)
    if fn is None:
        parser.print_help()
        return 1
    return fn(args)


if __name__ == "__main__":
    sys.exit(main())
