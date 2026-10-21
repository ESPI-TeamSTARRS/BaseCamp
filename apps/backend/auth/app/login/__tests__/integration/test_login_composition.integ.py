from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from httpx import ASGITransport, AsyncClient

from app.core.__tests__.in_memory_business_event_logger import InMemoryBusinessEventLogger
from app.core.config import Settings
from app.login.__tests__.fakes import FakeClock, FakeStore, FakeUnitOfWork
from app.login.application.get_current_account import GetCurrentAccountUseCase
from app.login.application.unauthenticated_error import UnauthenticatedError
from app.login.composition import build_key_ring
from app.login.domain.entities.access_token_claims import AccessTokenClaims
from app.login.domain.enums.token_rejection import TokenRejection
from app.login.domain.exceptions.access_token_rejected_error import AccessTokenRejectedError
from app.login.infrastructure.clients.jwt_access_token_signer import JwtAccessTokenSigner
from app.login.infrastructure.clients.jwt_access_token_verifier import JwtAccessTokenVerifier
from app.main import create_app
from app.service_token.domain.entities.token_claims import TokenClaims
from app.service_token.domain.enums.token_use import TokenUse
from app.service_token.infrastructure.clients.ed25519_key_store import Ed25519KeyStore
from app.service_token.infrastructure.clients.jwt_token_decoder import JwtTokenDecoder
from app.service_token.infrastructure.clients.jwt_token_signer import JwtTokenSigner

NOW = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
ISSUER = "basecamp-auth"
CLIENT_AUDIENCE = "basecamp-client-api"


def write_pair(directory: Path, key: Ed25519PrivateKey) -> tuple[Path, Path]:
    private, public = directory / "private.pem", directory / "public.pem"
    private.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    public.write_bytes(
        key.public_key().public_bytes(
            serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
        )
    )
    return private, public


def service_token_for(store: Ed25519KeyStore, audience: str) -> str:
    return JwtTokenSigner(store).sign(
        TokenClaims(
            subject="shop",
            audience=audience,
            scopes=frozenset({"payments:write"}),
            issuer=ISSUER,
            issued_at=int(NOW.timestamp()),
            expires_at=int((NOW + timedelta(minutes=5)).timestamp()),
            token_id="jti-service",
            token_use=TokenUse.SERVICE,
        )
    )


@pytest.fixture
def keys(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path]:
    directory = tmp_path / "keys"
    directory.mkdir()
    private, public = write_pair(directory, Ed25519PrivateKey.generate())
    monkeypatch.setenv("APP_JWT_PRIVATE_KEY_FILE", str(private))
    monkeypatch.setenv("APP_JWT_PUBLIC_KEY_FILE", str(public))
    monkeypatch.delenv("APP_JWT_PREVIOUS_PUBLIC_KEYS_DIR", raising=False)
    return private, public


def key_store() -> Ed25519KeyStore:
    settings = Settings()
    return Ed25519KeyStore(settings.jwt_private_key_file, settings.jwt_public_key_file)


class TestBuildKeyRing:
    def test_missing_secrets_do_not_stop_the_startup_but_fail_on_first_use(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.setenv("APP_JWT_PRIVATE_KEY_FILE", str(tmp_path / "absent.pem"))

        ring = build_key_ring(Settings())

        with pytest.raises(FileNotFoundError):
            ring.public_keys()

    def test_the_mounted_secret_is_shared_with_service_tokens_and_gives_the_same_kid(
        self, keys: tuple[Path, Path]
    ) -> None:
        ring = build_key_ring(Settings())

        assert ring.signing_kid == key_store().key_id
        assert [key.kid for key in ring.public_keys()] == [key_store().key_id]

    def test_previous_public_keys_are_published_after_the_current_one(
        self, keys: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        previous = tmp_path / "previous"
        previous.mkdir()
        _, old_public = write_pair(previous, Ed25519PrivateKey.generate())
        (previous / "private.pem").unlink()
        old_public.rename(previous / "old.pem")
        monkeypatch.setenv("APP_JWT_PREVIOUS_PUBLIC_KEYS_DIR", str(previous))

        assert len(build_key_ring(Settings()).public_keys()) == 2


class TestApplicationWiring:
    async def test_the_real_application_serves_the_only_jwks_and_refuses_anonymous_me(
        self, keys: tuple[Path, Path]
    ) -> None:
        async with AsyncClient(
            transport=ASGITransport(app=create_app()), base_url="http://t"
        ) as client:
            published = (await client.get("/.well-known/jwks.json")).json()["keys"]
            anonymous = await client.get("/me")
            former_route = await client.get("/internal/jwks")

        assert [key["kid"] for key in published] == [key_store().key_id]
        assert anonymous.status_code == 401
        assert former_route.status_code == 404

    async def test_the_service_starts_and_answers_health_without_any_secret(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.setenv("APP_JWT_PRIVATE_KEY_FILE", str(tmp_path / "absent.pem"))
        async with AsyncClient(
            transport=ASGITransport(app=create_app()), base_url="http://t"
        ) as client:
            assert (await client.get("/health")).status_code == 200


class TestClientAndServiceTokensNeverMix:
    """Meme cle, deux sortes de jetons : chacune est refusee par le verificateur de l'autre."""

    def test_a_client_token_is_not_a_service_token(self, keys: tuple[Path, Path]) -> None:
        claims = AccessTokenClaims(uuid4(), ("customer",), True, NOW, NOW + timedelta(hours=1), "j")
        token = JwtAccessTokenSigner(build_key_ring(Settings()), ISSUER, CLIENT_AUDIENCE).sign(
            claims
        )

        decoded = JwtTokenDecoder(key_store()).decode(token)

        assert decoded.token_use is TokenUse.CLIENT
        assert decoded.audience == CLIENT_AUDIENCE
        assert decoded.audience != "payment"

    @pytest.mark.parametrize("audience", ["payment", CLIENT_AUDIENCE])
    def test_a_service_token_is_refused_as_a_client_token(
        self, keys: tuple[Path, Path], audience: str
    ) -> None:
        verifier = JwtAccessTokenVerifier(build_key_ring(Settings()), ISSUER, CLIENT_AUDIENCE)

        with pytest.raises(AccessTokenRejectedError) as raised:
            verifier.verify(service_token_for(key_store(), audience), NOW)

        assert raised.value.rejection is TokenRejection.INVALID

    def test_a_service_token_cannot_open_me(self, keys: tuple[Path, Path]) -> None:
        events = InMemoryBusinessEventLogger()
        clock = FakeClock()
        use_case = GetCurrentAccountUseCase(
            lambda: FakeUnitOfWork(FakeStore()),
            JwtAccessTokenVerifier(build_key_ring(Settings()), ISSUER, CLIENT_AUDIENCE),
            clock,
            events,
        )
        token = service_token_for(key_store(), CLIENT_AUDIENCE)

        with pytest.raises(UnauthenticatedError):
            use_case.execute(token)

        assert [event.reason for event in events.events] == ["invalid"]
