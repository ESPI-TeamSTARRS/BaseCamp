import pytest

from app.cart.__tests__.fake_cart_product_reader import FakeCartProductReader, default_catalog
from app.cart.application.invalid_cart_error import InvalidCartError
from app.cart.application.quote_cart import QuoteCartUseCase
from app.cart.domain.enums.line_status import LineStatus
from app.core.__tests__.in_memory_business_event_logger import InMemoryBusinessEventLogger


def _use_case(events: InMemoryBusinessEventLogger | None = None) -> QuoteCartUseCase:
    return QuoteCartUseCase(
        FakeCartProductReader(default_catalog()), events or InMemoryBusinessEventLogger()
    )


class TestQuoteCartTotals:
    def test_computes_lines_subtotal_free_shipping_and_total_from_database_prices(self) -> None:
        quote = _use_case().execute([("tente", 1), ("popote", 2)])

        assert [(line.product_id, line.line_total_cents) for line in quote.lines] == [
            ("tente", 32900),
            ("popote", 7800),
        ]
        assert quote.subtotal_cents == 40700
        assert quote.shipping_cents == 0
        assert quote.total_cents == 40700

    def test_adds_590_shipping_below_80_euros(self) -> None:
        quote = _use_case().execute([("popote", 1)])

        assert quote.subtotal_cents == 3900
        assert quote.shipping_cents == 590
        assert quote.total_cents == 4490
        assert quote.amount_remaining_for_free_shipping_cents == 4100

    def test_shipping_is_still_charged_just_below_80_euros(self) -> None:
        quote = _use_case().execute([("rare", 2), ("popote", 1)])

        assert quote.subtotal_cents == 7900
        assert quote.shipping_cents == 590
        assert quote.amount_remaining_for_free_shipping_cents == 100

    def test_shipping_is_free_from_80_euros(self) -> None:
        quote = _use_case().execute([("popote", 2), ("rare", 1)])

        assert quote.subtotal_cents == 9800
        assert quote.shipping_cents == 0
        assert quote.amount_remaining_for_free_shipping_cents == 0

    def test_keeps_the_order_of_the_requested_lines(self) -> None:
        quote = _use_case().execute([("popote", 1), ("tente", 1)])

        assert [line.product_id for line in quote.lines] == ["popote", "tente"]


class TestQuoteCartStock:
    def test_flags_a_line_above_the_stock_with_the_available_quantity(self) -> None:
        quote = _use_case().execute([("rare", 5)])

        line = quote.lines[0]
        assert line.status is LineStatus.INSUFFICIENT_STOCK
        assert line.available_quantity == 2
        assert quote.has_issues is True

    def test_flags_a_sold_out_product_with_zero_available(self) -> None:
        line = _use_case().execute([("epuise", 1)]).lines[0]

        assert line.status is LineStatus.INSUFFICIENT_STOCK
        assert line.available_quantity == 0

    def test_a_line_within_stock_is_ok(self) -> None:
        quote = _use_case().execute([("rare", 2)])

        assert quote.lines[0].status is LineStatus.OK
        assert quote.has_issues is False


class TestQuoteCartValidation:
    @pytest.mark.parametrize(
        "items",
        [
            [],
            [("tente", 0)],
            [("tente", 11)],
            [("tente", -1)],
            [("zz-evil-zz", 1)],
            [("tente", 1), ("tente", 2)],
            [(f"p{i}", 1) for i in range(51)],
        ],
    )
    def test_rejects_invalid_carts(self, items: list[tuple[str, int]]) -> None:
        with pytest.raises(InvalidCartError):
            _use_case().execute(items)

    def test_error_message_never_echoes_the_input(self) -> None:
        with pytest.raises(InvalidCartError) as error:
            _use_case().execute([("zz-evil-zz", 1)])

        assert "zz-evil-zz" not in str(error.value)

    def test_accepts_fifty_distinct_lines(self) -> None:
        catalog = default_catalog()
        use_case = QuoteCartUseCase(FakeCartProductReader(catalog), InMemoryBusinessEventLogger())

        quote = use_case.execute([(p.id, 1) for p in catalog])

        assert len(quote.lines) == len(catalog)


class TestQuoteCartEvents:
    def test_a_quote_emits_cart_quoted_with_line_count_and_total(self) -> None:
        events = InMemoryBusinessEventLogger()

        _use_case(events).execute([("tente", 1), ("popote", 2)])

        (event,) = events.events
        assert (event.event, event.outcome.value, event.reason) == ("cart.quoted", "success", None)
        assert event.attributes == {"line_count": 2, "total_cents": 40700}

    @pytest.mark.parametrize(
        ("items", "reason"),
        [
            ([], "invalid_cart"),
            ([(f"p{i}", 1) for i in range(51)], "invalid_cart"),
            ([("tente", 0)], "quantity_out_of_range"),
            ([("tente", 11)], "quantity_out_of_range"),
            ([("tente", 1), ("tente", 2)], "duplicate_product"),
            ([("inconnu", 1)], "product_not_found"),
        ],
    )
    def test_a_rejected_cart_emits_a_denied_event_with_a_stable_reason(
        self, items: list[tuple[str, int]], reason: str
    ) -> None:
        events = InMemoryBusinessEventLogger()

        with pytest.raises(InvalidCartError):
            _use_case(events).execute(items)

        (event,) = events.events
        assert (event.event, event.outcome.value, event.reason) == (
            "cart.quote_rejected",
            "denied",
            reason,
        )
        assert "inconnu" not in repr(event)
