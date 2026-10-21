import dataclasses

import pytest

from app.core.__tests__.in_memory_business_event_logger import InMemoryBusinessEventLogger
from app.core.events.outcome import Outcome
from app.order.__tests__.fake_order_unit_of_work import (
    FakeOrderUnitOfWork,
    FakePseudonymizer,
    InMemoryStore,
    default_stock,
)
from app.order.application.idempotency_key_reused_error import IdempotencyKeyReusedError
from app.order.application.insufficient_stock_error import InsufficientStockError
from app.order.application.invalid_order_error import InvalidOrderError
from app.order.application.place_order import PlaceOrderUseCase
from app.order.application.place_order_command import PlaceOrderCommand
from app.order.domain.enums.order_status import OrderStatus
from app.order.domain.enums.shipping_country import ShippingCountry
from app.order.domain.value_objects.shipping_address import ShippingAddress

EMAIL = "camille.martin@example.org"


def _command(
    items: tuple[tuple[str, int], ...] = (("popote", 1),),
    key: str = "cle-0001-abcdef",
    country: str = "FR",
) -> PlaceOrderCommand:
    return PlaceOrderCommand(
        idempotency_key=key,
        email=EMAIL,
        full_name="Camille Martin",
        address_line1="12 rue des Alpes",
        address_line2=None,
        postal_code="38000",
        city="Grenoble",
        country=country,
        items=items,
    )


class _Harness:
    def __init__(self) -> None:
        self.store = InMemoryStore(stock=default_stock())
        self.events = InMemoryBusinessEventLogger()
        self.use_case = PlaceOrderUseCase(
            lambda: FakeOrderUnitOfWork(self.store), self.events, FakePseudonymizer()
        )

    def stock_of(self, product_id: str) -> int:
        return self.store.stock[product_id].stock


@pytest.fixture
def harness() -> _Harness:
    return _Harness()


class TestPlaceOrderCreation:
    def test_creates_a_pending_payment_order_with_frozen_prices_and_reserved_stock(
        self, harness: _Harness
    ) -> None:
        placed = harness.use_case.execute(_command((("tente", 1), ("popote", 2))))

        order = placed.order
        assert placed.created is True
        assert order.status is OrderStatus.PENDING_PAYMENT
        assert order.number.startswith("BC-")
        assert [
            (line.product_id, line.unit_price_cents, line.quantity) for line in order.lines
        ] == [
            ("tente", 32900, 1),
            ("popote", 3900, 2),
        ]
        assert order.subtotal_cents == 40700
        assert order.shipping_cents == 0
        assert order.total_cents == 40700
        assert harness.stock_of("tente") == 23
        assert harness.stock_of("popote") == 54
        assert [(r.product_id, r.quantity) for r in harness.store.reservations] == [
            ("tente", 1),
            ("popote", 2),
        ]

    def test_adds_590_shipping_below_80_euros(self, harness: _Harness) -> None:
        order = harness.use_case.execute(_command((("popote", 1),))).order

        assert (order.subtotal_cents, order.shipping_cents, order.total_cents) == (3900, 590, 4490)

    def test_keeps_the_email_and_the_normalised_address(self, harness: _Harness) -> None:
        order = harness.use_case.execute(_command(country="be")).order

        assert order.email == EMAIL
        assert order.address == ShippingAddress(
            full_name="Camille Martin",
            line1="12 rue des Alpes",
            line2=None,
            postal_code="38000",
            city="Grenoble",
            country=ShippingCountry.BE,
        )

    def test_the_frozen_price_does_not_follow_later_catalog_changes(
        self, harness: _Harness
    ) -> None:
        order = harness.use_case.execute(_command((("popote", 1),))).order
        harness.store.stock["popote"] = dataclasses.replace(
            harness.store.stock["popote"], price_cents=9999
        )

        stored = harness.store.orders[order.idempotency_key]
        assert stored.lines[0].unit_price_cents == 3900

    @pytest.mark.parametrize("country", ["FR", "BE", "CH", "LU", "DE", "ES", "IT"])
    def test_accepts_the_seven_supported_countries(self, harness: _Harness, country: str) -> None:
        order = harness.use_case.execute(_command(country=country)).order

        assert order.address.country.value == country


