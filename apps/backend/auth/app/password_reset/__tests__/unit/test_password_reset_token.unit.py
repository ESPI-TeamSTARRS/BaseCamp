from datetime import UTC, datetime, timedelta
from uuid import uuid4

from app.password_reset.domain.entities.password_reset_token import PasswordResetToken

NOW = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)


class TestPasswordResetToken:
    def test_issue_expires_after_thirty_minutes_and_is_unused(self) -> None:
        token = PasswordResetToken.issue(uuid4(), "h" * 64, NOW)

        assert token.expires_at == NOW + timedelta(minutes=30)
        assert token.used_at is None

    def test_it_is_usable_until_expiry(self) -> None:
        token = PasswordResetToken.issue(uuid4(), "h" * 64, NOW)

        assert token.is_usable(NOW + timedelta(minutes=29, seconds=59))
        assert not token.is_usable(NOW + timedelta(minutes=30))

    def test_a_used_token_is_no_longer_usable(self) -> None:
        token = PasswordResetToken.issue(uuid4(), "h" * 64, NOW).mark_used(NOW)

        assert token.used_at == NOW
        assert not token.is_usable(NOW)
