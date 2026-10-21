import base64
import hashlib
import hmac
import json
from datetime import UTC, datetime
from pathlib import Path

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from app.core.__tests__.in_memory_business_event_logger import InMemoryBusinessEventLogger
from app.service_token.application.verify_token import VerifyTokenUseCase
from app.service_token.domain.entities.token_claims import TokenClaims
from app.service_token.domain.enums.token_use import TokenUse
from app.service_token.domain.exceptions.invalid_token_error import InvalidTokenError
from app.service_token.domain.interfaces.clock import Clock
from app.service_token.infrastructure.clients.ed25519_key_store import Ed25519KeyStore
from app.service_token.infrastructure.clients.jwt_token_decoder import JwtTokenDecoder
from app.service_token.infrastructure.clients.jwt_token_signer import JwtTokenSigner

NOW = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
ISSUED_AT = int(NOW.timestamp())


class FixedClock(Clock):
    def now(self) -> datetime:
        return NOW


def _claims(token_use: TokenUse = TokenUse.SERVICE, audience: str = "payment") -> TokenClaims:
    return TokenClaims(
        subject="shop",
        audience=audience,
        scopes=frozenset({"payments:write"}),
        issuer="basecamp-auth",
        issued_at=ISSUED_AT,
        expires_at=ISSUED_AT + 300,
        token_id="jti-1",
        token_use=token_use,
    )


def _payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "iss": "basecamp-auth",
        "sub": "shop",
        "aud": "payment",
        "scope": "payments:write",
        "iat": ISSUED_AT,
        "exp": ISSUED_AT + 300,
        "jti": "jti-1",
        "token_use": "service",
    }
    payload.update(overrides)
    return payload


