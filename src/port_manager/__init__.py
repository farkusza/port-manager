"""port_manager — zero-dep dev port allocator.

Install:  pip install -e .
CLI:      port-manager alloc backend 3700-3799
         port-manager show  backend
         port-manager free   backend
         port-manager list
         port-manager scan  3000-3999
         port-manager health backend
         port-manager probe 127.0.0.1 4783

Library:
    from port_manager import alloc, free, show, list_claims, serve_probe, stop_probe
    from port_manager import health, find_free
"""

from port_manager.core import (  # noqa: F401
    Claim,
    alloc,
    find_free,
    free,
    health,
    list_claims,
    serve_probe,
    show,
    stop_probe,
)

__version__ = "0.2.0"
__all__ = [
    "Claim",
    "alloc",
    "find_free",
    "free",
    "health",
    "list_claims",
    "serve_probe",
    "show",
    "stop_probe",
]
