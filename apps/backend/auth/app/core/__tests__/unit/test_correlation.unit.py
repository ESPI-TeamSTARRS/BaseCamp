import uuid

import pytest

from app.core.logging import correlation


class TestCorrelationIdValidity:
    @pytest.mark.parametrize(
        "value", ["abcd1234", "7c1f0e52-3a0b-4f1e-9a52-1d6f7a9b2c10", "A" * 64]
    )
    def test_accepts_alphanumeric_and_dash_between_8_and_64_characters(self, value: str) -> None:
        assert correlation.is_valid_correlation_id(value)

    @pytest.mark.parametrize(
        "value",
        ["", "court", "A" * 65, "avec espace", "inj\nection", "<script>1234</script>", None],
    )
    def test_rejects_anything_else(self, value: str | None) -> None:
        assert not correlation.is_valid_correlation_id(value)


class TestCorrelationContext:
    def test_new_id_is_a_uuid4(self) -> None:
        assert uuid.UUID(correlation.new_correlation_id()).version == 4

    def test_set_then_read(self) -> None:
        correlation.set_correlation_id("abcd1234-xyz")

        assert correlation.current_correlation_id() == "abcd1234-xyz"

    def test_outbound_headers_forward_the_current_id(self) -> None:
        correlation.set_correlation_id("abcd1234-xyz")

        assert correlation.outbound_headers() == {"X-Correlation-ID": "abcd1234-xyz"}
