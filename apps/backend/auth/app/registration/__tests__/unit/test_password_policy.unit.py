import pytest

from app.registration.domain.enums.weak_password_reason import WeakPasswordReason
from app.registration.domain.exceptions.weak_password_error import WeakPasswordError
from app.registration.domain.interfaces.common_password_list import CommonPasswordList
from app.registration.domain.services.password_policy import PasswordPolicy


class FakeCommonPasswordList(CommonPasswordList):
    def contains(self, password: str) -> bool:
        return password.lower() == "motdepasse1234"


@pytest.fixture
def policy() -> PasswordPolicy:
    return PasswordPolicy(FakeCommonPasswordList())


class TestPasswordPolicy:
    def test_accepts_a_long_enough_uncommon_password(self, policy: PasswordPolicy) -> None:
        policy.validate("sentier-du-mont-blanc")

    def test_accepts_exactly_twelve_characters(self, policy: PasswordPolicy) -> None:
        policy.validate("a" * 12)

    def test_has_no_composition_rule(self, policy: PasswordPolicy) -> None:
        policy.validate("minusculesseulement")

    def test_counts_characters_not_bytes(self, policy: PasswordPolicy) -> None:
        policy.validate("é" * 12)

    def test_rejects_eleven_characters(self, policy: PasswordPolicy) -> None:
        with pytest.raises(WeakPasswordError) as raised:
            policy.validate("a" * 11)

        assert raised.value.reason is WeakPasswordReason.TOO_SHORT

    def test_rejects_a_common_password_whatever_the_case(self, policy: PasswordPolicy) -> None:
        with pytest.raises(WeakPasswordError) as raised:
            policy.validate("MotDePasse1234")

        assert raised.value.reason is WeakPasswordReason.TOO_COMMON

    def test_rejects_an_oversized_password(self, policy: PasswordPolicy) -> None:
        with pytest.raises(WeakPasswordError) as raised:
            policy.validate("a" * 129)

        assert raised.value.reason is WeakPasswordReason.TOO_LONG

    def test_error_message_never_reflects_the_password(self, policy: PasswordPolicy) -> None:
        with pytest.raises(WeakPasswordError) as raised:
            policy.validate("trop-court")

        assert "trop-court" not in str(raised.value)
