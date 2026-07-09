# ports-registry

> Local port bookkeeping for Windows + WSL developers.
> **No daemon. No OS-level port locking.** Just a SQLite registry + a read-only live scanner.

[![PyPI](https://img.shields.io/pypi/v/ports-registry)](https://pypi.org/project/ports-registry/)
[![Python](https://img.shields.io/pypi/pyversions/ports-registry)](https://pypi.org/project/ports-registry/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![CI](https://img.shields.io/github/actions/workflow/status/farkusza/ports-registry/ci.yml)](https://github.com/farkusza/ports-registry/actions)

`ports` is a small CLI that answers two questions every dev asks daily:

1. *Is this port already in use by something of mine?*
2. *What was I running on port 8000 again?*

It keeps a SQLite-backed **registry** of which ports belong to which projects, and cross-references it against a live **scanner** that reads `netstat -ano` on Windows and `ss -tlnp` inside WSL.

---

## Install

### Option A — pip (developers)

```bash
pip install ports-registry
```

That's it. You now have a `ports` command on your PATH.

### Option B — standalone .exe (Windows users without pip)

Download `ports.exe` from the [latest release](https://github.com/farkusza/ports-registry/releases/latest). Drop it somewhere on your `PATH` (e.g. `C:\Users\<you>\bin\`), and you're done. No Python required.

### Option C — from source

```bash
git clone https://github.com/farkusza/ports-registry.git
cd ports-registry
pip install -e .
```

---

## Quick start

```bash
# Initialize a .ports file in your project root
ports init --project-dir C:\code\my-app

# Claim port 8000 for my-app
ports register 8000 my-app --description "FastAPI dev server"

# Re-registering the same port for the same project is idempotent
ports register 8000 my-app --description "FastAPI dev server (HTTPS)"

# Try to claim 8000 for a DIFFERENT project — this fails loudly
ports register 8000 other-app
# → CONFLICT: Port 8000 is already registered to: my-app (C:\code\my-app)

# List everything, with live status
ports list
# →  PORT  PROJECT  DESCRIPTION           LIVE   PID
#    ─────────────────────────────────────────────────
#      8000  my-app   FastAPI dev server    YES    28944

# Check whether your registered ports are actually live
ports check
# → All 1 registered port(s) clear.

# Release a port
ports release 8000 my-app
```

---

## Commands

| Command | Purpose |
|---|---|
| `ports init` | Create `.ports` file in project root |
| `ports register <port> <project>` | Claim a port for a project |
| `ports release <port> <project>` | Release a port back to the pool |
| `ports list` | Show all registered ports + live status |
| `ports check` | Verify registered ports against live listeners |

Run `ports --help` for full options. The registry lives at `%LOCALAPPDATA%\ports-registry\registry.db` on Windows and `~/.local/share/ports-registry/registry.db` on Linux/macOS. Override per-command with `--registry`.

---

## Design choices

- **Idempotent registration**: re-registering the same port for the **same project** updates metadata and succeeds.
- **Cross-project re-registration** raises `ConflictError` — the port belongs to someone else.
- **No OS locks.** The scanner is read-only. Binding is left to the service.
- **Single-file CLI** (`ports.py`), stdlib only, no third-party dependencies.
- **Windows + WSL aware** by design — the scanner runs both `netstat -ano` and `wsl -d Ubuntu -e ss -tlnp` and merges the results. A port is "live" if either namespace shows a listener.

### Why "no OS-level locking"?

Because if your dev environment says "port 8000 is locked, hands off" and the OS is happily serving it, you've created a *new* problem on top of the one you're trying to solve. `ports` is bookkeeping, not enforcement. The registry tells you what you said was yours; the scanner tells you what the OS actually thinks is live. You decide who wins.

---

## Development

```bash
git clone https://github.com/farkusza/ports-registry.git
cd ports-registry
pip install -e .
pytest
```

### Build a standalone .exe (Windows)

```bash
pip install pyinstaller
pyinstaller ports.spec
# → dist/ports.exe (single-file, ~15 MB, no Python required on target)
```

### Publish a release

1. Bump version in `pyproject.toml`
2. `python -m build` → wheel + sdist in `dist/`
3. `twine upload dist/*`
4. Tag + push; GitHub Actions builds the .exe and attaches it to the release

---

## License

MIT — see [LICENSE](LICENSE).