"""Tests for the live port scanner (Windows netstat + WSL ss)."""
import pytest

from ports import Scanner, LiveListener


def test_parse_netstat_listening_line_windows():
    line = "  TCP    127.0.0.1:8000         0.0.0.0:0              LISTENING       28944"
    listeners = Scanner.parse_netstat_line(line)
    assert len(listeners) == 1
    assert listeners[0].port == 8000
    assert listeners[0].pid == 28944
    assert listeners[0].namespace == "windows"


def test_parse_ss_listening_line_wsl():
    line = 'LISTEN 0  2048  0.0.0.0:8000  0.0.0.0:*  users:((\"uvicorn\",pid=471,fd=14))'
    listeners = Scanner.parse_ss_line(line)
    assert len(listeners) == 1
    assert listeners[0].port == 8000
    assert listeners[0].pid == 471
    assert listeners[0].namespace == "wsl"
    assert listeners[0].process_name == "uvicorn"


def test_parse_non_listening_lines_return_empty():
    assert Scanner.parse_netstat_line("  TCP    0.0.0.0:135         0.0.0.0:0              LISTENING") == []
    assert Scanner.parse_netstat_line("  TCP    127.0.0.1:8000         127.0.0.1:5432         ESTABLISHED 28944") == []
    # Kernel listeners (no users:(...) block) ARE still listeners — surface them
    # with pid=0/process_name="" so the registry knows the port is in use even
    # when it can't identify the owner.
    kernel = Scanner.parse_ss_line("LISTEN 0  128  0.0.0.0:111  0.0.0.0:*")
    assert len(kernel) == 1
    assert kernel[0].port == 111
    assert kernel[0].pid == 0
    assert kernel[0].process_name == ""
    assert kernel[0].namespace == "wsl"
