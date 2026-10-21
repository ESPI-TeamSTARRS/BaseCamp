from collections.abc import AsyncIterator, Iterator
from datetime import timedelta
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from app.admin.__tests__.stack import OPERATOR_EMAIL, OTHER_OPERATOR_EMAIL, AdminStack
from app.core.__tests__.in_memory_business_event_logger import InMemoryBusinessEventLogger
from app.login.__tests__.stack import ACCOUNT_SECRET, EMAIL


@pytest.fixture
def events() -> InMemoryBusinessEventLogger:
    return InMemoryBusinessEventLogger()


@pytest.fixture
def stack(events: InMemoryBusinessEventLogger) -> Iterator[AdminStack]:
    stack = AdminStack(events)
    yield stack
    stack.engine.dispose()


@pytest.fixture
async def client(stack: AdminStack) -> AsyncIterator[AsyncClient]:
    async with AsyncClient(
        transport=ASGITransport(app=stack.application), base_url="http://test"
    ) as http:
        yield http


class TestAccessControl:
    @pytest.mark.parametrize(
        ("method", "path"),
        [
            ("GET", "/admin/users"),
            ("POST", f"/admin/users/{uuid4()}/disable"),
            ("POST", f"/admin/users/{uuid4()}/enable"),
        ],
    )
    async def test_without_a_token_the_answer_is_the_generic_401(
        self, client: AsyncClient, method: str, path: str
    ) -> None:
        response = await client.request(method, path)

        assert response.status_code == 401
        assert response.json() == {"detail": "Authentification requise."}
        assert response.headers["www-authenticate"] == "Bearer"

    @pytest.mark.parametrize(
        ("method", "path"),
        [
            ("GET", "/admin/users"),
            ("POST", f"/admin/users/{uuid4()}/disable"),
            ("POST", f"/admin/users/{uuid4()}/enable"),
        ],
    )
    async def test_a_customer_token_is_refused_with_403(
        self, client: AsyncClient, stack: AdminStack, method: str, path: str
    ) -> None:
        headers = await stack.token_of(client, EMAIL)

        response = await client.request(method, path, headers=headers)

        assert response.status_code == 403
        assert response.json() == {"detail": "Accès refusé."}

    async def test_a_forged_or_expired_token_is_the_generic_401(
        self, client: AsyncClient, stack: AdminStack
    ) -> None:
        headers = await stack.token_of(client, OPERATOR_EMAIL)
        assert (await client.get("/admin/users", headers=headers)).status_code == 200

        forged = {"Authorization": "Bearer " + headers["Authorization"][7:-4] + "AAAA"}
        stack.clock.current += timedelta(minutes=16)

        assert (await client.get("/admin/users", headers=forged)).status_code == 401
        assert (await client.get("/admin/users", headers=headers)).status_code == 401

    async def test_the_role_is_never_read_from_a_client_parameter(
        self, client: AsyncClient, stack: AdminStack
    ) -> None:
        headers = await stack.token_of(client, EMAIL)

        response = await client.get(
            "/admin/users?role=operator", headers={**headers, "X-Role": "operator"}
        )

        assert response.status_code == 403

    async def test_a_disabled_operator_loses_access_at_once(
        self, client: AsyncClient, stack: AdminStack
    ) -> None:
        stack.add_account(OTHER_OPERATOR_EMAIL, role="operator")
        headers = await stack.token_of(client, OTHER_OPERATOR_EMAIL)
        with stack.engine.begin() as connection:
            connection.execute(
                text("UPDATE users SET disabled_at = '2026-01-01 12:00:00' WHERE email = :e"),
                {"e": OTHER_OPERATOR_EMAIL},
            )

        assert (await client.get("/admin/users", headers=headers)).status_code == 401

    async def test_a_demoted_operator_loses_access_at_once(
        self, client: AsyncClient, stack: AdminStack
    ) -> None:
        headers = await stack.token_of(client, OPERATOR_EMAIL)
        with stack.engine.begin() as connection:
            connection.execute(
                text("UPDATE users SET role = 'customer' WHERE email = :e"), {"e": OPERATOR_EMAIL}
            )

        assert (await client.get("/admin/users", headers=headers)).status_code == 403


