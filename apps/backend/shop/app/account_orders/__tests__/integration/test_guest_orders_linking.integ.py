from collections.abc import Iterator

import httpx
import pytest
from sqlalchemy import text

from app.account_orders.__tests__.stack import EMAIL, OTHER_EMAIL, Shop
from app.account_orders.infrastructure.clients.http_account_profile_directory import (
    HttpAccountProfileDirectory,
)


@pytest.fixture
def shop() -> Iterator[Shop]:
    shop = Shop()
    yield shop
    shop.engine.dispose()


def owners(shop: Shop) -> dict[str, str | None]:
    with shop.engine.connect() as connection:
        return {
            row.number: row.user_id
            for row in connection.execute(text("SELECT number, user_id FROM orders"))
        }


class TestRetroactiveLinking:
    async def test_guest_orders_with_the_same_verified_email_are_linked_on_first_listing(
        self, shop: Shop
    ) -> None:
        async with shop.client() as client:
            first = (await shop.order(client)).json()
            second = (await shop.order(client, email=EMAIL.upper())).json()  # casse differente
            elsewhere = (await shop.order(client, email=OTHER_EMAIL)).json()
            user, headers = shop.account()

            listing = (await client.get("/me/orders", headers=headers)).json()

        assert {item["number"] for item in listing["items"]} == {first["number"], second["number"]}
        assert owners(shop) == {
            first["number"]: str(user),
            second["number"]: str(user),
            elsewhere["number"]: None,
        }
        linked = [e for e in shop.lines() if e["event"] == "order.guest_orders_linked"]
        assert [e["attributes"]["count"] for e in linked] == [2]

    async def test_an_unverified_email_links_nothing(self, shop: Shop) -> None:
        async with shop.client() as client:
            guest = (await shop.order(client)).json()
            _, headers = shop.account(verified=False)

            listing = (await client.get("/me/orders", headers=headers)).json()

        assert listing["items"] == []
        assert owners(shop)[guest["number"]] is None
        assert any(
            e["event"] == "order.guest_link_skipped" and e["reason"] == "email_not_verified"
            for e in shop.lines()
        )

    async def test_a_token_claiming_a_verified_email_that_auth_denies_links_nothing(
        self, shop: Shop
    ) -> None:
        async with shop.client() as client:
            guest = (await shop.order(client)).json()
            _, headers = shop.account(verified=False, claim_verified=True)

            await client.get("/me/orders", headers=headers)

        assert owners(shop)[guest["number"]] is None

    async def test_linking_is_idempotent_and_never_steals_an_order_already_linked(
        self, shop: Shop
    ) -> None:
        async with shop.client() as client:
            guest = (await shop.order(client)).json()
            first_user, first = shop.account()
            second_user, second = shop.account()  # un autre compte, meme adresse verifiee

            await client.get("/me/orders", headers=first)
            await client.get("/me/orders", headers=first)
            second_listing = (await client.get("/me/orders", headers=second)).json()

        assert owners(shop)[guest["number"]] == str(first_user)
        assert second_listing["items"] == []
        assert str(second_user) not in owners(shop).values()

    async def test_an_auth_outage_links_nothing_but_the_list_is_still_served(
        self, shop: Shop
    ) -> None:
        async with shop.client() as client:
            guest = (await shop.order(client)).json()
            _, headers = shop.account()
            shop.directory.down = True

            response = await client.get("/me/orders", headers=headers)

            shop.directory.down = False
            await client.get("/me/orders", headers=headers)  # la tentative suivante reussit

        assert response.status_code == 200
        assert any(
            e["event"] == "order.guest_link_skipped" and e["reason"] == "profile_unavailable"
            for e in shop.lines()
        )
        assert owners(shop)[guest["number"]] is not None

    async def test_buying_while_connected_also_links_earlier_guest_orders(self, shop: Shop) -> None:
        async with shop.client() as client:
            earlier = (await shop.order(client)).json()
            user, headers = shop.account()

            placed = (await shop.order(client, headers, item="tente")).json()

        assert owners(shop) == {earlier["number"]: str(user), placed["number"]: str(user)}

    async def test_a_failure_of_the_linking_never_fails_the_purchase(self, shop: Shop) -> None:
        _, headers = shop.account()

        def boom(token: str) -> None:
            raise RuntimeError("auth en panne")

        shop.directory.profile_of = boom  # type: ignore[method-assign]
        async with shop.client() as client:
            response = await shop.order(client, headers)

        assert response.status_code == 201
        assert any(
            e["event"] == "order.guest_link_skipped" and e["reason"] == "link_failed"
            for e in shop.lines()
        )

    async def test_the_tracking_by_number_and_email_still_works_without_an_account(
        self, shop: Shop
    ) -> None:
        async with shop.client() as client:
            guest = (await shop.order(client)).json()
            _, headers = shop.account()
            await client.get("/me/orders", headers=headers)  # la commande est rattachee

            lookup = await client.post(
                "/orders/lookup", json={"orderNumber": guest["number"], "email": EMAIL}
            )

        assert lookup.status_code == 200
        assert lookup.json()["number"] == guest["number"]


class TestNoSensitiveDataInLogs:
    async def test_neither_the_token_nor_the_address_reach_the_journal(self, shop: Shop) -> None:
        async with shop.client() as client:
            await shop.order(client)
            _, headers = shop.account()
            await client.get("/me/orders", headers=headers)
            await client.get("/me/orders", headers={"Authorization": "Bearer jeton-invalide.x.y"})

        journal = shop.log.getvalue()
        token = headers["Authorization"].removeprefix("Bearer ")
        assert token not in journal and token.split(".")[1] not in journal
        assert EMAIL not in journal
        assert "jeton-invalide" not in journal


class TestHttpProfileDirectory:
    def directory(self, handler: httpx.MockTransport) -> HttpAccountProfileDirectory:
        return HttpAccountProfileDirectory(httpx.Client(transport=handler), "http://auth/me")

    def test_it_reads_the_profile_of_the_token_holder(self) -> None:
        seen: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen.append(request)
            return httpx.Response(200, json={"email": EMAIL, "email_verified": True, "id": "x"})

        profile = self.directory(httpx.MockTransport(handler)).profile_of("jeton")

        assert profile is not None and (profile.email, profile.email_verified) == (EMAIL, True)
        assert seen[0].headers["authorization"] == "Bearer jeton"

    @pytest.mark.parametrize(
        "response",
        [
            httpx.Response(401, json={"detail": "x"}),
            httpx.Response(503),
            httpx.Response(200, text="pas du json"),
            httpx.Response(200, json={"email": EMAIL}),
            httpx.Response(200, json={"email": "", "email_verified": True}),
            httpx.Response(200, json={"email": EMAIL, "email_verified": "oui"}),
            httpx.Response(200, json=["liste"]),
        ],
    )
    def test_any_failure_or_odd_answer_is_no_profile(self, response: httpx.Response) -> None:
        directory = self.directory(httpx.MockTransport(lambda request: response))

        assert directory.profile_of("jeton") is None

    def test_a_network_failure_is_no_profile(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("auth arrete")

        assert self.directory(httpx.MockTransport(handler)).profile_of("jeton") is None
