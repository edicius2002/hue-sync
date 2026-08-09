"""Fixtures compartidas. Los dobles viven en tests/fakes.py."""

from __future__ import annotations

import pytest
from fakes import FakeBackend, FakeRest


@pytest.fixture
def backend() -> FakeBackend:
    return FakeBackend()


@pytest.fixture
def rest() -> FakeRest:
    return FakeRest()


@pytest.fixture
def session(backend, rest):
    """Sesion con delays casi nulos: los reintentos reales duermen segundos y
    eso convertiria la suite en algo inutilmente lento."""
    from huebpm.hue.client import EntertainmentSession

    s = EntertainmentSession(
        "192.168.1.9", "u" * 40, "a" * 32, "area-1",
        backend=backend, start_delay=0.0, reconnect_delay=0.0, connect_attempts=3,
    )
    s.rest = rest
    return s