class TestPlaceOrderIdempotency:
    def test_replaying_the_same_key_returns_the_same_order_without_duplicate(
        self, harness: _Harness
    ) -> None:
        first = harness.use_case.execute(_command((("popote", 2),)))
        second = harness.use_case.execute(_command((("popote", 2),)))

        assert second.created is False
        assert second.order.id == first.order.id
        assert second.order.number == first.order.number
        assert len(harness.store.orders) == 1
        assert harness.stock_of("popote") == 54  # reserve une seule fois
        assert len(harness.store.reservations) == 1

    def test_the_same_key_with_another_content_is_refused(self, harness: _Harness) -> None:
        harness.use_case.execute(_command((("popote", 1),)))

        with pytest.raises(IdempotencyKeyReusedError):
            harness.use_case.execute(_command((("popote", 3),)))

    def test_the_line_order_does_not_change_the_fingerprint(self, harness: _Harness) -> None:
        first = harness.use_case.execute(_command((("tente", 1), ("popote", 1))))
        second = harness.use_case.execute(_command((("popote", 1), ("tente", 1))))

        assert second.created is False
        assert second.order.id == first.order.id

    def test_a_concurrent_insert_of_the_same_key_returns_the_winning_order(
        self, harness: _Harness
    ) -> None:
        winner = harness.use_case.execute(_command(key="cle-0002-abcdef"))
        harness.store.orders.clear()
        harness.store.concurrent_order = winner.order

        placed = harness.use_case.execute(_command(key="cle-0002-abcdef"))

        assert placed.created is False
        assert placed.order.id == winner.order.id


class TestPlaceOrderStock:
    def test_insufficient_stock_gives_an_error_and_no_partial_reservation(
        self, harness: _Harness
    ) -> None:
        with pytest.raises(InsufficientStockError):
            harness.use_case.execute(_command((("tente", 1), ("rare", 3))))

        assert harness.stock_of("tente") == 24  # la ligne valide n'est pas reservee non plus
        assert harness.stock_of("rare") == 2
        assert harness.store.orders == {}
        assert harness.store.reservations == []

    def test_an_out_of_stock_product_cannot_be_ordered(self, harness: _Harness) -> None:
        with pytest.raises(InsufficientStockError):
            harness.use_case.execute(_command((("epuise", 1),)))

    def test_the_last_pieces_can_be_ordered_exactly(self, harness: _Harness) -> None:
        harness.use_case.execute(_command((("rare", 2),)))

        assert harness.stock_of("rare") == 0


class TestPlaceOrderValidation:
    def test_refuses_a_country_outside_the_list(self, harness: _Harness) -> None:
        with pytest.raises(InvalidOrderError) as error:
            harness.use_case.execute(_command(country="US"))

        assert error.value.message == "Pays de livraison non pris en charge."
        assert harness.store.orders == {}

    def test_refuses_an_unknown_product_without_echoing_its_id(self, harness: _Harness) -> None:
        with pytest.raises(InvalidOrderError) as error:
            harness.use_case.execute(_command((("zz-evil-zz", 1),)))

        assert "zz-evil-zz" not in error.value.message

    @pytest.mark.parametrize(
        "items",
        [(), (("popote", 0),), (("popote", 11),), (("popote", 1), ("popote", 1))],
    )
    def test_refuses_an_invalid_cart(
        self, harness: _Harness, items: tuple[tuple[str, int], ...]
    ) -> None:
        with pytest.raises(InvalidOrderError):
            harness.use_case.execute(_command(items))

    def test_refuses_more_than_fifty_lines(self, harness: _Harness) -> None:
        with pytest.raises(InvalidOrderError):
            harness.use_case.execute(_command(tuple((f"p{i}", 1) for i in range(51))))


