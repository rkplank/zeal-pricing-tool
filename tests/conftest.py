from __future__ import annotations

import httpx
import pytest


@pytest.fixture(autouse=True)
def _no_ssl_in_httpx_client(monkeypatch: pytest.MonkeyPatch) -> None:
    """Patch httpx.AsyncClient.__init__ to default verify=False for all tests.

    httpx.AsyncClient() initialises an SSL context at construction time.
    On this machine (Windows, missing OPENSSL_Applink) that initialisation
    deadlocks before any request is made.  Defaulting verify=False bypasses
    SSL context creation and unblocks all eight previously hanging tests.

    Why setdefault: tests that explicitly pass verify=True keep that value.
    Why autouse: the deadlock is triggered by any code path that calls
    httpx.AsyncClient(), including app lifespan and CLI helpers exercised
    by smoke tests — so the patch must be active for every test function.
    Production code is never affected; this fixture only runs under pytest.
    """
    _orig = httpx.AsyncClient.__init__

    def _patched_init(self, *args, **kwargs):  # type: ignore[misc]
        kwargs.setdefault("verify", False)
        _orig(self, *args, **kwargs)

    monkeypatch.setattr(httpx.AsyncClient, "__init__", _patched_init)
