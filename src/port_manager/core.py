"""
port_manager.core
=================
Zero-dep dev port allocator.

State directory (platform-safe):
  Linux/mac : ${XDG_STATE_HOME:-~/.local/state}/port-manager/
  Windows   : %LOCALAPPDATA%\\port-manager\\

Claim files             : <state>/ports/<port>.claim   (JSON: service, port, pid, ts)
Service lookup in       : <state>/ports/services.json  ({service: port})
HTTP probe (optional)   : GET /who-holds/<port> -> {service, port, pid}
"""

from __future__ import annotations

import http.server
import json
import os
import socket
import sys
import threading
import time
from pathlib import Path
from typing import Dict, List, Optional


# ---------------------------------------------------------------------------
# paths
# ---------------------------------------------------------------------------

def _state_root() -> Path:
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
        return Path(base) / "port-manager"
    xdg = os.environ.get("XDG_STATE_HOME", "")
    if xdg:
        return Path(xdg) / "port-manager"
    return Path.home() / ".local" / "state" / "port-manager"


def _ports_dir() -> Path:
    return _state_root() / "ports"


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _services_path() -> Path:
    return _ports_dir() / "services.json"


def _load_index() -> Dict[str, str]:
    p = _services_path()
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _save_index(idx: Dict[str, str]) -> None:
    # ponytail: plain write — atomic rename is overkill for a dev tool state file
    _services_path().write_text(
        json.dumps(idx, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _port_in_use(port: int, bind_addr: str = "127.0.0.1") -> bool:
    """Probe whether ``port`` is actively listening on ``bind_addr``."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.2)
        try:
            return s.connect_ex((bind_addr, port)) == 0
        except (OSError, socket.error):
            return False


# ---------------------------------------------------------------------------
# public API
# ---------------------------------------------------------------------------

class Claim:
    """Holds a port allocation returned by :func:`alloc`."""

    def __init__(self, service: str, port: int, pid: int) -> None:
        self.service = service
        self.port = port
        self.pid = pid

    def __repr__(self) -> str:
        return f"Claim(service={self.service!r}, port={self.port}, pid={self.pid})"


def alloc(
    service: str,
    lo: int = 3000,
    hi: int = 3999,
    bind_addr: str = "127.0.0.1",
) -> Claim:
    """Allocate a free TCP port in ``[lo, hi]`` and claim it for *service*."""
    if lo > hi:
        raise ValueError(f"Invalid port range: {lo}-{hi}")

    pid = os.getpid()
    _ports_dir().mkdir(parents=True, exist_ok=True)

    idx = _load_index()

    # reuse existing claim for same service
    existing_fn = idx.get(service)
    if existing_fn and (_ports_dir() / existing_fn).exists():
        try:
            data = json.loads((_ports_dir() / existing_fn).read_text(encoding="utf-8"))
            return Claim(service=data["service"], port=int(data["port"]), pid=int(data["pid"]))
        except (json.JSONDecodeError, OSError, KeyError, ValueError):
            pass

    span = hi - lo + 1
    seed = hash(service) % span
    candidates = [lo + ((seed + i) % span) for i in range(span)]

    for port in candidates:
        claim_fn = f"{port}.claim"
        if (_ports_dir() / claim_fn).exists():
            continue
        claimed_ports = {int(fn.stem) for fn in _ports_dir().glob("*.claim") if fn.stem.isdigit()}
        if port in claimed_ports:
            continue
        if _port_in_use(port, bind_addr):
            continue

        # atomic create: O_CREAT|O_EXCL guarantees only one writer wins the race
        claim_path = _ports_dir() / claim_fn
        try:
            fd = os.open(str(claim_path), os.O_WRONLY | os.O_CREAT | os.O_EXCL)
        except FileExistsError:
            continue
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump({"service": service, "port": port, "pid": pid, "ts": time.time()}, fh)
        except OSError:
            try:
                claim_path.unlink(missing_ok=True)
            except OSError:
                pass
            continue

        idx[service] = claim_fn
        _save_index(idx)
        return Claim(service=service, port=port, pid=pid)

    raise RuntimeError(f"No free port in [{lo}, {hi}] for {service=}")


def free(service: str) -> bool:
    """Release a claimed port by service name."""
    idx = _load_index()
    claim_fn = idx.pop(service, None)
    if claim_fn is None:
        return False
    try:
        (_ports_dir() / claim_fn).unlink(missing_ok=True)
    except OSError:
        pass
    _save_index(idx)
    return True


def show(service: str) -> Optional[Claim]:
    """Return the active :class:`Claim` for *service*, or ``None``."""
    idx = _load_index()
    claim_fn = idx.get(service)
    if claim_fn is None:
        return None
    try:
        data = json.loads((_ports_dir() / claim_fn).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return Claim(
        service=data["service"],
        port=int(data["port"]),
        pid=int(data["pid"]),
    )


def list_claims() -> Dict[str, Claim]:
    """Return all current claims keyed by service name."""
    claims: Dict[str, Claim] = {}
    if not _ports_dir().exists():
        return claims
    idx = _load_index()
    for svc, claim_fn in idx.items():
        try:
            data = json.loads((_ports_dir() / claim_fn).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        claims[svc] = Claim(
            service=data["service"],
            port=int(data["port"]),
            pid=int(data["pid"]),
        )
    return claims


# ---------------------------------------------------------------------------
# optional HTTP probe
# ---------------------------------------------------------------------------

class _HoldHandler(http.server.BaseHTTPRequestHandler):
    """Serves ``/who-holds/<port>`` JSON responses."""

    state_ref: Dict[str, Claim]

    def do_GET(self):  # noqa: N802
        import urllib.parse

        parts = urllib.parse.urlparse(self.path).path.strip("/").split("/")
        if len(parts) == 2 and parts[0] == "who-holds":
            try:
                port = int(parts[1])
            except ValueError:
                self._json(400, {"error": "port must be an integer"})
                return
            match = next(
                (c for c in self.state_ref.values() if c.port == port),
                None,
            )
            if match is None:
                self._json(404, {"error": f"port {port} is not held by port-manager"})
            else:
                self._json(200, {"service": match.service, "port": match.port, "pid": match.pid})
            return
        self._json(404, {"error": "try /who-holds/<port>"})

    def _json(self, code: int, body: dict) -> None:
        payload = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, fmt, *args):  # noqa: D401
        pass


def serve_probe(
    host: str = "127.0.0.1",
    port: int = 4783,
) -> threading.Thread:
    """Start a tiny HTTP server answering ``/who-holds/<port>``."""
    claims = list_claims()
    _HoldHandler.state_ref = claims  # type: ignore[attr-defined]
    server = http.server.HTTPServer((host, port), _HoldHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread._server_ref = server  # type: ignore[attr-defined]
    thread.start()
    return thread


def stop_probe(thread: threading.Thread) -> None:
    server = getattr(thread, "_server_ref", None)
    if server is not None:
        server.shutdown()


# ---------------------------------------------------------------------------
# find_free / health
# ---------------------------------------------------------------------------

def find_free(
    count: int = 1,
    lo: int = 3000,
    hi: int = 3999,
    bind_addr: str = "127.0.0.1",
) -> List[int]:
    """Return up to *count* free ports in ``[lo, hi]`` without claiming them."""
    if count < 1:
        raise ValueError("count must be >= 1")
    if lo > hi:
        raise ValueError(f"Invalid port range: {lo}-{hi}")
    claimed = {int(fn.stem) for fn in _ports_dir().glob("*.claim") if fn.stem.isdigit()}
    # ponytail: single pass, count-limited
    return [p for p in range(lo, hi + 1) if p not in claimed and not _port_in_use(p, bind_addr)][:count]


def health(service: str) -> Optional[Dict]:
    """Return status dict for *service*, or ``None`` if not claimed."""
    claim = show(service)
    if claim is None:
        return None
    listening = _port_in_use(claim.port)
    status = "dead" if not listening else "ok"
    return {"service": claim.service, "port": claim.port, "pid": claim.pid, "status": status}
