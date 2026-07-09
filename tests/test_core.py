"""
tests/test_core.py
=================
Fast, isolated pytest suite for `port_manager.core`.
Per-test tmpdir for state root; no symlinks, fully Windows-friendly.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

# ensure src/ importable when run via pytest from repo root
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from port_manager.core import (  # noqa: E402
    Claim,
    _ports_dir,
    alloc,
    free,
    list_claims,
    show,
)


# ── fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def _isolated_state(tmp_path, monkeypatch):
    """Redirect the state dir to a fresh tmp dir per test."""
    test_dir = tmp_path / "pm-state"
    (test_dir / "ports").mkdir(parents=True)
    monkeypatch.setattr("port_manager.core._state_root", lambda: test_dir)
    yield test_dir


# ── alloc ─────────────────────────────────────────────────────────────────────

class TestAlloc:
    def test_returns_claim_in_range(self):
        c = alloc("web", lo=5000, hi=5010)
        assert isinstance(c, Claim)
        assert c.service == "web"
        assert 5000 <= c.port <= 5010
        assert c.pid == os.getpid()

    def test_alloc_same_service_returns_same_port(self):
        c1 = alloc("svc-a", lo=6000, hi=6010)
        c2 = alloc("svc-a", lo=6000, hi=6010)
        assert c1.port == c2.port

    def test_alloc_two_distinct_services_get_different_ports(self):
        c1 = alloc("a", lo=6200, hi=6210)
        c2 = alloc("b", lo=6200, hi=6210)
        assert c1.port != c2.port

    def test_alloc_exhausted_range_raises(self):
        for i in range(4000, 4010):
            alloc(f"ex{i}", lo=4000, hi=4009)
        with pytest.raises(RuntimeError, match="No free port"):
            alloc("should-fail", lo=4000, hi=4009)

    def test_alloc_bad_range_raises(self):
        with pytest.raises(ValueError):
            alloc("x", lo=9000, hi=8999)

    def test_alloc_default_range(self):
        c = alloc("default-test")
        assert 3000 <= c.port <= 3999

    def test_alloc_writes_claim_file_and_index(self):
        c = alloc("fm", lo=7000, hi=7010)
        assert (_ports_dir() / f"{c.port}.claim").exists()
        idx = json.loads((_ports_dir() / "services.json").read_text())
        assert idx.get("fm") == f"{c.port}.claim"


# ── show ──────────────────────────────────────────────────────────────────────

class TestShow:
    def test_show_after_alloc(self):
        c = alloc("visible", lo=7100, hi=7110)
        got = show("visible")
        assert got is not None
        assert got.port == c.port
        assert got.service == "visible"

    def test_show_missing_returns_none(self):
        assert show("does-not-exist") is None


# ── free ──────────────────────────────────────────────────────────────────────

class TestFree:
    def test_free_removes_claim(self):
        c = alloc("evict-me", lo=7200, hi=7210)
        assert show("evict-me") is not None
        assert free("evict-me") is True
        assert show("evict-me") is None

    def test_free_missing_returns_false(self):
        assert free("ghost") is False


# ── list ──────────────────────────────────────────────────────────────────────

class TestList:
    def test_list_empty_initially(self):
        assert list_claims() == {}

    def test_list_reflects_claims(self):
        alloc("alpha", lo=7300, hi=7310)
        alloc("beta", lo=7400, hi=7410)
        claims = list_claims()
        assert "alpha" in claims
        assert "beta" in claims
        assert claims["alpha"].port != claims["beta"].port

    def test_list_excludes_freed(self):
        alloc("here", lo=7500, hi=7510)
        free("here")
        assert "here" not in list_claims()
