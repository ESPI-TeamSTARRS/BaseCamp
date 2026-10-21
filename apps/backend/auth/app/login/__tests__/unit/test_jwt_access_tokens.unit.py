"""Signature et verification des jetons d'acces : claims publies et vecteurs d'attaque."""

import base64
import json
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

import jwt
import pytest

from app.login.domain.entities.access_token_claims import AccessTokenClaims
from app.login.domain.enums.token_rejection import TokenRejection
from app.login.domain.exceptions.access_token_rejected_error import AccessTokenRejectedError
from app.login.infrastructure.clients.ed25519_key_ring import Ed25519KeyRing
from app.login.infrastructure.clients.jwt_access_token_signer import JwtAccessTokenSigner
from app.login.infrastructure.clients.jwt_access_token_verifier import JwtAccessTokenVerifier

ISSUER = "basecamp-auth"
AUDIENCE = "basecamp-client-api"
NOW = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)


def claims(
    issued_at: datetime = NOW, ttl: timedelta = timedelta(minutes=15), roles: tuple[str, ...] = ()
) -> AccessTokenClaims:
    return AccessTokenClaims(
        uuid4(), roles or ("customer",), True, issued_at, issued_at + ttl, str(uuid4())
    )


def signer(ring: Ed25519KeyRing, audience: str = AUDIENCE) -> JwtAccessTokenSigner:
    return JwtAccessTokenSigner(ring, ISSUER, audience)


def verifier(ring: Ed25519KeyRing, audience: str = AUDIENCE) -> JwtAccessTokenVerifier:
    return JwtAccessTokenVerifier(ring, ISSUER, audience)


