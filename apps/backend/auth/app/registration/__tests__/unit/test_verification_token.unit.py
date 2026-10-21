from datetime import UTC, datetime, timedelta
from uuid import uuid4

from app.registration.domain.entities.verification_token import (
    VERIFICATION_TOKEN_TTL,
    VerificationToken,
)

NOW = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)


class TestVerificationToken:
    def test_ttl_is_24_hours(self) -> None:
        assert timedelta(hours=24) == VERIFICATION_TOKEN_TTL

    def test_issued_token_expires_in_24_hours_and_is_unused(self) -> None:
        token = VerificationToken.issue(uuid4(), "a" * 64, NOW)

        assert token.expires_at == NOW + timedelta(hours=24)
        assert token.used_at is None

    def test_is_usable_before_expiry(self) -> None:
        token = VerificationToken.issue(uuid4(), "a" * 64, NOW)

        assert token.is_usable(NOW + timedelta(hours=23, minutes=59)) is True

    def test_is_not_usable_at_expiry(self) -> None:
        token = VerificationToken.issue(uuid4(), "a" * 64, NOW)

        assert token.is_usable(NOW + timedelta(hours=24)) is False

    def test_is_not_usable_once_used(self) -> None:
        token = VerificationToken.issue(uuid4(), "a" * 64, NOW).mark_used(NOW)

        assert token.is_usable(NOW + timedelta(minutes=1)) is False
