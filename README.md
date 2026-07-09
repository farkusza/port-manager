# port-manager

> Zero-dep dev port allocator with live scan, health probes, and an HTTP status server.
> **No daemon. No OS-level port locking.** State lives in `%LOCALAPPDATA%\port-manager\` on Windows, `~/.local/state/port-manager/` on Linux/macOS.

[![PyPI](https://img.shields.io/pypi/v/farkus-port-manager)](https://pypi.org/project/farkus-port-manager/)
[![Python](https://img.shields.io/pypi/pyversions/farkus-port-manager)](https://pypi.org/project/farkus-port-manager/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![CI](https://img.shields.io/github/actions/workflow/status/farkusza/port-manager/ci.yml)](https://github.com/farkusza/port-manager/actions)

`port-manager` is the missing plumbing between "I need port X for service Y" and "actually binding it." Claim ports for named services, see what your registry thinks vs. what the OS is actually doing, scan ranges for squatters and conflicts, expose a live HTTP endpoint for status queries.

Optional Rich integration: install `pip install port-manager[rich]` for tables + progress bars instead of plain text.

---

## Install

### pip (developers)

```bash
# NOTE: PyPI has the bare "port-manager" name (unrelated project, Portuguese
# description). Our PyPI package is "farkus-port-manager"; the CLI binary
# you invoke after install is still "port-manager".
pip install farkus-port-manager
# or with rich tables + progress bars:
pip install farkus-port-manager[rich]
```

### Standalone .exe (Windows users without pip)

Download `port-manager.exe` from the [latest release](https://github.com/farkusza/port-manager/releases/latest). Drop it on your `PATH`, done. No Python required.

### From source

```bash
git clone https://github.com/farkusza/port-manager.git
cd port-manager
pip install -e .
```

---

## Commands

| Command | Purpose |
|---|---|
| `port-manager alloc <service> [lo-hi]` | Claim a free TCP port for `<service>`, print it |
| `port-manager show <service>` | Print the claimed port (blank if free) |
| `port-manager free <service>` | Release a claim |
| `port-manager list` | Show all active claims |
| `port-manager scan [lo-hi]` | Scan a range for squatting / conflicts |
| `port-manager health <service>` | Check if a claimed port is still alive |
| `port-manager probe [host] [port]` | Start the HTTP status server (default `127.0.0.1:4783`) |
| `port-manager help [command]` | Show help (per-command detail for `scan`) |

Run `port-manager` (no args) for the full help text.

---

## Quick start

```bash
# Claim port 3789 for "backend", print it
port-manager alloc backend 3700-3799
# → 3789

# Later: who had backend?
port-manager show backend
# → 3789

# Release it
port-manager free backend

# What's actually happening on 3000-3999?
port-manager scan 3000-3999
# → table: PORT │ STATUS   │ TAG     │ OWNER
#          3789 │ CLAIMED  │ backend │ -
#          4432 │ SQUATTER │ -       │ node.exe -> server.js (pid 471)
#          scanned 3000-3999 (1000 ports) in 2.4s — CLAIMED: 1, SQUATTER: 1, FREE: 998 (hidden)

# Is my backend still alive?
port-manager health backend
# → {"service": "backend", "port": 3789, "pid": 12345, "status": "ok"}
```

---

## Library

```python
from port_manager import alloc, free, show, list_claims
from port_manager import serve_probe, stop_probe, health, find_free

# Claim a port
claim = alloc("backend", lo=5000, hi=5010)
print(claim.port, claim.pid)   # e.g. 5007 12345

# Look it up
assert show("backend").port == claim.port

# Health check
status = health("backend")
# → {"service": "backend", "port": 5007, "pid": 12345, "status": "ok"}

# Release
free("backend")

# HTTP probe server — GET /who-holds/<port> → JSON
t = serve_probe(host="127.0.0.1", port=4783)
# ...
stop_probe(t)
```

---

## What `scan` finds

| Status | Meaning |
|---|---|
| `FREE` | Not in the registry, not listening on the OS. Hidden by default in output. |
| `CLAIMED` | In the registry, not listening (healthy idle claim). |
| `CONFLICT` | In the registry AND listening on the OS (something else grabbed it). |
| `SQUATTER` | Not in the registry, but listening (someone else is on your range). |

The `Owner` column shows the process name, PID, and (when relevant) the script the process is running — e.g. `python.exe -> server.py (pid 28944)` or `node.exe -> dev-server.js (pid 471)`.

Scan runs against `127.0.0.1` only. Full 1000-port range takes ~2-5 s on localhost via 50-worker thread pool.

---

## Design choices

- **No OS-level port locking.** The scanner is read-only. Binding is the service's responsibility.
- **Service-dedup.** Re-claiming the same port for the same service returns the existing claim (idempotent). Different service gets `RuntimeError`.
- **Stale-claim reaping.** Claims older than 1 h whose PID is no longer alive are reaped on the next `alloc` for that range. PID-liveness based, not just time.
- **Advisory file lock** for cross-process concurrency (POSIX `fcntl`, Windows `msvcrt`).
- **Optional Rich.** Zero-dep at the core; install `port-manager[rich]` for tables + progress bars.

---

## State

```
%LOCALAPPDATA%\port-manager\ports\
├── .lock                  ← advisory fd-lock
├── services.json          ← {"backend": "3789.claim"}
├── 3789.claim             ← JSON: {service, port, pid, ts}
└── events.jsonl           ← JSONL event log (alloc / free / probe hits)
```

The event log is the foundation for the planned `watch` command (HTTP-streamed live status hooks).

---

## Development

```bash
git clone https://github.com/farkusza/port-manager.git
cd port-manager
pip install -e ".[rich]"
pytest
```

### Build a standalone .exe (Windows)

```bash
pip install pyinstaller
pyinstaller ports.spec --clean --noconfirm
# → dist/port-manager.exe (single-file, ~15 MB, zero Python required on target)
```

### Publish a release

1. Bump version in `pyproject.toml`
2. `python -m build` → wheel + sdist in `dist/`
3. `twine upload dist/*` (or use the GitHub Actions PyPI trusted publisher)
4. Tag + push; CI builds the `.exe` and attaches it to the release

---

## License

MIT — see [LICENSE](LICENSE).