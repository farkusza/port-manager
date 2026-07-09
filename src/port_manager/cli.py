#!/usr/bin/env python3
"""CLI entry point for port-manager."""
from __future__ import annotations

import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List, Tuple

# ---------------------------------------------------------------------------
# rich — optional, graceful fallback
# ---------------------------------------------------------------------------
try:
    from rich.console import Console
    from rich.table import Table
    from rich import print as rprint
    from rich.progress import Progress, BarColumn, TimeElapsedColumn, TimeRemainingColumn
    _HAS_RICH = True
    _CONSOLE = Console()
except ImportError:  # pragma: no cover — rich not installed
    _HAS_RICH = False
    _CONSOLE = None  # type: ignore[assignment]

from port_manager.core import (
    alloc, free, find_free, health, list_claims, show,
    serve_probe, stop_probe, _port_in_use,
)
from port_manager import _port_owner

# ---------------------------------------------------------------------------
# Help text — single source of truth for every command
# ---------------------------------------------------------------------------

_HELP_MAIN = """\
port-manager — zero-dep dev port allocator

USAGE
  port-manager <command> [args]

COMMANDS
  alloc <service> [lo-hi]   Claim a free TCP port and print it
  show  <service>           Print the claimed port (blank if free)
  free  <service>           Release a claimed port
  list                      Show all active claims
  scan [lo-hi]              Scan a port range for squatting / conflicts
  health <service>          Check if a claimed port is still healthy
  probe [host] [port]       Start HTTP probe server (default 127.0.0.1:4783)
  help [command]            Show this help or detailed help for a command

ARGUMENTS
  service       Any string identifier (e.g. backend, frontend, api)
  lo-hi         Port range as lo-hi (default 3000-3999 when omitted)
  host          Probe bind address (default 127.0.0.1)
  port          Probe listen port (default 4783)

STATE
  Linux/mac : $XDG_STATE_HOME/port-manager/ or ~/.local/state/port-manager/
  Windows   : %LOCALAPPDATA%\\port-manager\\

EXAMPLES
  port-manager alloc backend 3700-3799
  port-manager show  backend
  port-manager free  backend
  port-manager list
  port-manager scan 3700-3799
  port-manager health backend
  port-manager help scan

SHORTCUTS
  --help, -h    Same as bare `port-manager` (shows this text)
"""

_HELP_SCAN = """\
scan — probe a port range for conflicts and squatters

SYNOPSIS
  port-manager scan [lo-hi]

ARGUMENTS
  lo-hi         Inclusive port range to scan.
                Default: 3000-3999  Example: 3700-3799

OUTPUT
  Rich table (if rich is installed) or plain text:
    PORT     STATUS    TAG
    ─────────────────────────────
    3000     FREE      -
    3007     CLAIMED   web-ui
    3758     CONFLICT  backend  ← two things think they own 3758

  STATUS values:
    FREE        Not claimed by port-manager, not listening on OS
    CLAIMED     In port-manager's claim list, not listening (healthy)
    CONFLICT    In port-manager's claim list AND listening on OS
    SQUATTER    Not in port-manager, but listening on OS

EXIT CODES
  0   Always (machine-readable output on stdout)

BEHAVIOUR
  - Parallelised with a 50-worker thread pool over 0.2 s connect timeouts.
  - Full 3000-3999 scan: ~2-5 s on localhost (vs ~2 min sequential).
  - Runs against 127.0.0.1 only (no external interface scan).
"""

_HELP_UNKNOWN = """\
Unknown command: {cmd!r}

Type `port-manager` or `port-manager help` for the command list.
"""

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _probe(port: int) -> Dict:
    listening = _port_in_use(port)
    svc = None
    if listening:
        for c in list_claims().values():
            if c.port == port:
                svc = c.service
                break
    owner = None
    if listening:
        try:
            owner = _port_owner.port_owner(port)
        except (OSError, subprocess.TimeoutExpired):
            owner = None
    return {"port": port, "listening": listening, "svc": svc, "owner": owner}


