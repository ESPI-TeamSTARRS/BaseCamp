import re
from pathlib import Path

import pytest

from app.core.events.business_event import BusinessEvent
from app.observability.__tests__.stack import (
    OWNER_EMAIL,
    OWNER_PHRASE,
    SHOP_SECRET,
    ObservedService,
    metric,
)

LABEL = re.compile(r'([a-z_]+)="')
CLOSED_LABELS = {
    "route",
    "method",
    "status",
    "le",
    "event",
    "outcome",
    "reason",
    "cause",
    "step",
    "client",
    "result",
}


@pytest.fixture
def service(tmp_path: Path) -> ObservedService:
    return ObservedService(tmp_path)


def token_body(client_id: str, secret: str) -> dict[str, str]:
    return {
        "grant_type": "client_credentials",
        "client_id": client_id,
        "client_secret": secret,
        "audience": "payment",
        "scope": "payments:write",
    }


async def scrape(service: ObservedService) -> str:
    async with service.client() as client:
        response = await client.get("/metrics")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain; version=0.0.4")
    return str(response.text)


class TestEndpoint:
    async def test_it_serves_the_prometheus_text_format_with_every_family(
        self, service: ObservedService
    ) -> None:
        body = await scrape(service)

        for family in (
            "auth_http_requests_total",
            "auth_http_request_duration_seconds",
            "auth_events_total",
            "auth_login_failures_total",
            "auth_lockouts_triggered_total",
            "auth_refresh_reuse_detected_total",
            "auth_service_token_denied_total",
            "auth_service_token_rate_limited_total",
            "auth_active_lockouts",
            "auth_state_up",
        ):
            assert f"# TYPE {family} " in body
        assert metric(body, "auth_state_up") == 1

    async def test_it_is_refused_behind_a_proxy_and_logged(self, service: ObservedService) -> None:
        async with service.client() as client:
            responses = [
                await client.get("/metrics", headers={header: "203.0.113.7"})
                for header in ("X-Forwarded-For", "X-Real-Ip", "Forwarded")
            ]

        assert {r.status_code for r in responses} == {404}
        refused = [e for e in service.lines() if e["event"] == "service.metrics_refused"]
        assert len(refused) == 3
        assert {e["reason"] for e in refused} == {"proxied_request"}

    async def test_the_route_is_not_in_the_openapi_document(self, service: ObservedService) -> None:
        async with service.client() as client:
            document = (await client.get("/openapi.json")).json()

        assert "/metrics" not in document["paths"]


class TestSignals:
    async def test_requests_are_counted_by_route_template_method_and_status(
        self, service: ObservedService
    ) -> None:
        async with service.client() as client:
            await client.get("/health")
            await client.post("/login", json={"email": "x@example.test", "password": "a"})
            await client.get("/inconnue/123456")
        body = await scrape(service)

        health = 'auth_http_requests_total{route="/health",method="GET",status="200"}'
        login = 'auth_http_requests_total{route="/login",method="POST",status="401"}'
        unmatched = 'auth_http_requests_total{route="unmatched",method="GET",status="404"}'
        assert (metric(body, health), metric(body, login), metric(body, unmatched)) == (1, 1, 1)
        assert "123456" not in body
        count = 'auth_http_request_duration_seconds_count{route="/login",method="POST"}'
        assert metric(body, count) == 1

    async def test_login_failures_lockouts_and_active_locks_follow_the_events(
        self, service: ObservedService
    ) -> None:
        async with service.client() as client:
            for _ in range(6):
                await client.post(
                    "/login", json={"email": "inconnu@example.test", "password": "mauvais"}
                )
        body = await scrape(service)

        assert metric(body, 'auth_login_failures_total{cause="unknown_account"}') == 5
        assert metric(body, 'auth_login_failures_total{cause="account_locked"}') == 1
        assert metric(body, 'auth_lockouts_triggered_total{step="password"}') == 1
        assert metric(body, 'auth_active_lockouts{step="password"}') == 1

    async def test_a_replayed_refresh_token_is_counted(self, service: ObservedService) -> None:
        async with service.client() as client:
            login = await client.post(
                "/login", json={"email": OWNER_EMAIL, "password": OWNER_PHRASE}
            )
            old = login.headers["set-cookie"].split(";")[0].split("=", 1)[1]
            headers = {"X-Requested-With": "test", "Cookie": f"refresh_token={old}"}
            await client.post("/refresh", headers=headers)
            await client.post("/refresh", headers=headers)
        body = await scrape(service)

        succeeded = 'auth_events_total{event="auth.login_succeeded",outcome="success",reason=""}'
        assert metric(body, "auth_refresh_reuse_detected_total") == 1
        assert metric(body, succeeded) == 1

    async def test_service_token_denials_are_counted_per_known_client(
        self, service: ObservedService
    ) -> None:
        async with service.client() as client:
            await client.post("/internal/token", json=token_body("shop", "mauvais"))
            await client.post("/internal/token", json=token_body("shop", "encore-mauvais"))
            await client.post("/internal/token", json=token_body("intrus-1", "x"))
            await client.post("/internal/token", json=token_body("intrus-2", "x"))
            ok = await client.post("/internal/token", json=token_body("shop", SHOP_SECRET))
        body = await scrape(service)

        issued = 'auth_events_total{event="auth.service_token_issued",outcome="success",reason=""}'
        assert ok.status_code == 200
        assert metric(body, 'auth_service_token_denied_total{client="shop"}') == 2
        assert metric(body, 'auth_service_token_denied_total{client="unknown"}') == 2
        assert "intrus" not in body
        assert metric(body, issued) == 1

    async def test_the_active_lock_gauge_is_read_from_the_database_each_time(
        self, service: ObservedService
    ) -> None:
        async with service.client() as client:
            for _ in range(5):
                await client.post("/login", json={"email": "a@example.test", "password": "x"})
            first = await scrape(service)
            with service.engine.begin() as connection:
                connection.exec_driver_sql(
                    "UPDATE login_lockouts SET locked_until = '2000-01-01 00:00:00'"
                )
            second = await scrape(service)

        assert metric(first, 'auth_active_lockouts{step="password"}') == 1
        assert 'auth_active_lockouts{step="password"}' not in second

    async def test_an_unreadable_database_shows_state_up_zero_and_no_state_series(
        self, service: ObservedService
    ) -> None:
        with service.engine.begin() as connection:
            connection.exec_driver_sql("DROP TABLE login_lockouts")

        body = await scrape(service)

        assert metric(body, "auth_state_up") == 0
        assert "auth_active_lockouts{" not in body
        assert "# TYPE auth_http_requests_total counter" in body


