from datetime import UTC, datetime

from app.registration.domain.entities.user import User
from app.registration.domain.enums.user_role import UserRole
from app.registration.domain.value_objects.email_address import EmailAddress

NOW = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)


class TestUser:
    def test_a_new_account_is_a_customer_with_unverified_email(self) -> None:
        user = User.register(EmailAddress.of("camille@example.com"), "$argon2id$hash", NOW)

        assert user.role is UserRole.CUSTOMER
        assert user.email_verified_at is None
        assert user.created_at == NOW

    def test_representation_never_contains_the_password_hash(self) -> None:
        user = User.register(EmailAddress.of("camille@example.com"), "$argon2id$secret", NOW)

        assert "secret" not in repr(user)
