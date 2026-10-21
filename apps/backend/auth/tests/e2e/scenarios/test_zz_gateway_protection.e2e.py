"""Protections de la passerelle contre la force brute sur les routes d'auth.

Le nom place ce fichier en dernier : il epuise les compteurs par IP de la passerelle (`login` et
`register` partagent un seuil, `password/forgot` a le sien), ce qui ferait echouer les scenarios
suivants s'ils partageaient ces compteurs.
"""

import os
import statistics
import time
import uuid
from concurrent.futures import ThreadPoolExecutor

import httpx
import pytest

BASE_URL = os.environ.get("E2E_BASE_URL", "http://127.0.0.1:8080")
MAX_ATTEMPTS = 200
MAX_BODY_BYTES = 1_048_576
ATTACKERS = 200
HEALTH_PROBES = 60
P95_LIMIT_SECONDS = 0.2


@pytest.fixture
def client() -> httpx.Client:
    return httpx.Client(base_url=BASE_URL, timeout=10.0)


def first_limited(client: httpx.Client, path: str, body: dict[str, str]) -> httpx.Response | None:
    """Premiere reponse 429, avec un `X-Forwarded-For` different a chaque essai (forge)."""
    for attempt in range(MAX_ATTEMPTS):
        response = client.post(
            path, json=body, headers={"X-Forwarded-For": f"203.0.113.{attempt % 250 + 1}"}
        )
        if response.status_code == 429:
            return response
    return None


class TestRateLimit:
    def test_register_is_limited_per_real_ip_with_retry_after_despite_forged_headers(
        self, client: httpx.Client
    ) -> None:
        body = {"email": f"e2e-limit-{uuid.uuid4().hex[:8]}@example.test", "password": "x" * 12}

        limited = first_limited(client, "/api/auth/register", body)

        assert limited is not None, "un X-Forwarded-For forge contourne la limite"
        assert int(limited.headers["Retry-After"]) >= 1

    def test_login_shares_the_limit_and_answers_429_with_retry_after(
        self, client: httpx.Client
    ) -> None:
        limited = first_limited(
            client, "/api/auth/login", {"email": "inconnu@example.test", "password": "mauvais"}
        )

        assert limited is not None
        assert int(limited.headers["Retry-After"]) >= 1

    def test_password_forgot_has_its_own_limit(self, client: httpx.Client) -> None:
        limited = first_limited(
            client, "/api/auth/password/forgot", {"email": "inconnu@example.test"}
        )

        assert limited is not None
        assert int(limited.headers["Retry-After"]) >= 1


class TestRequestShape:
    @pytest.mark.parametrize("path", ["/api/auth/login", "/api/auth/password/forgot"])
    def test_an_oversized_body_is_rejected_with_413(self, client: httpx.Client, path: str) -> None:
        response = client.post(path, content=b"x" * (MAX_BODY_BYTES + 1))

        assert response.status_code in (413, 429)  # 429 si le compteur par IP est deja epuise


class TestUnderAttack:
    def test_health_stays_up_and_fast_during_200_parallel_attempts(
        self, client: httpx.Client
    ) -> None:
        def attack(index: int) -> int:
            with httpx.Client(base_url=BASE_URL, timeout=30.0) as http:
                return int(
                    http.post(
                        "/api/auth/login",
                        json={"email": f"nobody-{index}@example.test", "password": "mauvais"},
                    ).status_code
                )

        def probe(_: int) -> tuple[int, float]:
            started = time.perf_counter()
            status = client.get("/api/auth/health").status_code
            return int(status), time.perf_counter() - started

        with ThreadPoolExecutor(ATTACKERS + HEALTH_PROBES) as pool:
            attackers = [pool.submit(attack, index) for index in range(ATTACKERS)]
            probes = [pool.submit(probe, index) for index in range(HEALTH_PROBES)]
            attack_statuses = [future.result() for future in attackers]
            health = [future.result() for future in probes]

        assert set(attack_statuses) <= {401, 429}
        assert {status for status, _ in health} == {200}
        durations = sorted(duration for _, duration in health)
        p95 = durations[int(len(durations) * 0.95) - 1]
        assert p95 < P95_LIMIT_SECONDS, (
            f"p95 = {p95:.3f}s (mediane {statistics.median(durations):.3f}s)"
        )
