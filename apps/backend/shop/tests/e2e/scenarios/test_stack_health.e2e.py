"""Parcours de sante de la pile complete, via la passerelle Traefik."""

import os

import httpx
import pytest

BASE_URL = os.environ.get("E2E_BASE_URL", "http://127.0.0.1:8080")


@pytest.fixture
def client() -> httpx.Client:
    return httpx.Client(base_url=BASE_URL, timeout=5.0)


class TestStackHealth:
    def test_shop_liveness_is_reachable_through_the_gateway(self, client: httpx.Client) -> None:
        response = client.get("/api/shop/health")

        assert response.status_code == 200
        assert response.json()["status"] == "up"

    def test_shop_readiness_confirms_the_database_is_reachable(self, client: httpx.Client) -> None:
        response = client.get("/api/shop/health/ready")

        assert response.status_code == 200
        assert response.json()["status"] == "up"

    def test_frontend_home_page_is_served(self, client: httpx.Client) -> None:
        response = client.get("/")

        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
