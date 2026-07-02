"""End-to-end: init → register → check cycle."""
import tempfile
from pathlib import Path

from ports import Registry, Scanner


def test_e2e_collision_detection():
    with tempfile.TemporaryDirectory() as d:
        db = Path(d) / "registry.db"
        reg = Registry(db)

        entry = reg.register(8000, "fd-dab", "API", Path("/home/farkus/farkus-analytics"))
        assert entry.port == 8000

        entries = reg.list_all()
        scanner = Scanner()
        conflicts = scanner.conflicts_with(entries)

        conflict_map = {c["port"]: c for c in conflicts}
        reg.close()

        result = conflict_map.get(8000)
        assert result is not None
        assert result["project"] == "fd-dab"
        assert "live" in result
