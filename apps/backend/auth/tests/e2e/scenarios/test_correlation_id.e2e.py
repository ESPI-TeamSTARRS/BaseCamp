"""Identifiant de correlation : repris ou genere par auth, renvoye a travers la passerelle."""

import os
import re

import httpx
import pytest

BASE_URL = os.environ.get("E2E_BASE_URL", "http://127.0.0.1:8080")
HEADER = "X-Correlation-ID"
VALID_ID = "7c1f0e52-3a0b-4f1e-9a52-1d6f7a9b2c10"
GENERATED = re.compile(r"^[A-Za-z0-9-]{8,64}$")


@pytest.fixture
def client() -> httpx.Client:
    return httpx.Client(base_url=BASE_URL, timeout=5.0, follow_redirects=True)


class TestCorrelationId:
    def test_a_valid_incoming_id_is_echoed_through_the_gateway(self, client: httpx.Client) -> None:
        response = client.get("/api/auth/health", headers={HEADER: VALID_ID})

        assert response.headers[HEADER] == VALID_ID

    def test_a_missing_or_invalid_id_is_replaced_by_a_generated_one(
        self, client: httpx.Client
    ) -> None:
        missing = client.get("/api/auth/health").headers[HEADER]
        invalid = client.get("/api/auth/health", headers={HEADER: "trop court"}).headers[HEADER]

        assert GENERATED.match(missing) and GENERATED.match(invalid)
        assert invalid != "trop court"
