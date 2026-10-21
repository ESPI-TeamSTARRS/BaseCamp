from dataclasses import replace
from datetime import UTC, datetime

import pytest

from app.core.__tests__.in_memory_business_event_logger import InMemoryBusinessEventLogger
from app.core.events.outcome import Outcome
from app.service_token.application.verify_token import VerifyTokenUseCase
from app.service_token.domain.entities.token_claims import TokenClaims
from app.service_token.domain.enums.token_use import TokenUse
from app.service_token.domain.exceptions.invalid_token_error import InvalidTokenError
from app.service_token.domain.interfaces.clock import Clock
from app.service_token.domain.interfaces.token_decoder import TokenDecoder

NOW = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
ISSUED_AT = int(NOW.timestamp())


class FakeDecoder(TokenDecoder):
    def __init__(self, claims: TokenClaims | None) -> None:
        self._claims = claims

    def decode(self, token: str) -> TokenClaims:
        if self._claims is None:
            raise InvalidTokenError
        return self._claims


class FixedClock(Clock):
    def __init__(self, now: datetime = NOW) -> None:
        self._now = now

    def now(self) -> datetime:
        return self._now


def _claims(**overrides: object) -> TokenClaims:
    base = TokenClaims(
        subject="shop",
        audience="payment",
        scopes=frozenset({"payments:write"}),
        issuer="basecamp-auth",
        issued_at=ISSUED_AT,
        expires_at=ISSUED_AT + 300,
        token_id="jti-1",
        token_use=TokenUse.SERVICE,
    )
    return replace(base, **overrides)  # type: ignore[arg-type]


def _verifier(
    claims: TokenClaims | None,
    expected_use: TokenUse = TokenUse.SERVICE,
    now: datetime = NOW,
    events: InMemoryBusinessEventLogger | None = None,
) -> VerifyTokenUseCase:
    return VerifyTokenUseCase(
        FakeDecoder(claims),
        FixedClock(now),
        expected_use,
        "basecamp-auth",
        events or InMemoryBusinessEventLogger(),
    )


class TestAccepts:
    def test_accepts_a_valid_service_token(self) -> None:
        claims = _verifier(_claims()).execute("t", "payment", "payments:write")

        assert claims.subject == "shop"

    def test_scope_is_optional(self) -> None:
        assert _verifier(_claims()).execute("t", "payment").subject == "shop"


class TestRefuses:
    def test_refuses_an_unreadable_or_badly_signed_token(self) -> None:
        with pytest.raises(InvalidTokenError):
            _verifier(None).execute("t", "payment")

    def test_refuses_an_expired_token(self) -> None:
        later = datetime.fromtimestamp(ISSUED_AT + 300, tz=UTC)

        with pytest.raises(InvalidTokenError):
            _verifier(_claims(), now=later).execute("t", "payment")

    def test_refuses_a_token_issued_in_the_future(self) -> None:
        earlier = datetime.fromtimestamp(ISSUED_AT - 60, tz=UTC)

        with pytest.raises(InvalidTokenError):
            _verifier(_claims(), now=earlier).execute("t", "payment")

    def test_refuses_another_issuer(self) -> None:
        with pytest.raises(InvalidTokenError):
            _verifier(_claims(issuer="evil")).execute("t", "payment")

    def test_refuses_another_audience(self) -> None:
        with pytest.raises(InvalidTokenError):
            _verifier(_claims()).execute("t", "shop")

    def test_refuses_a_missing_scope(self) -> None:
        with pytest.raises(InvalidTokenError):
            _verifier(_claims()).execute("t", "payment", "payments:read")


class TestTokenUse:
    def test_a_client_token_is_refused_as_a_service_token(self) -> None:
        client_token = _claims(token_use=TokenUse.CLIENT)

        with pytest.raises(InvalidTokenError):
            _verifier(client_token, TokenUse.SERVICE).execute("t", "payment")

    def test_a_service_token_is_refused_as_a_client_token(self) -> None:
        with pytest.raises(InvalidTokenError):
            _verifier(_claims(), TokenUse.CLIENT).execute("t", "payment")

    def test_a_client_token_is_accepted_by_a_client_verifier(self) -> None:
        client_token = _claims(token_use=TokenUse.CLIENT, audience="shop")

        assert _verifier(client_token, TokenUse.CLIENT).execute("t", "shop").subject == "shop"


class TestBusinessEvents:
    def test_a_refusal_emits_a_denied_event_with_its_reason_and_never_the_token(self) -> None:
        events = InMemoryBusinessEventLogger()

        with pytest.raises(InvalidTokenError):
            _verifier(_claims(token_use=TokenUse.CLIENT), events=events).execute(
                "tok-must-not-leak", "payment"
            )

        [event] = events.events
        assert event.event == "auth.token_verification_denied"
        assert event.outcome is Outcome.DENIED
        assert event.reason == "token_use"
        assert event.resource_type == "service_token"
        assert "tok-must-not-leak" not in repr(event)

    def test_an_accepted_token_emits_nothing(self) -> None:
        events = InMemoryBusinessEventLogger()

        _verifier(_claims(), events=events).execute("t", "payment")

        assert events.events == []
