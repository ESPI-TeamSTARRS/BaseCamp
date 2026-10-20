"""Parcours de l'isolation du service auth, via la passerelle Traefik."""

import os

import httpx
import pytest

BASE_URL = os.environ.get("E2E_BASE_URL", "http://127.0.0.1:8080")


@pytest.fixture
def client() -> httpx.Client:
    return httpx.Client(base_url=BASE_URL, timeout=5.0, follow_redirects=True)


class TestAuthStack:
    def test_liveness_is_reachable_through_the_gateway(self, client: httpx.Client) -> None:
        response = client.get("/api/auth/health")

        assert response.status_code == 200
        assert response.json() == {"service": "basecamp-auth", "status": "up"}

    def test_readiness_confirms_the_dedicated_database_is_reachable(
        self, client: httpx.Client
    ) -> None:
        response = client.get("/api/auth/health/ready")

        assert response.status_code == 200
        assert response.json()["status"] == "up"

    @pytest.mark.parametrize(
        "path",
        [
            "/api/auth/internal/jwks",
            "/api/auth/internal/",
            "/api/auth/internal",
            "/api/auth/%69nternal/jwks",
            "/api/auth/./internal/jwks",
            "/api/auth//internal/jwks",
            "/internal/jwks",
        ],
    )
    def test_internal_routes_are_not_reachable_from_outside(
        self, client: httpx.Client, path: str
    ) -> None:
        response = client.get(path)

        assert response.status_code in (403, 404)
        assert "basecamp-auth" not in response.text
