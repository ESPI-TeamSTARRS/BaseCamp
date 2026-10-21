import pytest

from app.confirmation.domain.enums.payment_method import PaymentMethod


class TestPaymentMethod:
    def test_only_the_three_test_methods_exist(self) -> None:
        assert {method.value for method in PaymentMethod} == {
            "pm_test_success",
            "pm_test_declined",
            "pm_test_timeout",
        }

    @pytest.mark.parametrize("value", ["4242424242424242", "pm_card_visa", "", "PM_TEST_SUCCESS"])
    def test_any_other_value_is_refused(self, value: str) -> None:
        with pytest.raises(ValueError):
            PaymentMethod(value)