def _scan_range(lo: int, hi: int, bind_addr: str = "127.0.0.1") -> Tuple[List[Dict], float]:
    """Fast parallel port scan."""
    ports = list(range(lo, hi + 1))
    t0 = time.time()
    results_lock = threading.Lock()
    results: List[Dict] = []

    # ponytail: one loop — rich wraps the same pool with a progress bar
    def _collect():
        with ThreadPoolExecutor(max_workers=50) as pool:
            futures = {pool.submit(_probe, p): p for p in ports}
            for fut in as_completed(futures):
                with results_lock:
                    results.append(fut.result())
                if _HAS_RICH:
                    progress.update(task_id, advance=1, refresh=True)

    if _HAS_RICH:
        from rich.progress import Progress
        progress = Progress(
            "[progress.description]{task.description}",
            BarColumn(),
            "[progress.percentage]{task.percentage:>3.0f}%",
            TimeElapsedColumn(),
            TimeRemainingColumn(),
            console=_CONSOLE,
        )
        task_id = progress.add_task(f"scanning {lo}-{hi}", total=len(ports))
        with progress:
            _collect()
    else:
        _collect()

    claimed_ports = {c.port: c.service for c in list_claims().values()}
    out: List[Dict] = []
    for r in results:
        svc = claimed_ports.get(r["port"]) or r.get("svc") or "-"
        if svc and svc != "-":
            status = "CONFLICT" if r["listening"] else "CLAIMED"
        elif r["listening"]:
            status = "SQUATTER"
        else:
            status = "FREE"
        out.append({"port": r["port"], "status": status, "tag": svc, "owner": r.get("owner")})

    elapsed = time.time() - t0
    out.sort(key=lambda r: r["port"])
    return out, elapsed


def _style_status(status: str) -> str:
    return status


def _print_help(topic: str) -> int:
    text = {
        "alloc":  None,  # minimal; extend if needed
        "show":   None,
        "free":   None,
        "list":   None,
        "scan":   _HELP_SCAN,
        "probe":  None,
    }.get(topic)
    if text is None:
        print(_HELP_UNKNOWN.format(cmd=topic), file=sys.stderr)
        return 1
    print(text)
    return 0


# ---------------------------------------------------------------------------
# dispatch
# ---------------------------------------------------------------------------

