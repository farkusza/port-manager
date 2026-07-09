# Changelog

All notable changes to `ports-registry` are documented here.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] — 2026-07-08

### Added
- `ports init` — create `.ports` file in project root
- `ports register <port> <project>` — claim a port for a project
- `ports release <port> <project>` — release a port back to the pool
- `ports list` — show all registered ports with live status (port + project + PID)
- `ports check` — verify registered ports against live listeners; exits non-zero on conflict
- Idempotent re-registration: re-registering the same port for the same project updates metadata and succeeds
- Cross-project re-registration raises `ConflictError` with the owner's name and path
- Windows + WSL aware scanner: cross-references `netstat -ano` and `wsl -d Ubuntu -e ss -tlnp`
- SQLite-backed registry at `%LOCALAPPDATA%\ports-registry\registry.db` (Windows) or `~/.local/share/ports-registry/registry.db` (Linux/macOS)
- `--registry` flag on every command for path override
- `pyproject.toml` for pip-installable distribution (`pip install ports-registry`)
- PyInstaller spec for standalone Windows `.exe` (no Python required on target)
- GitHub Actions CI on push + pull request

[0.1.0]: https://github.com/kyle-farkus/ports-registry/releases/tag/v0.1.0