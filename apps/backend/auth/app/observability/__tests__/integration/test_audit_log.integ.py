"""Journal d'audit reel : une ligne JSON par requete et par evenement, sans donnee sensible."""

from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from app.observability.__tests__.stack import (
    CORRELATION,
    OWNER_EMAIL,
    OWNER_PHRASE,
    SHOP_SECRET,
    VALIDATOR,
    ObservedService,
)

BAD_PHRASE = "mot-de-passe-errone-1234"


@pytest.fixture
def service(tmp_path: Path) -> ObservedService:
    return ObservedService(tmp_path)


def validate(validator: Draft202012Validator, lines: list[dict[str, object]]) -> None:
    for line in lines:
        validator.validate(line)


class TestRequestLines:
    async def test_every_request_writes_one_schema_valid_line_with_route_status_and_latency(
        self, service: ObservedService
    ) -> None:
        headers = {"X-Correlation-ID": CORRELATION}
        async with service.client() as client:
            await client.post(
                "/login", json={"email": "x@example.test", "password": "a"}, headers=headers
            )
            await client.get("/inconnue/987654", headers=headers)

        lines = service.lines()
        validate(VALIDATOR, lines)
        requests = [line for line in lines if line["event"] == "service.request_completed"]
        assert [
            (r["attributes"]["route"], r["attributes"]["method"], r["attributes"]["status"])
            for r in requests
        ] == [("/login", "POST", 401), ("unmatched", "GET", 404)]
        assert all(r["correlation_id"] == CORRELATION for r in lines)  # request_id commun
        assert all(isinstance(r["duration_ms"], int) and r["duration_ms"] >= 0 for r in requests)
        assert [(r["outcome"], r["reason"]) for r in requests] == [
            ("denied", "http_401"),
            ("denied", "http_404"),
        ]
        assert "987654" not in service.all_output()

    async def test_probes_that_succeed_are_not_logged_but_failures_are(
        self, service: ObservedService
    ) -> None:
        async with service.client() as client:
            await client.get("/health")
            await client.get("/metrics")
            await client.get("/metrics", headers={"X-Forwarded-For": "203.0.113.7"})

        requests = [e for e in service.lines() if e["event"] == "service.request_completed"]
        assert [r["attributes"]["status"] for r in requests] == [404]

    async def test_an_unhandled_error_is_one_error_line_without_trace(
        self, service: ObservedService
    ) -> None:
        async def boom() -> None:
            raise RuntimeError("secret-interne-42")

        service.application.add_api_route("/boom", boom)
        async with service.client() as client:
            with pytest.raises(RuntimeError):
                await client.get("/boom")

        output = service.all_output()
        assert "service.unhandled_error" in output
        assert "secret-interne-42" not in output
        request = [e for e in service.lines() if e["event"] == "service.request_completed"][-1]
        assert request["outcome"] == "error" and request["attributes"]["status"] == 500


class TestTypedEvents:
    async def test_the_security_events_are_written_with_their_stable_names(
        self, service: ObservedService
    ) -> None:
        async with service.client() as client:
            login = await client.post(
                "/login", json={"email": OWNER_EMAIL, "password": OWNER_PHRASE}
            )
            await client.post("/login", json={"email": OWNER_EMAIL, "password": BAD_PHRASE})
            for _ in range(5):
                await client.post("/login", json={"email": "inconnu@example.test", "password": "x"})
            old = login.headers["set-cookie"].split(";")[0].split("=", 1)[1]
            headers = {"X-Requested-With": "t", "Cookie": f"refresh_token={old}"}
            await client.post("/refresh", headers=headers)
            await client.post("/refresh", headers=headers)
            await client.post("/password/forgot", json={"email": OWNER_EMAIL})
            await client.post(
                "/internal/token",
                json={
                    "grant_type": "client_credentials",
                    "client_id": "shop",
                    "client_secret": SHOP_SECRET,
                    "audience": "payment",
                    "scope": "payments:write",
                },
            )
            await client.post(
                "/internal/token",
                json={
                    "grant_type": "client_credentials",
                    "client_id": "shop",
                    "client_secret": "mauvais",
                    "audience": "payment",
                    "scope": "payments:write",
                },
            )

        names = {line["event"] for line in service.lines()}
        assert {
            "auth.login_succeeded",
            "auth.login_failed",
            "auth.lockout_triggered",
            "auth.token_refreshed",
            "auth.refresh_reuse_detected",
            "auth.password_reset_requested",
            "auth.service_token_issued",
            "auth.service_token_denied",
            "service.request_completed",
        } <= names
        validate(VALIDATOR, service.lines())

    async def test_events_name_the_step_and_the_cause_but_never_the_account(
        self, service: ObservedService
    ) -> None:
        async with service.client() as client:
            await client.post("/login", json={"email": OWNER_EMAIL, "password": BAD_PHRASE})

        failed = next(e for e in service.lines() if e["event"] == "auth.login_failed")
        assert failed["attributes"]["step"] == "password"
        assert failed["attributes"]["cause"] == "wrong_password"
        assert set(failed["attributes"]) == {"email_hash", "cause", "step"}


class TestNoSensitiveDataAnywhere:
    async def test_neither_the_journal_nor_the_metrics_hold_an_address_a_password_or_a_token(
        self, service: ObservedService
    ) -> None:
        async with service.client() as client:
            login = await client.post(
                "/login", json={"email": OWNER_EMAIL, "password": OWNER_PHRASE}
            )
            access = login.json()["access_token"]
            refresh = login.headers["set-cookie"].split(";")[0].split("=", 1)[1]
            await client.post("/login", json={"email": OWNER_EMAIL, "password": BAD_PHRASE})
            await client.get("/me", headers={"Authorization": f"Bearer {access}"})
            await client.get("/me", headers={"Authorization": f"Bearer {access}x"})
            await client.post(
                "/refresh", headers={"X-Requested-With": "t", "Cookie": f"refresh_token={refresh}"}
            )
            await client.post("/password/forgot", json={"email": OWNER_EMAIL})
            await client.post(
                "/internal/token",
                json={
                    "grant_type": "client_credentials",
                    "client_id": "shop",
                    "client_secret": SHOP_SECRET,
                    "audience": "payment",
                    "scope": "payments:write",
                },
            )
            metrics = (await client.get("/metrics")).text

        output = service.all_output() + metrics
        local_part = OWNER_EMAIL.split("@")[0]
        for secret in (
            OWNER_EMAIL,
            local_part,
            OWNER_PHRASE,
            BAD_PHRASE,
            SHOP_SECRET,
            access,
            access.split(".")[1],
            refresh,
            "BEGIN PRIVATE KEY",
        ):
            assert secret not in output