def main() -> None:
    args = sys.argv[1:]

    # bare call or --help / -h
    if not args or args[0] in ("--help", "-h"):
        print(_HELP_MAIN)
        return

    cmd = args[0]

    # help <command>
    if cmd == "help":
        topic = args[1] if len(args) > 1 else ""
        if not topic:
            print(_HELP_MAIN)
            return
        rc = _print_help(topic)
        sys.exit(rc)

    # alloc ...
    if cmd == "alloc":
        if len(args) < 2:
            print("alloc: missing <service>\nUsage: port-manager alloc <service> [lo-hi]", file=sys.stderr)
            sys.exit(3)
        service = args[1]
        lo = hi = None
        if len(args) >= 3:
            try:
                lo_str, hi_str = args[2].split("-", 1)
                lo, hi = int(lo_str), int(hi_str)
                if lo > hi:
                    raise ValueError
            except (ValueError, AttributeError):
                print(f"alloc: bad range {args[2]!r} (expected lo-hi, e.g. 3700-3799)", file=sys.stderr)
                sys.exit(3)
        try:
            claim = alloc(service, lo=lo or 3000, hi=hi or 3999)
        except RuntimeError as exc:
            print(f"alloc: {exc}", file=sys.stderr)
            sys.exit(2)
        print(claim.port)
        return

    # show ...
    if cmd == "show":
        if len(args) < 2:
            print("show: missing <service>\nUsage: port-manager show <service>", file=sys.stderr)
            sys.exit(3)
        claim = show(args[1])
        if claim is None:
            sys.exit(1)
        print(claim.port)
        return

    # free ...
    if cmd == "free":
        if len(args) < 2:
            print("free: missing <service>\nUsage: port-manager free <service>", file=sys.stderr)
            sys.exit(3)
        ok = free(args[1])
        if not ok:
            sys.exit(1)
        return

    # list ...
    if cmd == "list":
        claims = list_claims()
        if _HAS_RICH:
            console = Console()
            table = Table(title="Active Port Claims", show_edge=True, show_header=True)
            table.add_column("Service", style="cyan", no_wrap=True)
            table.add_column("Port", justify="right", style="green")
            table.add_column("PID", justify="right", style="magenta")
            for svc in sorted(claims):
                c = claims[svc]
                table.add_row(c.service, str(c.port), str(c.pid))
            console.print(table)
        else:
            for svc in sorted(claims):
                c = claims[svc]
                print(f"{c.service:<20} {c.port}  {c.pid}")
        return

    # scan [lo-hi]
    if cmd == "scan":
        lo = hi = None
        if len(args) >= 2:
            try:
                lo_str, hi_str = args[1].split("-", 1)
                lo, hi = int(lo_str), int(hi_str)
                if lo > hi:
                    raise ValueError
            except (ValueError, AttributeError):
                print(f"scan: bad range {args[1]!r} (expected lo-hi, e.g. 3700-3799)", file=sys.stderr)
                sys.exit(3)
        lo = lo or 3000
        hi = hi or 3999
        results, elapsed = _scan_range(lo, hi)
        if _HAS_RICH:
            console = Console()
            table = Table(title=f"Scan {lo}-{hi}", show_edge=False, show_header=True)
            table.add_column("Port", justify="right")
            table.add_column("Status", justify="left")
            table.add_column("Tag", justify="left")
            table.add_column("Owner", justify="left")
            counts: Dict[str, int] = {}
            display_rows = [r for r in results if r["status"] != "FREE"]
            for r in display_rows:
                counts[r["status"]] = counts.get(r["status"], 0) + 1
                style_map = {"CLAIMED": "green", "CONFLICT": "bold red", "SQUATTER": "yellow"}
                table.add_row(str(r["port"]), f"[{style_map.get(r['status'], '')}]{r['status']}[/]", r["tag"], r.get("owner") or "-")
            console.print(table)
            counts_str = ", ".join(f"{k}: {v}" for k, v in sorted(counts.items()))
            free_count = sum(1 for r in results if r["status"] == "FREE")
            if free_count:
                counts_str += f", FREE: {free_count} (hidden)"
            console.print(f"[dim]scanned {lo}-{hi} ({hi - lo + 1} ports) in {elapsed:.1f}s — {counts_str}[/]")
        else:
            header = f"{'PORT':<8} {'STATUS':<10} {'TAG':<20} OWNER"
            print(header)
            print("-" * len(header))
            counts = {}
            display_rows = [r for r in results if r["status"] != "FREE"]
            for r in display_rows:
                counts[r["status"]] = counts.get(r["status"], 0) + 1
                print(f"{r['port']:<8} {r['status']:<10} {r['tag']:<20} {r.get('owner') or '-'}")
            print("-" * len(header))
            parts = [f"{k}: {v}" for k, v in sorted(counts.items())]
            free_count = sum(1 for r in results if r["status"] == "FREE")
            if free_count:
                parts.append(f"FREE: {free_count} (hidden)")
            print(f"scanned {lo}-{hi} ({hi - lo + 1} ports) in {elapsed:.1f}s — " + ", ".join(parts))
        return

    # health <service>
    if cmd == "health":
        if len(args) < 2:
            print("health: missing <service>\nUsage: port-manager health <service>", file=sys.stderr)
            sys.exit(3)
        result = health(args[1])
        if result is None:
            print(f"health: {args[1]}: not claimed", file=sys.stderr)
            sys.exit(1)
        if _HAS_RICH:
            console = Console()
            style = {
                "ok": "green",
                "conflict": "bold red",
                "dead": "red",
            }.get(result["status"], "")
            console.print_json(data=result)
        else:
            print(f"{result['service']}\t{result['port']}\t{result['pid']}\t{result['status']}")
        return

    # probe [host] [port]
    if cmd == "probe":
        host = args[1] if len(args) > 1 else "127.0.0.1"
        port = int(args[2]) if len(args) > 2 else 4783
        t = serve_probe(host=host, port=port)
        print(f"probe listening on {host}:{port}  (Ctrl-C to stop)")
        try:
            while t.is_alive():
                time.sleep(0.5)
        except KeyboardInterrupt:
            print()
        finally:
            stop_probe(t)
        return

    # unknown
    print(_HELP_UNKNOWN.format(cmd=cmd), file=sys.stderr)
    sys.exit(1)


if __name__ == "__main__":
    main()
