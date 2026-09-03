from __future__ import annotations

import socket

import pytest

from tabletop_companion.infrastructure.diagnostics import local_addresses


def test_local_addresses_prefer_home_lan_over_virtual_and_vpn_adapters(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    addresses = [
        (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("26.77.107.88", 0)),
        (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("172.24.208.1", 0)),
        (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("192.168.0.32", 0)),
    ]
    monkeypatch.setattr(socket, "getaddrinfo", lambda *args, **kwargs: addresses)

    assert local_addresses()[0] == "192.168.0.32"
