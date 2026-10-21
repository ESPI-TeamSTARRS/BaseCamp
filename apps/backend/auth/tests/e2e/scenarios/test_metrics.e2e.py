"""Signaux de detection sur la pile reelle : `/metrics` n'existe que sur le reseau interne.

La collecte se lit depuis l'interieur du conteneur `auth` (`docker compose exec`, E2E_CHECK_LOGS=1);
la passerelle, elle, ne doit jamais la servir.
"""

import json
import os
import shutil
import subprocess
import uuid
from pathlib import Path

import httpx
import pytest

REPO_ROOT = Path(__file__).resolve().parents[6]  # docker compose se lance depuis la racine
BASE_URL = os.environ.get("E2E_BASE_URL", "http://127.0.0.1:8080")
needs_docker = pytest.mark.skipif(
    not (os.environ.get("E2E_CHECK_LOGS") and shutil.which("docker")),
    reason="definir E2E_CHECK_LOGS=1 (docker compose requis)",
)
SCRAPE = (
    "import json,sys,urllib.request,urllib.error;"
    "req=urllib.request.Request('http://127.0.0.1:8000/metrics',"
    "headers=dict(zip(sys.argv[1::2],sys.argv[2::2])));"
    "\ntry:\n r=urllib.request.urlopen(req);print(json.dumps({'status':r.status,'body':r.read().decode()}))"
    "\nexcept urllib.error.HTTPError as e:\n print(json.dumps({'status':e.code,'body':''}))"
)


def scrape(*headers: str) -> dict[str, object]:
    command = ["docker", "compose", "exec", "-T", "auth", "python", "-c", SCRAPE, *headers]
    completed = subprocess.run(  # noqa: S603
        command,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=180,
        check=True,
        cwd=REPO_ROOT,
    )
    return json.loads(completed.stdout.strip().splitlines()[-1])  # type: ignore[no-any-return]


@pytest.fixture
def client() -> httpx.Client:
    return httpx.Client(base_url=BASE_URL, timeout=30.0)


class TestGatewayNeverServesMetrics:
    @pytest.mark.parametrize("path", ["/api/auth/metrics", "/metrics", "/api/auth/metrics/"])
    def test_the_gateway_does_not_return_the_collection(
        self, client: httpx.Client, path: str
    ) -> None:
        response = client.get(path)

        assert "auth_http_requests_total" not in response.text
        assert "# TYPE" not in response.text
        assert response.status_code in (404, 308)


@needs_docker
class TestInternalCollection:
    def test_the_service_serves_its_families_on_the_internal_network(
        self, client: httpx.Client
    ) -> None:
        email = f"e2e-metrics-{uuid.uuid4().hex[:10]}@example.test"
        client.post("/api/auth/login", json={"email": email, "password": "inconnu-12345"})

        result = scrape()

        body = str(result["body"])
        assert result["status"] == 200
        for family in (
            "auth_http_requests_total",
            "auth_http_request_duration_seconds",
            "auth_login_failures_total",
            "auth_active_lockouts",
            "auth_service_token_denied_total",
            "auth_refresh_reuse_detected_total",
            "auth_state_up 1",
        ):
            assert family in body
        assert 'auth_login_failures_total{cause="unknown_account"}' in body
        assert email not in body

    def test_a_request_carrying_a_proxy_header_is_refused(self) -> None:
        for header in ("X-Forwarded-For", "X-Real-Ip", "X-Forwarded-Host"):
            assert scrape(header, "203.0.113.7")["status"] == 404
