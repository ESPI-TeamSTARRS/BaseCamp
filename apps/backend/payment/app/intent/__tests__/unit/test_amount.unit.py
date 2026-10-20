import pytest

from app.intent.domain.value_objects.amount import Amount


class TestAmount:
    def test_accepts_a_positive_integer_of_cents(self) -> None:
        assert Amount(1999).cents == 1999

    @pytest.mark.parametrize("value", [0, -1, -500])
    def test_rejects_zero_and_negative_amounts(self, value: int) -> None:
        with pytest.raises(ValueError, match="strictement positif"):
            Amount(value)

    @pytest.mark.parametrize("value", [10.5, "10", True])
    def test_rejects_non_integer_values(self, value: object) -> None:
        with pytest.raises(TypeError, match="entier"):
            Amount(value)  # type: ignore[arg-type]
