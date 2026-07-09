# Changelog

All notable changes to `port-manager` are documented here.
Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Versioning: [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] — 2026-07-09

### Added
- `port-manager alloc <service> [lo-hi]` — claim a free TCP port for a named service
- `port-manager show <service>` — print the claimed port (blank if free)
- `port-manager free <service>` — release a claim
- `port-manager list` — show all active claims
- `port-manager scan [lo-hi]` — scan a range for squatting / conflicts (50-worker thread pool, FREE ports hidden by default)
- `port-manager health <service>` — check if a claimed port is still alive
- `port-manager probe [host] [port]` — start HTTP status server (`GET /who-holds/<port>`)
- Service-dedup: re-claiming the same port for the same service returns the existing claim
- Stale-claim reaping: claims whose PID is no longer alive get cleared on the next `alloc`
- Advisory file lock for cross-process concurrency (POSIX `fcntl`, Windows `msvcrt`)
- Optional Rich integration: tables + progress bars via `pip install port-manager[rich]`
- Platform-safe state directory (`%LOCALAPPDATA%\port-manager\` on Windows, `~/.local/state/port-manager/` on Linux/macOS)
- Zero external dependencies at the core
- JSONL event log (`events.jsonl`) for the planned `watch` streaming command

[0.1.0]: https://github.com/farkusza/port-manager/releases/tag/v0.1.0