class TestList:
    async def test_lists_accounts_without_any_secret(
        self, client: AsyncClient, stack: AdminStack
    ) -> None:
        headers = await stack.token_of(client, OPERATOR_EMAIL)

        response = await client.get("/admin/users", headers=headers)

        assert response.status_code == 200
        body = response.json()
        assert (body["total"], body["limit"], body["offset"]) == (2, 50, 0)
        assert {item["email"] for item in body["items"]} == {OPERATOR_EMAIL, EMAIL}
        assert set(body["items"][0]) == {
            "id",
            "email",
            "role",
            "email_verified",
            "disabled",
            "created_at",
        }
        assert "hash" not in response.text and "argon2" not in response.text
        assert response.headers["cache-control"] == "no-store"

    async def test_is_paginated(self, client: AsyncClient, stack: AdminStack) -> None:
        for index in range(5):
            stack.add_account(f"client{index}@example.com")
        headers = await stack.token_of(client, OPERATOR_EMAIL)

        first = (await client.get("/admin/users?limit=3&offset=0", headers=headers)).json()
        second = (await client.get("/admin/users?limit=3&offset=3", headers=headers)).json()
        last = (await client.get("/admin/users?limit=3&offset=6", headers=headers)).json()

        assert first["total"] == 7
        assert (len(first["items"]), len(second["items"]), len(last["items"])) == (3, 3, 1)
        ids = [item["id"] for page in (first, second, last) for item in page["items"]]
        assert len(set(ids)) == 7

    @pytest.mark.parametrize("query", ["limit=0", "limit=101", "offset=-1", "limit=abc"])
    async def test_invalid_pagination_is_a_422(
        self, client: AsyncClient, stack: AdminStack, query: str
    ) -> None:
        headers = await stack.token_of(client, OPERATOR_EMAIL)

        assert (await client.get(f"/admin/users?{query}", headers=headers)).status_code == 422

    async def test_the_listing_is_audited(
        self, client: AsyncClient, stack: AdminStack, events: InMemoryBusinessEventLogger
    ) -> None:
        headers = await stack.token_of(client, OPERATOR_EMAIL)
        events.events.clear()

        await client.get(
            "/admin/users?limit=10", headers={**headers, "X-Forwarded-For": "203.0.113.7"}
        )

        [event] = events.events
        assert (event.event, event.actor_type, event.actor_id) == (
            "auth.accounts_listed",
            "operator",
            str(stack.operator_id),
        )
        assert dict(event.attributes) == {"limit": 10, "offset": 0, "returned": 2}
        assert event.client_ip == "203.0.113.7"
        assert EMAIL not in repr(event)


