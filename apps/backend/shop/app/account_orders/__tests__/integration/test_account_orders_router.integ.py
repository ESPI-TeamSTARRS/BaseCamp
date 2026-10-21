from collections.abc import Iterator
from uuid import uuid4

import pytest
from sqlalchemy import text

from app.account_orders.__tests__.stack import EMAIL, OTHER_EMAIL, Shop


@pytest.fixture
def shop() -> Iterator[Shop]:
    shop = Shop()
    yield shop
    shop.engine.dispose()


def owner_of(shop: Shop, number: str) -> str | None:
    with shop.engine.connect() as connection:
        value = connection.execute(
            text("SELECT user_id FROM orders WHERE number = :n"), {"n": number}
        ).scalar_one()
    return None if value is None else str(value)


class TestPlacingAnOrder:
    async def test_a_guest_order_is_unchanged_and_has_no_account(self, shop: Shop) -> None:
        async with shop.client() as client:
            response = await shop.order(client)

        assert response.status_code == 201
        assert owner_of(shop, response.json()["number"]) is None

    async def test_a_connected_customer_order_carries_only_the_account_identifier(
        self, shop: Shop
    ) -> None:
        user, headers = shop.account()
        async with shop.client() as client:
            response = await shop.order(client, headers)

        body = response.json()
        assert response.status_code == 201
        assert owner_of(shop, body["number"]) == str(user)
        assert "user_id" not in body and str(user) not in response.text

    async def test_the_response_shape_is_identical_for_guests_and_customers(
        self, shop: Shop
    ) -> None:
        _, headers = shop.account()
        async with shop.client() as client:
            guest = await shop.order(client)
            member = await shop.order(client, headers)

        assert set(guest.json()) == set(member.json())

    @pytest.mark.parametrize(
        "header",
        [
            {"Authorization": "Bearer pas.un.jeton"},
            {"Authorization": "Basic dXNlcjpwYXNz"},
            {"Authorization": "Bearer "},
        ],
    )
    async def test_an_invalid_token_never_blocks_a_purchase(
        self, shop: Shop, header: dict[str, str]
    ) -> None:
        async with shop.client() as client:
            response = await shop.order(client, header)

        assert response.status_code == 201
        assert owner_of(shop, response.json()["number"]) is None

    async def test_an_expired_or_foreign_token_is_treated_as_a_guest(self, shop: Shop) -> None:
        expired = shop.key.token(issued_at=1.0)
        async with shop.client() as client:
            response = await shop.order(client, {"Authorization": f"Bearer {expired}"})

        assert response.status_code == 201
        assert owner_of(shop, response.json()["number"]) is None
        assert any(line["event"] == "customer.token_rejected" for line in shop.lines())

    async def test_an_auth_outage_without_any_key_still_lets_the_customer_buy_as_a_guest(
        self, shop: Shop
    ) -> None:
        _, headers = shop.account()
        shop.jwks.down = True
        async with shop.client() as client:
            response = await shop.order(client, headers)

        assert response.status_code == 201
        assert owner_of(shop, response.json()["number"]) is None


