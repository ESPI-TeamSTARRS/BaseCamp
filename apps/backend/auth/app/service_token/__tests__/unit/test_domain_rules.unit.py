import dataclasses

import pytest

from app.service_token.domain.entities.client_declaration import ClientDeclaration
from app.service_token.domain.entities.issued_token import IssuedToken
from app.service_token.domain.entities.service_client import ServiceClient
from app.service_token.domain.enums.service_audience import ServiceAudience
from app.service_token.domain.enums.service_scope import ServiceScope
from app.service_token.domain.exceptions.invalid_declaration_error import InvalidDeclarationError

LONG_SECRET = "s" * 32


class TestServiceScope:
    def test_payments_write_belongs_to_the_payment_audience(self) -> None:
        assert ServiceScope.PAYMENTS_WRITE.audience is ServiceAudience.PAYMENT

    def test_refunds_write_belongs_to_the_payment_audience(self) -> None:
        assert ServiceScope.REFUNDS_WRITE.audience is ServiceAudience.PAYMENT

    def test_scope_value_is_the_wire_format(self) -> None:
        assert ServiceScope("payments:write") is ServiceScope.PAYMENTS_WRITE
        assert ServiceScope("refunds:write") is ServiceScope.REFUNDS_WRITE


class TestClientDeclaration:
    def test_accepts_a_long_enough_secret(self) -> None:
        declaration = ClientDeclaration(
            "shop", frozenset({ServiceScope.PAYMENTS_WRITE}), LONG_SECRET, None
        )

        assert declaration.previous_secret is None

    def test_rejects_a_short_current_secret(self) -> None:
        with pytest.raises(InvalidDeclarationError):
            ClientDeclaration("shop", frozenset({ServiceScope.PAYMENTS_WRITE}), "short", None)

    def test_rejects_a_short_previous_secret(self) -> None:
        with pytest.raises(InvalidDeclarationError):
            ClientDeclaration(
                "shop", frozenset({ServiceScope.PAYMENTS_WRITE}), LONG_SECRET, "short"
            )

    def test_rejects_a_malformed_client_id(self) -> None:
        with pytest.raises(InvalidDeclarationError):
            ClientDeclaration("Shop Évil", frozenset({ServiceScope.PAYMENTS_WRITE}), LONG_SECRET)

    def test_never_shows_secrets_in_its_representation(self) -> None:
        declaration = ClientDeclaration(
            "shop",
            frozenset({ServiceScope.PAYMENTS_WRITE}),
            "current-" + LONG_SECRET,
            "prev-" + LONG_SECRET,
        )

        assert "current-" not in repr(declaration)
        assert "prev-" not in repr(declaration)


class TestServiceClient:
    def test_never_shows_hashes_in_its_representation(self) -> None:
        client = ServiceClient("shop", frozenset(), "hash-current", "hash-previous")

        assert "hash-" not in repr(client)

    def test_is_immutable(self) -> None:
        client = ServiceClient("shop", frozenset(), "hash-current")

        with pytest.raises(dataclasses.FrozenInstanceError):
            client.client_id = "other"  # type: ignore[misc]


class TestIssuedToken:
    def test_never_shows_the_token_in_its_representation(self) -> None:
        issued = IssuedToken("eyJ.secret.token", 300, "payments:write")

        assert "secret" not in repr(issued)

    def test_exposes_expiry_in_seconds(self) -> None:
        assert IssuedToken("t", 300, "payments:write").expires_in == 300