class TestDisable:
    async def test_a_disabled_account_cannot_log_in_and_loses_its_sessions(
        self, client: AsyncClient, stack: AdminStack
    ) -> None:
        await client.post("/login", json={"email": EMAIL, "password": ACCOUNT_SECRET})
        await client.post("/login", json={"email": EMAIL, "password": ACCOUNT_SECRET})
        assert stack.scalar("SELECT COUNT(*) FROM refresh_tokens") == 2
        headers = await stack.token_of(client, OPERATOR_EMAIL)

        response = await client.post(f"/admin/users/{stack.customer_id}/disable", headers=headers)

        assert response.status_code == 200
        assert response.json()["disabled"] is True
        # il ne reste que la session de l'operateur
        assert stack.scalar("SELECT COUNT(*) FROM refresh_tokens") == 1
        login = await client.post("/login", json={"email": EMAIL, "password": ACCOUNT_SECRET})
        assert (login.status_code, login.json()) == (401, {"detail": "Identifiants invalides."})

    async def test_enabling_restores_the_login(
        self, client: AsyncClient, stack: AdminStack
    ) -> None:
        headers = await stack.token_of(client, OPERATOR_EMAIL)
        await client.post(f"/admin/users/{stack.customer_id}/disable", headers=headers)

        response = await client.post(f"/admin/users/{stack.customer_id}/enable", headers=headers)

        assert response.json()["disabled"] is False
        login = await client.post("/login", json={"email": EMAIL, "password": ACCOUNT_SECRET})
        assert login.status_code == 200

    async def test_both_actions_are_idempotent(
        self, client: AsyncClient, stack: AdminStack
    ) -> None:
        headers = await stack.token_of(client, OPERATOR_EMAIL)
        url = f"/admin/users/{stack.customer_id}"

        first = await client.post(f"{url}/disable", headers=headers)
        second = await client.post(f"{url}/disable", headers=headers)
        enabled = await client.post(f"{url}/enable", headers=headers)
        again = await client.post(f"{url}/enable", headers=headers)

        assert [r.status_code for r in (first, second, enabled, again)] == [200, 200, 200, 200]

    async def test_an_operator_cannot_disable_themselves(
        self, client: AsyncClient, stack: AdminStack
    ) -> None:
        stack.add_account(OTHER_OPERATOR_EMAIL, role="operator")
        headers = await stack.token_of(client, OPERATOR_EMAIL)

        response = await client.post(f"/admin/users/{stack.operator_id}/disable", headers=headers)

        assert response.status_code == 409
        assert response.json()["code"] == "cannot_disable_self"
        assert stack.scalar("SELECT COUNT(*) FROM users WHERE disabled_at IS NOT NULL") == 0

    async def test_two_operators_cannot_lock_each_other_out(
        self, client: AsyncClient, stack: AdminStack
    ) -> None:
        second = stack.add_account(OTHER_OPERATOR_EMAIL, role="operator")
        first_headers = await stack.token_of(client, OPERATOR_EMAIL)
        second_headers = await stack.token_of(client, OTHER_OPERATOR_EMAIL)

        disabled = await client.post(f"/admin/users/{second}/disable", headers=first_headers)
        back = await client.post(
            f"/admin/users/{stack.operator_id}/disable", headers=second_headers
        )

        assert disabled.status_code == 200
        assert back.status_code == 401  # le compte desactive ne peut plus agir
        active = "SELECT COUNT(*) FROM users WHERE role = 'operator' AND disabled_at IS NULL"
        assert stack.scalar(active) == 1

    async def test_an_unknown_account_is_a_404(
        self, client: AsyncClient, stack: AdminStack
    ) -> None:
        headers = await stack.token_of(client, OPERATOR_EMAIL)

        for action in ("disable", "enable"):
            response = await client.post(f"/admin/users/{uuid4()}/{action}", headers=headers)
            assert response.status_code == 404
            assert response.json()["code"] == "account_not_found"

    async def test_a_malformed_identifier_is_a_422(
        self, client: AsyncClient, stack: AdminStack
    ) -> None:
        headers = await stack.token_of(client, OPERATOR_EMAIL)

        response = await client.post("/admin/users/pas-un-uuid/disable", headers=headers)

        assert response.status_code == 422

    async def test_each_action_writes_an_audit_line(
        self, client: AsyncClient, stack: AdminStack, events: InMemoryBusinessEventLogger
    ) -> None:
        headers = await stack.token_of(client, OPERATOR_EMAIL)
        events.events.clear()

        await client.post(f"/admin/users/{stack.customer_id}/disable", headers=headers)
        await client.post(f"/admin/users/{stack.operator_id}/disable", headers=headers)
        await client.post(f"/admin/users/{stack.customer_id}/enable", headers=headers)

        disabled, refused, enabled = events.events
        assert (disabled.event, disabled.resource_id, disabled.actor_id) == (
            "auth.account_disabled",
            str(stack.customer_id),
            str(stack.operator_id),
        )
        assert (refused.event, refused.reason) == (
            "auth.admin_action_refused",
            "cannot_disable_self",
        )
        assert (enabled.event, enabled.resource_id) == (
            "auth.account_enabled",
            str(stack.customer_id),
        )
        assert all(e.actor_type == "operator" for e in (disabled, refused, enabled))
        assert EMAIL not in repr(events.events)
