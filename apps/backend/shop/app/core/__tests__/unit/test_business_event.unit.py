import pytest

from app.core.events.business_event import BusinessEvent
from app.core.events.outcome import Outcome


class TestBusinessEventFactories:
    def test_success_has_no_reason(self) -> None:
        event = BusinessEvent.success("cart.quoted", attributes={"line_count": 2})

        assert (event.event, event.outcome, event.reason) == ("cart.quoted", Outcome.SUCCESS, None)
        assert event.attributes == {"line_count": 2}

    def test_denied_and_error_carry_a_reason(self) -> None:
        denied = BusinessEvent.denied("cart.quote_rejected", "invalid_cart")
        error = BusinessEvent.error("service.unhandled_error", "internal_error")

        assert (denied.outcome, denied.reason) == (Outcome.DENIED, "invalid_cart")
        assert (error.outcome, error.reason) == (Outcome.ERROR, "internal_error")

    def test_resource_and_actor_are_kept(self) -> None:
        event = BusinessEvent.success(
            "catalog.product_viewed", resource_type="product", resource_id="tente-a"
        )

        assert (event.resource_type, event.resource_id) == ("product", "tente-a")


class TestBusinessEventValidation:
    @pytest.mark.parametrize(
        "name", ["Cart.quoted", "quoted", "cart.", "cart quoted.x", "a.b.c", ""]
    )
    def test_event_name_must_be_domain_dot_action_in_lowercase(self, name: str) -> None:
        with pytest.raises(ValueError, match="event"):
            BusinessEvent.success(name)

    def test_a_refusal_without_reason_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="reason"):
            BusinessEvent(event="cart.quote_rejected", outcome=Outcome.DENIED)

    def test_a_success_with_a_reason_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="reason"):
            BusinessEvent(event="cart.quoted", outcome=Outcome.SUCCESS, reason="invalid_cart")

    def test_reason_must_be_a_snake_case_code_not_a_sentence(self) -> None:
        with pytest.raises(ValueError, match="reason"):
            BusinessEvent.denied("cart.quote_rejected", "Le panier est invalide.")

    def test_resource_id_requires_a_resource_type(self) -> None:
        with pytest.raises(ValueError, match="resource"):
            BusinessEvent.success("catalog.product_viewed", resource_id="tente-a")

    def test_attribute_values_must_be_scalars(self) -> None:
        with pytest.raises(ValueError, match="attributes"):
            BusinessEvent.success("cart.quoted", attributes={"lines": [1, 2]})

    def test_attribute_keys_must_be_snake_case(self) -> None:
        with pytest.raises(ValueError, match="attributes"):
            BusinessEvent.success("cart.quoted", attributes={"Line Count": 1})
