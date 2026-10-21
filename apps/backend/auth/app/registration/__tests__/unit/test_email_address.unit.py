import pytest

from app.registration.domain.exceptions.invalid_email_error import InvalidEmailError
from app.registration.domain.value_objects.email_address import EmailAddress


class TestEmailAddress:
    def test_normalizes_case_and_surrounding_spaces(self) -> None:
        assert (
            EmailAddress.of("  Camille.Dupont@Example.COM ").value == "camille.dupont@example.com"
        )

    @pytest.mark.parametrize(
        "raw",
        [
            "",
            "sans-arobase",
            "a@b",
            "@example.com",
            "camille@",
            "deux@@example.com",
            "espace dans@example.com",
            "camille@exa mple.com",
            "camille@-example.com",
            "camille@example..com",
            "camille@example.com\r\nBcc: victime@example.org",
            "camille\n@example.com",
            f"{'a' * 65}@example.com",
            f"a@{'b' * 250}.com",
        ],
    )
    def test_rejects_malformed_addresses(self, raw: str) -> None:
        with pytest.raises(InvalidEmailError):
            EmailAddress.of(raw)

    def test_invalid_email_message_never_reflects_the_input(self) -> None:
        with pytest.raises(InvalidEmailError) as raised:
            EmailAddress.of("secret-saisie")

        assert "secret-saisie" not in str(raised.value)
        assert raised.value.code == "email_invalid"
