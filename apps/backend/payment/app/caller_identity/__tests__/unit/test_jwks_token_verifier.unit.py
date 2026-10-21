import time
from datetime import UTC, datetime

import pytest

from app.caller_identity.__tests__.tokens import ISSUER, KEY, SigningKey, StaticJwks
from app.caller_identity.domain.enums.token_kind import TokenKind
from app.caller_identity.domain.exceptions.token_rejected_error import (
    TokenRejectedError,
    TokenRejection,
)
from app.caller_identity.domain.exceptions.verification_keys_unavailable_error import (
    VerificationKeysUnavailableError,
)
from app.caller_identity.infrastructure.clients.jwks_key_cache import JwksKeyCache
from app.caller_identity.infrastructure.clients.jwks_token_verifier import JwksTokenVerifier

NOW = datetime.now(UTC)


def _verifier(*keys: SigningKey, source: StaticJwks | None = None) -> JwksTokenVerifier:
    cache = JwksKeyCache(source or StaticJwks(*keys), time.monotonic, 300, 10)
    return JwksTokenVerifier(cache, ISSUER, "payment", "basecamp-client-api")


def _rejection(token: str, verifier: JwksTokenVerifier | None = None) -> TokenRejection:
    with pytest.raises(TokenRejectedError) as raised:
        (verifier or _verifier(KEY)).verify(token, NOW)
    return raised.value.rejection


class TestAcceptedTokens:
    def test_a_service_token_gives_its_subject_and_scopes(self) -> None:
        caller = _verifier(KEY).verify(
            KEY.token(sub="shop", scope="payments:write refunds:write"), NOW
        )

        assert (caller.subject, caller.kind) == ("shop", TokenKind.SERVICE)
        assert caller.scopes == {"payments:write", "refunds:write"}

    def test_a_client_token_gives_its_roles(self) -> None:
        token = KEY.token(sub="op-1", use="client", roles=["operator"])

        caller = _verifier(KEY).verify(token, NOW)

        assert (caller.subject, caller.kind, caller.roles) == (
            "op-1",
            TokenKind.CLIENT,
            frozenset({"operator"}),
        )

    def test_a_token_just_expired_is_still_accepted_within_the_clock_tolerance(self) -> None:
        token = KEY.token(issued_at=time.time() - 100, lifetime=90)

        assert _verifier(KEY).verify(token, NOW).subject == "shop"


class TestRefusedTokens:
    def test_an_expired_token(self) -> None:
        token = KEY.token(issued_at=time.time() - 3600, lifetime=60)

        assert _rejection(token) is TokenRejection.EXPIRED

    def test_a_token_signed_by_an_unknown_key_with_a_known_kid(self) -> None:
        forged = SigningKey(KEY.kid).token()

        assert _rejection(forged) is TokenRejection.INVALID

    def test_a_token_with_an_unknown_kid(self) -> None:
        assert _rejection(SigningKey("other").token()) is TokenRejection.UNKNOWN_KEY

    def test_a_token_without_kid(self) -> None:
        token = KEY.token(headers={"kid": ""})

        assert _rejection(token) is TokenRejection.MISSING_KEY_ID

    def test_the_none_algorithm(self) -> None:
        header = "eyJhbGciOiJub25lIiwia2lkIjoia2lkLTEifQ"
        body = KEY.token().split(".")[1]

        assert _rejection(f"{header}.{body}.") is TokenRejection.BAD_ALGORITHM

    def test_a_wrong_audience(self) -> None:
        assert _rejection(KEY.token(audience="shop")) is TokenRejection.WRONG_AUDIENCE

    def test_a_wrong_issuer(self) -> None:
        assert _rejection(KEY.token(issuer="evil")) is TokenRejection.WRONG_ISSUER

    def test_a_client_token_carrying_the_service_audience(self) -> None:
        token = KEY.token(use="client", audience="payment")

        assert _rejection(token) is TokenRejection.WRONG_AUDIENCE

    def test_a_service_token_carrying_the_client_audience(self) -> None:
        token = KEY.token(use="service", audience="basecamp-client-api")

        assert _rejection(token) is TokenRejection.WRONG_AUDIENCE

    def test_an_unknown_token_use(self) -> None:
        assert _rejection(KEY.token(use="other")) is TokenRejection.WRONG_TOKEN_USE

    @pytest.mark.parametrize("claim", ["exp", "iat", "sub", "jti", "token_use", "iss", "aud"])
    def test_a_token_missing_a_required_claim(self, claim: str) -> None:
        assert _rejection(KEY.token(drop=(claim,))) is TokenRejection.INVALID

    @pytest.mark.parametrize("garbage", ["", "abc", "a.b", "a.b.c", "eyJ.eyJ.x", "....."])
    def test_garbage(self, garbage: str) -> None:
        assert _rejection(garbage) in {TokenRejection.INVALID, TokenRejection.MISSING_KEY_ID}


class TestKeysUnavailable:
    def test_no_key_ever_read_is_reported_as_unavailable(self) -> None:
        source = StaticJwks(KEY)
        source.down = True

        with pytest.raises(VerificationKeysUnavailableError):
            _verifier(source=source).verify(KEY.token(), NOW)

    def test_keys_already_read_keep_working_when_auth_goes_down(self) -> None:
        source = StaticJwks(KEY)
        verifier = _verifier(source=source)
        verifier.verify(KEY.token(), NOW)

        source.down = True

        assert verifier.verify(KEY.token(), NOW).subject == "shop"
