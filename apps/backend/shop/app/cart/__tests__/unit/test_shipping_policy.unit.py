import pytest

from app.cart.domain.services.shipping_policy import ShippingPolicy


class TestShippingPolicy:
    @pytest.mark.parametrize(
        ("subtotal_cents", "expected"),
        [(1, 590), (7999, 590), (8000, 0), (8001, 0), (50000, 0)],
    )
    def test_shipping_is_590_below_the_free_threshold(
        self, subtotal_cents: int, expected: int
    ) -> None:
        assert ShippingPolicy.shipping_cents(subtotal_cents) == expected

    def test_empty_subtotal_has_no_shipping(self) -> None:
        assert ShippingPolicy.shipping_cents(0) == 0

    def test_threshold_is_80_euros(self) -> None:
        assert ShippingPolicy.FREE_SHIPPING_THRESHOLD_CENTS == 8000
