# Ports Registry

Local port bookkeeping for Windows + WSL developers.

No daemon. No OS-level port locking. Just a SQLite registry and a live scanner
that cross-references `netstat -ano` (Windows) and `ss -tlnp` (WSL).

## Commands

| Command       | Purpose                              |
|---------------|--------------------------------------|
| `ports init`  | Create `.ports` file in project root |
| `ports register <port> <project>` | Claim a port for a project |
| `ports release <port> <project>`  | Release a port back to the pool |
| `ports list`  | Show all registered ports + live status |
| `ports check` | Verify registered ports against live listeners |

## Design choices

- Idempotent registration: re-registering the same port for the **same project** updates metadata and succeeds.
- Cross-project re-registration: raises `ConflictError` — the port belongs to someone else.
- No OS locks. The scanner is read-only. Binding is left to the service.