class TestPlaceOrderBusinessEvents:
    @staticmethod
    def _names(harness: _Harness) -> list[str]:
        return [event.event for event in harness.events.events]

    def test_emits_stock_reserved_then_order_created_with_stable_fields(
        self, harness: _Harness
    ) -> None:
        order = harness.use_case.execute(_command()).order

        assert self._names(harness) == ["stock.reserved", "order.created"]
        created = harness.events.events[-1]
        assert created.outcome is Outcome.SUCCESS
        assert created.reason is None
        assert created.resource_type == "order"
        assert created.resource_id == order.number
        assert created.attributes == {
            "email_hash": FakePseudonymizer().pseudonymize(EMAIL),
            "line_count": 1,
            "total_cents": 4490,
            "country": "FR",
        }

    def test_events_never_carry_the_email_nor_the_address_nor_the_key(
        self, harness: _Harness
    ) -> None:
        harness.use_case.execute(_command())

        dump = repr(harness.events.events)
        assert EMAIL not in dump
        assert "camille" not in dump
        assert "rue des Alpes" not in dump
        assert "cle-0001-abcdef" not in dump

    def test_the_email_hash_is_stable_per_address(self, harness: _Harness) -> None:
        harness.use_case.execute(_command(key="cle-0003-abcdef"))
        harness.use_case.execute(_command(key="cle-0004-abcdef"))

        hashes = {event.attributes["email_hash"] for event in harness.events.events}
        assert len(hashes) == 1

    def test_emits_a_denied_stock_insufficient_event(self, harness: _Harness) -> None:
        with pytest.raises(InsufficientStockError):
            harness.use_case.execute(_command((("rare", 3),)))

        assert self._names(harness) == ["stock.insufficient"]
        event = harness.events.events[0]
        assert event.outcome is Outcome.DENIED
        assert event.reason == "insufficient_stock"
        assert (event.resource_type, event.resource_id) == ("product", "rare")

    def test_emits_order_replayed_on_an_idempotent_replay(self, harness: _Harness) -> None:
        placed = harness.use_case.execute(_command())
        harness.events.events.clear()

        harness.use_case.execute(_command())

        assert self._names(harness) == ["order.replayed"]
        event = harness.events.events[0]
        assert event.outcome is Outcome.SUCCESS
        assert event.resource_id == placed.order.number

    @pytest.mark.parametrize(
        ("kwargs", "reason"),
        [
            ({"country": "US"}, "country_not_supported"),
            ({"items": ()}, "invalid_cart"),
            ({"items": (("popote", 11),)}, "quantity_out_of_range"),
            ({"items": (("popote", 1), ("popote", 1))}, "duplicate_product"),
            ({"items": (("zz-evil-zz", 1),)}, "product_not_found"),
        ],
    )
    def test_emits_order_rejected_with_a_snake_case_reason(
        self, harness: _Harness, kwargs: dict[str, object], reason: str
    ) -> None:
        with pytest.raises(InvalidOrderError):
            harness.use_case.execute(_command(**kwargs))  # type: ignore[arg-type]

        assert self._names(harness) == ["order.rejected"]
        event = harness.events.events[0]
        assert event.outcome is Outcome.DENIED
        assert event.reason == reason
        assert "zz-evil-zz" not in repr(event)

    def test_emits_order_rejected_when_the_key_is_reused_with_another_content(
        self, harness: _Harness
    ) -> None:
        harness.use_case.execute(_command((("popote", 1),)))
        harness.events.events.clear()

        with pytest.raises(IdempotencyKeyReusedError):
            harness.use_case.execute(_command((("popote", 3),)))

        assert self._names(harness) == ["order.rejected"]
        assert harness.events.events[0].reason == "idempotency_key_reused"
