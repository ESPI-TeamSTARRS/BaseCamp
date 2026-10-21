"""Garde d'administration : jeton d'`auth` vérifié par JWKS, rôle `operator` et second facteur `face`."""

from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

import pytest

from app.core.__tests__.in_memory_business_event_logger import InMemoryBusinessEventLogger
from app.customer_identity.__tests__.tokens import AUDIENCE, ISSUER, SigningKey
from app.customer_identity.application.authorize_operator import AuthorizeOperatorUseCase
from app.customer_identity.application.forbidden_error import ForbiddenError
from app.customer_identity.application.identity_unavailable_error import IdentityUnavailableError
from app.customer_identity.application.unauthenticated_error import UnauthenticatedError
from app.customer_identity.domain.exceptions.verification_keys_unavailable_error import (
    VerificationKeysUnavailableError,
)
from app.customer_identity.domain.interfaces.clock import Clock
from app.customer_identity.domain.interfaces.jwks_source import JwksSource
from app.customer_identity.infrastructure.clients.jwks_client_token_verifier import (
    JwksClientTokenVerifier,
)
from app.customer_identity.infrastructure.clients.jwks_key_cache import JwksKeyCache

NOW = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)


class _Jwks(JwksSource):
    def __init__(self, key: SigningKey) -> None:
        self.keys = {key.kid: key.jwk}
        self.down = False

    def fetch(self) -> Mapping[str, Mapping[str, Any]]:
        if self.down:
            raise VerificationKeysUnavailableError
        return dict(self.keys)


class _FixedClock(Clock):
    def now(self) -> datetime:
        return NOW


class _Setup:
    def __init__(self) -> None:
        self.key = SigningKey()
        self.jwks = _Jwks(self.key)
        self.events = InMemoryBusinessEventLogger()
        cache = JwksKeyCache(self.jwks, lambda: 1000.0, 300.0, 10.0)
        self.use_case = AuthorizeOperatorUseCase(
            JwksClientTokenVerifier(cache, ISSUER, AUDIENCE), _FixedClock(), self.events, "face"
        )

    def token(self, roles: list[str], amr: list[str] | None, **kwargs: Any) -> str:
        extra: dict[str, Any] = {"roles": roles}
        if amr is not None:
            extra["amr"] = amr
        return self.key.token(issued_at=NOW.timestamp(), extra=extra, **kwargs)


class TestAuthorizedOperator:
    def test_an_operator_with_the_face_factor_is_accepted(self) -> None:
        setup = _Setup()

        operator = setup.use_case.require(setup.token(["operator"], ["pwd", "face"]))

        assert operator.roles == ("operator",)
        assert "face" in operator.authentication_methods


class TestRefusedWithoutToken:
    @pytest.mark.parametrize("token", [None, ""])
    def test_no_token_is_a_401(self, token: str | None) -> None:
        with pytest.raises(UnauthenticatedError):
            _Setup().use_case.require(token)

    def test_a_forged_expired_or_foreign_token_is_a_401_not_a_403(self) -> None:
        setup = _Setup()
        foreign = SigningKey("autre").token(issued_at=NOW.timestamp())
        expired = setup.key.token(issued_at=NOW.timestamp() - 3600, lifetime=60)

        for token in ("pas.un.jeton", foreign, expired):
            with pytest.raises(UnauthenticatedError):
                setup.use_case.require(token)

        assert {e.event for e in setup.events.events} == {"customer.token_rejected"}


class TestForbidden:
    def test_a_customer_token_is_a_403(self) -> None:
        setup = _Setup()

        with pytest.raises(ForbiddenError):
            setup.use_case.require(setup.token(["customer"], ["pwd", "face"]))

        denied = setup.events.events[-1]
        assert (denied.event, denied.reason) == ("operator.access_denied", "not_operator")

    @pytest.mark.parametrize("amr", [None, [], ["pwd"], ["pwd", "otp"], "face", ["FACE"]])
    def test_an_operator_without_the_face_factor_is_a_403(self, amr: Any) -> None:
        setup = _Setup()
        token = setup.key.token(
            issued_at=NOW.timestamp(),
            extra={"roles": ["operator"], **({} if amr is None else {"amr": amr})},
        )

        with pytest.raises(ForbiddenError):
            setup.use_case.require(token)

        assert setup.events.events[-1].reason == "second_factor_missing"

    def test_roles_that_are_not_a_list_never_grant_access(self) -> None:
        setup = _Setup()
        token = setup.key.token(
            issued_at=NOW.timestamp(), extra={"roles": "operator", "amr": ["face"]}
        )

        with pytest.raises(ForbiddenError):
            setup.use_case.require(token)


class TestKeysUnavailable:
    def test_without_readable_keys_the_answer_is_a_503_not_an_access(self) -> None:
        setup = _Setup()
        setup.jwks.down = True

        with pytest.raises(IdentityUnavailableError):
            setup.use_case.require(setup.token(["operator"], ["face"]))
