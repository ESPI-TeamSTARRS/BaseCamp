import pytest

from app.core.logging.email_pseudonymizer import EmailPseudonymizer


class TestEmailPseudonymizer:
    def test_is_stable_and_16_hex_characters(self) -> None:
        pseudonymizer = EmailPseudonymizer("cle-de-test")

        first = pseudonymizer.pseudonymize("Jean@Exemple.fr")

        assert first == pseudonymizer.pseudonymize("  jean@exemple.fr ")
        assert len(first) == 16
        assert int(first, 16) >= 0

    def test_does_not_contain_the_email(self) -> None:
        assert "jean" not in EmailPseudonymizer("cle").pseudonymize("jean@exemple.fr")

    def test_depends_on_the_key(self) -> None:
        email = "jean@exemple.fr"

        assert EmailPseudonymizer("cle-a").pseudonymize(email) != EmailPseudonymizer(
            "cle-b"
        ).pseudonymize(email)

    def test_an_empty_key_is_refused(self) -> None:
        with pytest.raises(ValueError, match="key"):
            EmailPseudonymizer("")


class TestBuildPseudonymizer:
    def test_without_a_key_an_ephemeral_one_is_used(self) -> None:
        from app.core.logging.email_pseudonymizer import build_pseudonymizer

        first = build_pseudonymizer("").pseudonymize("a@b.fr")
        second = build_pseudonymizer("").pseudonymize("a@b.fr")

        assert first != second

    def test_with_a_key_it_is_deterministic(self) -> None:
        from app.core.logging.email_pseudonymizer import build_pseudonymizer

        first = build_pseudonymizer("k").pseudonymize("a@b.fr")
        second = build_pseudonymizer("k").pseudonymize("a@b.fr")

        assert first == second