class TestListing:
    async def test_without_a_token_the_answer_is_a_generic_401(self, shop: Shop) -> None:
        async with shop.client() as client:
            routes = [
                await client.get("/me/orders"),
                await client.get(f"/me/orders/{uuid4()}"),
                await client.get("/me/orders", headers={"Authorization": "Bearer faux.jeton.x"}),
            ]

        for response in routes:
            assert response.status_code == 401
            assert response.json() == {"detail": "Authentification requise."}
            assert response.headers["www-authenticate"] == "Bearer"

    async def test_only_my_orders_are_listed_newest_first(self, shop: Shop) -> None:
        _, mine = shop.account()
        _, theirs = shop.account(email=OTHER_EMAIL)
        async with shop.client() as client:
            first = await shop.order(client, mine)
            second = await shop.order(client, mine, item="tente")
            other = await shop.order(client, theirs, email=OTHER_EMAIL)
            guest = await shop.order(client, email="invite@example.org")
            listing = await client.get("/me/orders", headers=mine)

        body = listing.json()
        assert listing.status_code == 200
        assert {item["number"] for item in body["items"]} == {
            first.json()["number"],
            second.json()["number"],
        }
        assert other.json()["number"] not in listing.text
        assert guest.json()["number"] not in listing.text
        assert body["total"] == 2
        assert listing.headers["cache-control"] == "no-store"

    async def test_the_listing_never_exposes_the_email_or_the_address(self, shop: Shop) -> None:
        _, mine = shop.account()
        async with shop.client() as client:
            await shop.order(client, mine)
            listing = await client.get("/me/orders", headers=mine)

        assert EMAIL not in listing.text
        assert "Grenoble" not in listing.text and "rue des Alpes" not in listing.text
        item = listing.json()["items"][0]
        assert set(item) == {
            "id",
            "number",
            "status",
            "lines",
            "subtotal_cents",
            "shipping_cents",
            "total_cents",
            "created_at",
        }
        assert item["lines"][0] == {
            "name": "Popote",
            "unit_price_cents": 3900,
            "quantity": 1,
            "line_total_cents": 3900,
        }

    async def test_it_is_paginated(self, shop: Shop) -> None:
        _, mine = shop.account()
        async with shop.client() as client:
            for _ in range(5):
                await shop.order(client, mine)
            first = (await client.get("/me/orders?limit=2&offset=0", headers=mine)).json()
            last = (await client.get("/me/orders?limit=2&offset=4", headers=mine)).json()

        assert (first["total"], len(first["items"]), len(last["items"])) == (5, 2, 1)

    @pytest.mark.parametrize("query", ["limit=0", "limit=51", "offset=-1", "limit=x"])
    async def test_invalid_pagination_is_a_422(self, shop: Shop, query: str) -> None:
        _, mine = shop.account()
        async with shop.client() as client:
            response = await client.get(f"/me/orders?{query}", headers=mine)

        assert response.status_code == 422


class TestDetail:
    async def test_my_order_is_returned(self, shop: Shop) -> None:
        _, mine = shop.account()
        async with shop.client() as client:
            placed = (await shop.order(client, mine)).json()
            response = await client.get(f"/me/orders/{placed['id']}", headers=mine)

        assert response.status_code == 200
        assert response.json()["number"] == placed["number"]
        assert EMAIL not in response.text

    async def test_another_account_order_and_an_unknown_one_get_the_very_same_404(
        self, shop: Shop
    ) -> None:
        _, mine = shop.account()
        _, theirs = shop.account(email=OTHER_EMAIL)
        async with shop.client() as client:
            placed = (await shop.order(client, theirs, email=OTHER_EMAIL)).json()
            foreign = await client.get(f"/me/orders/{placed['id']}", headers=mine)
            unknown = await client.get(f"/me/orders/{uuid4()}", headers=mine)

        assert foreign.status_code == unknown.status_code == 404
        assert foreign.content == unknown.content == b'{"detail":"Commande introuvable."}'
        assert placed["number"] not in foreign.text

    async def test_a_guest_order_is_not_reachable_by_its_id(self, shop: Shop) -> None:
        _, mine = shop.account()
        async with shop.client() as client:
            placed = (await shop.order(client)).json()
            response = await client.get(f"/me/orders/{placed['id']}", headers=mine)

        assert response.status_code == 404

    async def test_a_malformed_identifier_is_a_422(self, shop: Shop) -> None:
        _, mine = shop.account()
        async with shop.client() as client:
            response = await client.get("/me/orders/pas-un-uuid", headers=mine)

        assert response.status_code == 422


class TestAuthOutage:
    async def test_known_keys_keep_verifying_tokens_when_auth_is_down(self, shop: Shop) -> None:
        _, mine = shop.account()
        async with shop.client() as client:
            assert (await client.get("/me/orders", headers=mine)).status_code == 200
            shop.jwks.down = True
            shop.directory.down = True
            shop.clock_value += 10_000  # cles perimees, auth arrete

            response = await client.get("/me/orders", headers=mine)

        assert response.status_code == 200

    async def test_without_any_key_the_answer_is_a_503_not_a_401(self, shop: Shop) -> None:
        _, mine = shop.account()
        shop.jwks.down = True
        async with shop.client() as client:
            response = await client.get("/me/orders", headers=mine)

        assert response.status_code == 503
        assert response.headers["retry-after"] == "5"
        assert response.json() == {"detail": "Identification momentanément indisponible."}