def _verifier(keys: tuple[str, str], use: TokenUse) -> VerifyTokenUseCase:
    decoder = JwtTokenDecoder(Ed25519KeyStore(*keys))
    return VerifyTokenUseCase(
        decoder, FixedClock(), use, "basecamp-auth", InMemoryBusinessEventLogger()
    )


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _hmac_token(payload: dict[str, object], key: bytes) -> str:
    """Jeton HS256 construit a la main (PyJWT refuse de signer en HMAC avec une cle PEM)."""
    header = _b64(json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
    body = _b64(json.dumps(payload).encode())
    signature = hmac.new(key, f"{header}.{body}".encode(), hashlib.sha256).digest()
    return f"{header}.{body}.{_b64(signature)}"


def _forge(keys: tuple[str, str], payload: dict[str, object], algorithm: str = "EdDSA") -> str:
    key_store = Ed25519KeyStore(*keys)
    return jwt.encode(payload, key_store.private_key_pem, algorithm=algorithm)


class TestSignedToken:
    def test_a_signed_token_has_the_documented_header_and_claims(
        self, signing_keys: tuple[str, str]
    ) -> None:
        key_store = Ed25519KeyStore(*signing_keys)

        token = JwtTokenSigner(key_store).sign(_claims())

        header = jwt.get_unverified_header(token)
        assert header["alg"] == "EdDSA"
        assert header["kid"] == key_store.key_id
        payload = jwt.decode(
            token,
            key_store.public_key_pem,
            algorithms=["EdDSA"],
            options={"verify_exp": False, "verify_aud": False, "verify_iat": False},
        )
        assert payload == _payload()

    def test_a_signed_token_round_trips_through_the_verifier(
        self, signing_keys: tuple[str, str]
    ) -> None:
        token = JwtTokenSigner(Ed25519KeyStore(*signing_keys)).sign(_claims())

        claims = _verifier(signing_keys, TokenUse.SERVICE).execute(
            token, "payment", "payments:write"
        )

        assert claims == _claims()


class TestSignatureChecks:
    def test_a_token_signed_by_another_key_is_refused(
        self, signing_keys: tuple[str, str], other_signing_keys: tuple[str, str]
    ) -> None:
        forged = _forge(other_signing_keys, _payload())

        with pytest.raises(InvalidTokenError):
            _verifier(signing_keys, TokenUse.SERVICE).execute(forged, "payment")

    def test_a_tampered_payload_is_refused(self, signing_keys: tuple[str, str]) -> None:
        token = JwtTokenSigner(Ed25519KeyStore(*signing_keys)).sign(_claims())
        header, _, signature = token.split(".")
        body = json.dumps(_payload(sub="admin")).encode()
        tampered = ".".join(
            [header, base64.urlsafe_b64encode(body).rstrip(b"=").decode(), signature]
        )

        with pytest.raises(InvalidTokenError):
            _verifier(signing_keys, TokenUse.SERVICE).execute(tampered, "payment")

    def test_the_none_algorithm_is_refused(self, signing_keys: tuple[str, str]) -> None:
        unsigned = jwt.encode(_payload(), "", algorithm="none")

        with pytest.raises(InvalidTokenError):
            _verifier(signing_keys, TokenUse.SERVICE).execute(unsigned, "payment")

    def test_an_hmac_token_keyed_with_the_public_key_is_refused(
        self, signing_keys: tuple[str, str]
    ) -> None:
        public_pem = Ed25519KeyStore(*signing_keys).public_key_pem
        confused = _hmac_token(_payload(), public_pem)

        with pytest.raises(InvalidTokenError):
            _verifier(signing_keys, TokenUse.SERVICE).execute(confused, "payment")

    @pytest.mark.parametrize("missing", ["exp", "iat", "iss", "sub", "aud", "jti", "token_use"])
    def test_a_token_missing_a_required_claim_is_refused(
        self, signing_keys: tuple[str, str], missing: str
    ) -> None:
        payload = _payload()
        del payload[missing]

        with pytest.raises(InvalidTokenError):
            _verifier(signing_keys, TokenUse.SERVICE).execute(
                _forge(signing_keys, payload), "payment"
            )

    @pytest.mark.parametrize(
        "overrides",
        [{"token_use": "admin"}, {"aud": ["payment", "shop"]}, {"exp": "tomorrow"}],
    )
    def test_malformed_claim_values_are_refused(
        self, signing_keys: tuple[str, str], overrides: dict[str, object]
    ) -> None:
        forged = _forge(signing_keys, _payload(**overrides))

        with pytest.raises(InvalidTokenError):
            _verifier(signing_keys, TokenUse.SERVICE).execute(forged, "payment")

    @pytest.mark.parametrize("garbage", ["", "abc", "a.b.c", "eyJ.eyJ.sig"])
    def test_garbage_is_refused(self, signing_keys: tuple[str, str], garbage: str) -> None:
        with pytest.raises(InvalidTokenError):
            _verifier(signing_keys, TokenUse.SERVICE).execute(garbage, "payment")


class TestCrossUseRefusal:
    def test_a_forged_client_token_signed_by_the_same_key_is_refused_as_service_token(
        self, signing_keys: tuple[str, str]
    ) -> None:
        client_token = _forge(signing_keys, _payload(token_use="client", aud="shop"))

        with pytest.raises(InvalidTokenError):
            _verifier(signing_keys, TokenUse.SERVICE).execute(client_token, "shop")

    def test_a_client_token_claiming_the_payment_audience_is_still_refused_as_service_token(
        self, signing_keys: tuple[str, str]
    ) -> None:
        client_token = _forge(signing_keys, _payload(token_use="client"))

        with pytest.raises(InvalidTokenError):
            _verifier(signing_keys, TokenUse.SERVICE).execute(client_token, "payment")

    def test_a_service_token_is_refused_as_client_token(
        self, signing_keys: tuple[str, str]
    ) -> None:
        service_token = JwtTokenSigner(Ed25519KeyStore(*signing_keys)).sign(_claims())

        with pytest.raises(InvalidTokenError):
            _verifier(signing_keys, TokenUse.CLIENT).execute(service_token, "payment")

    def test_a_client_token_is_accepted_by_the_client_verifier(
        self, signing_keys: tuple[str, str]
    ) -> None:
        client_token = JwtTokenSigner(Ed25519KeyStore(*signing_keys)).sign(
            _claims(TokenUse.CLIENT, audience="shop")
        )

        claims = _verifier(signing_keys, TokenUse.CLIENT).execute(client_token, "shop")

        assert claims.token_use is TokenUse.CLIENT


class TestKeyStore:
    def test_publishes_a_public_okp_jwk_with_a_stable_thumbprint_kid(
        self, signing_keys: tuple[str, str]
    ) -> None:
        first = Ed25519KeyStore(*signing_keys).public_jwk()
        second = Ed25519KeyStore(*signing_keys).public_jwk()

        assert first == second
        assert first.key_id
        assert len(base64.urlsafe_b64decode(first.x + "=")) == 32

    def test_rejects_a_non_ed25519_public_key(
        self, signing_keys: tuple[str, str], tmp_path: Path
    ) -> None:
        rsa_public = (
            rsa.generate_private_key(65537, 2048)
            .public_key()
            .public_bytes(Encoding.PEM, PublicFormat.SubjectPublicKeyInfo)
        )
        path = tmp_path / "rsa.pem"
        path.write_bytes(rsa_public)

        with pytest.raises(TypeError):
            Ed25519KeyStore(signing_keys[0], str(path)).public_jwk()