def b64(data: dict[str, Any]) -> str:
    raw = json.dumps(data, separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def payload_of(token: str) -> dict[str, Any]:
    decoded: dict[str, Any] = jwt.decode(token, options={"verify_signature": False})
    return decoded


def rejection_of(verify: JwtAccessTokenVerifier, token: str, now: datetime = NOW) -> TokenRejection:
    with pytest.raises(AccessTokenRejectedError) as raised:
        verify.verify(token, now)
    return raised.value.rejection


@pytest.fixture
def ring() -> Ed25519KeyRing:
    return Ed25519KeyRing.generate()


class TestPublishedClaims:
    def test_the_token_carries_the_documented_claims(self, ring: Ed25519KeyRing) -> None:
        subject = claims(roles=("operator",))

        token = signer(ring).sign(subject)

        payload = payload_of(token)
        assert set(payload) == {
            "iss",
            "aud",
            "sub",
            "roles",
            "email_verified",
            "token_use",
            "iat",
            "exp",
            "jti",
        }
        assert payload["iss"] == ISSUER
        assert payload["aud"] == AUDIENCE
        assert payload["sub"] == str(subject.subject)
        assert payload["roles"] == ["operator"]
        assert payload["email_verified"] is True
        assert payload["token_use"] == "client"
        assert payload["jti"] == subject.token_id
        assert payload["exp"] - payload["iat"] == 900

    def test_the_header_names_the_algorithm_and_the_signing_key(self, ring: Ed25519KeyRing) -> None:
        header = jwt.get_unverified_header(signer(ring).sign(claims()))

        assert header["alg"] == "EdDSA"
        assert header["kid"] == ring.signing_kid
        assert header["typ"] == "JWT"

    def test_a_valid_token_round_trips(self, ring: Ed25519KeyRing) -> None:
        subject = claims(roles=("customer", "operator"))

        verified = verifier(ring).verify(signer(ring).sign(subject), NOW)

        assert verified == subject


class TestRejectedTokens:
    def test_an_expired_token_is_expired(self, ring: Ed25519KeyRing) -> None:
        token = signer(ring).sign(claims())

        assert rejection_of(verifier(ring), token, NOW + timedelta(minutes=15)) is (
            TokenRejection.EXPIRED
        )

    def test_a_token_is_still_valid_one_second_before_expiry(self, ring: Ed25519KeyRing) -> None:
        token = signer(ring).sign(claims())

        verifier(ring).verify(token, NOW + timedelta(minutes=15, seconds=-1))

    def test_a_tampered_payload_is_invalid(self, ring: Ed25519KeyRing) -> None:
        header, _, signature = signer(ring).sign(claims()).split(".")
        forged = b64({**payload_of(signer(ring).sign(claims())), "roles": ["operator"]})

        assert rejection_of(verifier(ring), f"{header}.{forged}.{signature}") is (
            TokenRejection.INVALID
        )

    def test_a_token_without_signature_alg_none_is_invalid(self, ring: Ed25519KeyRing) -> None:
        payload = payload_of(signer(ring).sign(claims()))
        header = b64({"alg": "none", "typ": "JWT", "kid": ring.signing_kid})

        assert rejection_of(verifier(ring), f"{header}.{b64(payload)}.") is TokenRejection.INVALID

    def test_a_token_with_another_audience_is_invalid(self, ring: Ed25519KeyRing) -> None:
        token = signer(ring, audience="autre-service").sign(claims())

        assert rejection_of(verifier(ring), token) is TokenRejection.INVALID

    def test_a_token_with_another_issuer_is_invalid(self, ring: Ed25519KeyRing) -> None:
        token = JwtAccessTokenSigner(ring, "autre-emetteur", AUDIENCE).sign(claims())

        assert rejection_of(verifier(ring), token) is TokenRejection.INVALID

    def test_a_token_signed_by_an_unknown_key_is_invalid(self, ring: Ed25519KeyRing) -> None:
        token = signer(Ed25519KeyRing.generate()).sign(claims())

        assert rejection_of(verifier(ring), token) is TokenRejection.INVALID

    def test_a_token_claiming_a_known_kid_but_signed_by_another_key_is_invalid(
        self, ring: Ed25519KeyRing
    ) -> None:
        forged = jwt.encode(
            payload_of(signer(ring).sign(claims())),
            Ed25519KeyRing.generate().signing_key,
            algorithm="EdDSA",
            headers={"kid": ring.signing_kid},
        )

        assert rejection_of(verifier(ring), forged) is TokenRejection.INVALID

    def test_a_token_that_is_not_an_access_token_is_invalid(self, ring: Ed25519KeyRing) -> None:
        payload = {**payload_of(signer(ring).sign(claims())), "token_use": "service"}
        token = jwt.encode(
            payload, ring.signing_key, algorithm="EdDSA", headers={"kid": ring.signing_kid}
        )

        assert rejection_of(verifier(ring), token) is TokenRejection.INVALID

    def test_a_symmetric_algorithm_cannot_be_used_to_forge_a_token(
        self, ring: Ed25519KeyRing
    ) -> None:
        payload = payload_of(signer(ring).sign(claims()))
        forged = jwt.encode(payload, "x" * 64, algorithm="HS256", headers={"kid": ring.signing_kid})

        assert rejection_of(verifier(ring), forged) is TokenRejection.INVALID

    @pytest.mark.parametrize("missing", ["jti", "sub", "exp", "roles", "token_use", "iat"])
    def test_a_token_missing_a_claim_is_invalid(self, ring: Ed25519KeyRing, missing: str) -> None:
        payload = payload_of(signer(ring).sign(claims()))
        del payload[missing]
        token = jwt.encode(
            payload, ring.signing_key, algorithm="EdDSA", headers={"kid": ring.signing_kid}
        )

        assert rejection_of(verifier(ring), token) is TokenRejection.INVALID

    def test_a_token_without_kid_is_invalid(self, ring: Ed25519KeyRing) -> None:
        payload = payload_of(signer(ring).sign(claims()))
        token = jwt.encode(payload, ring.signing_key, algorithm="EdDSA")

        assert rejection_of(verifier(ring), token) is TokenRejection.INVALID

    @pytest.mark.parametrize(
        "garbage", ["", "abc", "a.b.c", "....", "x" * 5000, "é.é.é", " Bearer x"]
    )
    def test_garbage_is_invalid(self, ring: Ed25519KeyRing, garbage: str) -> None:
        assert rejection_of(verifier(ring), garbage) is TokenRejection.INVALID

    def test_a_malformed_subject_is_invalid(self, ring: Ed25519KeyRing) -> None:
        payload = {**payload_of(signer(ring).sign(claims())), "sub": "pas-un-uuid"}
        token = jwt.encode(
            payload, ring.signing_key, algorithm="EdDSA", headers={"kid": ring.signing_kid}
        )

        assert rejection_of(verifier(ring), token) is TokenRejection.INVALID


class TestKeyRotation:
    def test_tokens_of_the_previous_key_stay_valid_until_they_expire(self) -> None:
        old = Ed25519KeyRing.generate()
        old_token = signer(old).sign(claims())
        new = Ed25519KeyRing(Ed25519KeyRing.generate().signing_key, [old.signing_public_key])

        assert new.signing_kid != old.signing_kid
        assert verifier(new).verify(old_token, NOW).token_id
        assert (
            rejection_of(verifier(new), old_token, NOW + timedelta(minutes=15))
            is TokenRejection.EXPIRED
        )

    def test_new_tokens_are_signed_with_the_new_key_and_both_keys_are_published(self) -> None:
        old = Ed25519KeyRing.generate()
        new = Ed25519KeyRing(Ed25519KeyRing.generate().signing_key, [old.signing_public_key])

        token = signer(new).sign(claims())

        assert jwt.get_unverified_header(token)["kid"] == new.signing_kid
        assert [key.kid for key in new.public_keys()] == [new.signing_kid, old.signing_kid]
        assert verifier(new).verify(token, NOW)

    def test_once_the_old_key_is_retired_its_tokens_are_refused(self) -> None:
        old = Ed25519KeyRing.generate()
        old_token = signer(old).sign(claims())
        new = Ed25519KeyRing.generate()

        assert rejection_of(verifier(new), old_token) is TokenRejection.INVALID
