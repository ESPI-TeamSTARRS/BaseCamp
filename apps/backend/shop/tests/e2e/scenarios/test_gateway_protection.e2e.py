"""Protections portees par la passerelle Traefik (limitation de debit, taille de corps, en-tetes)."""

import os

import httpx
import pytest

BASE_URL = os.environ.get("E2E_BASE_URL", "")
ORDERS_PATH = "/api/shop/orders"
MAX_ATTEMPTS = 40
MAX_BODY_BYTES = 1_048_576


@pytest.fixture
def client() -> httpx.Client:
    return httpx.Client(base_url=BASE_URL, timeout=5.0)


def _first_limited_response(client: httpx.Client, forged_ips: bool) -> httpx.Response | None:
    for attempt in range(MAX_ATTEMPTS):
        headers = {"X-Forwarded-For": f"203.0.113.{attempt + 1}"} if forged_ips else {}
        response = client.get(ORDERS_PATH, headers=headers)
        if response.status_code == 429:
            return response
    return None


class TestRateLimit:
    def test_orders_are_rate_limited_per_real_ip_with_retry_after(
        self, client: httpx.Client
    ) -> None:
        limited = _first_limited_response(client, forged_ips=False)

        assert limited is not None, "aucun 429 apres trop de requetes"
        assert int(limited.headers["Retry-After"]) >= 1

    def test_forged_x_forwarded_for_does_not_bypass_the_limit(self, client: httpx.Client) -> None:
        limited = _first_limited_response(client, forged_ips=True)

        assert limited is not None, "un X-Forwarded-For forge contourne la limite"

    def test_other_routes_are_not_rate_limited(self, client: httpx.Client) -> None:
        statuses = {client.get("/api/shop/health").status_code for _ in range(30)}

        assert statuses == {200}


class TestBodySize:
    def test_oversized_body_is_rejected_with_413(self, client: httpx.Client) -> None:
        response = client.post("/api/shop/health", content=b"x" * (MAX_BODY_BYTES + 1))

        assert response.status_code == 413


class TestSecurityHeaders:
    @pytest.mark.parametrize("path", ["/api/shop/health", "/"])
    def test_gateway_sets_security_headers(self, client: httpx.Client, path: str) -> None:
        headers = client.get(path).headers

        assert "max-age=" in headers["Strict-Transport-Security"]
        assert headers["X-Content-Type-Options"] == "nosniff"
        assert headers["X-Frame-Options"].upper() == "DENY"