class TestBackofficeSignals:
    """Connexion du back-office : tentatives par etape et resultat, blocages; jamais d'email en etiquette."""

    EMAIL_HASH = "0123456789abcdef"

    @staticmethod
    def _emit(service: ObservedService, *events: BusinessEvent) -> None:
        for event in events:
            service.application.state.events.log(event)

    def _attrs(self, **extra: str) -> dict[str, str]:
        return {"email_hash": self.EMAIL_HASH, **extra}

    async def test_attempts_are_counted_per_step_and_result(self, service: ObservedService) -> None:
        self._emit(
            service,
            BusinessEvent.success("auth.backoffice_identify", attributes=self._attrs()),
            BusinessEvent.success("auth.backoffice_identify", attributes=self._attrs()),
            BusinessEvent.success("auth.backoffice_face_result", attributes=self._attrs()),
            BusinessEvent.denied(
                "auth.backoffice_face_result", "face_refused", attributes=self._attrs()
            ),
            BusinessEvent.success("auth.backoffice_password_result", attributes=self._attrs()),
            BusinessEvent.denied(
                "auth.backoffice_password_result", "wrong_password", attributes=self._attrs()
            ),
            BusinessEvent.denied(
                "auth.backoffice_password_result", "wrong_password", attributes=self._attrs()
            ),
            BusinessEvent.error(
                "auth.backoffice_face_result", "recognition_unavailable", attributes=self._attrs()
            ),
        )

        body = await scrape(service)

        def series(step: str, result: str) -> float:
            return metric(
                body, f'auth_backoffice_attempts_total{{step="{step}",result="{result}"}}'
            )

        assert series("identify", "success") == 2
        assert (series("face", "success"), series("face", "denied"), series("face", "error")) == (
            1,
            1,
            1,
        )
        assert (series("password", "success"), series("password", "denied")) == (1, 2)

    async def test_lockouts_are_counted_per_step(self, service: ObservedService) -> None:
        self._emit(
            service,
            BusinessEvent.denied(
                "auth.backoffice_lockout",
                "too_many_failures",
                attributes=self._attrs(step="face"),
            ),
            BusinessEvent.denied(
                "auth.backoffice_lockout",
                "too_many_failures",
                attributes=self._attrs(step="operator_password"),
            ),
            BusinessEvent.denied(
                "auth.backoffice_lockout",
                "too_many_failures",
                attributes=self._attrs(step="face"),
            ),
        )

        body = await scrape(service)

        assert metric(body, 'auth_backoffice_lockouts_total{step="face"}') == 2
        assert metric(body, 'auth_backoffice_lockouts_total{step="operator_password"}') == 1

    async def test_no_series_carries_an_email_or_its_hash(self, service: ObservedService) -> None:
        self._emit(
            service,
            BusinessEvent.denied(
                "auth.backoffice_face_result", "face_refused", attributes=self._attrs()
            ),
            BusinessEvent.denied(
                "auth.backoffice_lockout",
                "too_many_failures",
                attributes=self._attrs(step="face"),
            ),
        )

        body = await scrape(service)

        assert self.EMAIL_HASH not in body and "@" not in body
        assert "# TYPE auth_backoffice_attempts_total counter" in body
        assert "# TYPE auth_backoffice_lockouts_total counter" in body


class TestLabelsAreClosed:
    async def test_every_label_name_belongs_to_the_closed_list(
        self, service: ObservedService
    ) -> None:
        async with service.client() as client:
            await client.post("/login", json={"email": OWNER_EMAIL, "password": "mauvais"})
            await client.post("/internal/token", json=token_body("shop", "mauvais"))
            await client.get("/health")
        body = await scrape(service)

        used = {
            name
            for line in body.splitlines()
            if not line.startswith("#")
            for name in LABEL.findall(line)
        }
        assert used <= CLOSED_LABELS
