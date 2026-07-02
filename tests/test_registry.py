"""Tests for the SQLite registry layer."""
import sqlite3
import tempfile
from pathlib import Path

import pytest

from ports import Registry, RegistryEntry, ConflictError


@pytest.fixture
def tmp_registry():
    with tempfile.TemporaryDirectory() as d:
        db_path = Path(d) / "test.db"
        reg = Registry(db_path)
        yield reg
        reg.close()


def test_register_new_port(tmp_registry):
    entry = tmp_registry.register(
        port=3000,
        project="test-app",
        description="Next.js dev server",
        project_path=Path("/tmp/test-app"),
    )
    assert entry.port == 3000
    assert entry.project == "test-app"
    assert entry.id is not None


def test_register_duplicate_port_same_project(tmp_registry):
    """Re-registering the same port for the same project should succeed."""
    entry = tmp_registry.register(3000, "test-app", "first", Path("/tmp/a"))
    updated = tmp_registry.register(3000, "test-app", "second", Path("/tmp/b"))
    assert updated.id == entry.id
    assert updated.project == "test-app"


def test_register_duplicate_port_different_project_raises(tmp_registry):
    tmp_registry.register(3000, "test-app", "x", Path("/tmp/a"))
    with pytest.raises(ConflictError) as exc_info:
        tmp_registry.register(3000, "other-app", "y", Path("/tmp/b"))
    assert "test-app" in str(exc_info.value)


def test_release_port(tmp_registry):
    tmp_registry.register(3000, "test-app", "x", Path("/tmp/a"))
    assert tmp_registry.release(3000) is True
    assert tmp_registry.get(3000) is None
    assert tmp_registry.release(9999) is False


def test_list_all(tmp_registry):
    tmp_registry.register(8001, "app-a", "x", Path("/tmp/a"))
    tmp_registry.register(3000, "app-b", "y", Path("/tmp/b"))
    tmp_registry.register(5432, "app-c", "z", Path("/tmp/c"))
    entries = tmp_registry.list_all()
    assert [e.port for e in entries] == [3000, 5432, 8001]


def test_get_by_port(tmp_registry):
    tmp_registry.register(8000, "fd-dab", "API", Path("/home/farkus/farkus-analytics"))
    entry = tmp_registry.get(8000)
    assert entry is not None
    assert entry.project == "fd-dab"
    assert entry.description == "API"
    assert tmp_registry.get(9999) is None


def test_find_by_project(tmp_registry):
    tmp_registry.register(3000, "fd-dab", "web", Path("/tmp/a"))
    tmp_registry.register(8000, "fd-dab", "api", Path("/tmp/b"))
    tmp_registry.register(5000, "other", "x", Path("/tmp/c"))
    entries = tmp_registry.find_by_project("fd-dab")
    assert [e.port for e in entries] == [3000, 8000]
