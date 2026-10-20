"""Identifiant de correlation : repris ou genere par le service, renvoye a travers la passerelle."""

import os
import re

import httpx
import pytest

BASE_URL = os.environ.get("E2E_BASE_URL", "")
HEADER = "X-Correlation-ID"
VALID_ID = "7c1f0e52-3a0b-4f1e-9a52-1d6f7a9b2c10"
GENERATED = re.compile(r"^[A-Za-z0-9-]{8,64}$")


@pytest.fixture
def client() -> httpx.Client:
    return httpx.Client(base_url=BASE_URL, timeout=5.0)


class TestCorrelationId:
    def test_a_valid_incoming_id_is_echoed_through_the_gateway(self, client: httpx.Client) -> None:
        response = client.get("/api/shop/health", headers={HEADER: VALID_ID})

        assert response.headers[HEADER] == VALID_ID

    def test_a_missing_id_is_generated(self, client: httpx.Client) -> None:
        response = client.get("/api/shop/health")

        assert GENERATED.match(response.headers[HEADER])

    def test_an_invalid_incoming_id_is_replaced(self, client: httpx.Client) -> None:
        response = client.get("/api/shop/health", headers={HEADER: "trop court"})

        assert response.headers[HEADER] != "trop court"
        assert GENERATED.match(response.headers[HEADER])
