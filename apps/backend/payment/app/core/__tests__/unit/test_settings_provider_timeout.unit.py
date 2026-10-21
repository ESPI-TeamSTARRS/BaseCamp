import pytest
from pydantic import ValidationError

from app.core.config import Settings


class TestProviderTimeout:
    def test_defaults_to_a_short_bounded_delay(self) -> None:
        assert 0 < Settings().provider_timeout_seconds <= 5

    @pytest.mark.parametrize("value", [0, -1, 30])
    def test_a_delay_outside_the_bounds_is_refused(self, value: float) -> None:
        with pytest.raises(ValidationError):
            Settings(provider_timeout_seconds=value)
