"""Isolation de payment : aucun appel venant de l'exterieur ne doit l'atteindre."""

import os
import socket

import httpx
import pytest

BASE_URL = os.environ.get("E2E_BASE_URL", "")


@pytest.fixture
def client() -> httpx.Client:
    return httpx.Client(base_url=BASE_URL, timeout=5.0)


class TestPaymentIsolation:
    @pytest.mark.parametrize("path", ["/health", "/health/ready"])
    def test_payment_is_not_routed_by_the_gateway(self, client: httpx.Client, path: str) -> None:
        response = client.get(f"/api/payment{path}")

        assert response.status_code == 404

    def test_payment_hostname_does_not_resolve_from_the_host(self) -> None:
        with pytest.raises(socket.gaierror):
            socket.getaddrinfo("payment", 8000)

    def test_payment_is_not_published_on_the_host(self) -> None:
        with pytest.raises(OSError), socket.create_connection(("127.0.0.1", 8000), timeout=2):
            pass
