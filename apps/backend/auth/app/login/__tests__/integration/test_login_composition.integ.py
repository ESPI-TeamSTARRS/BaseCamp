from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from httpx import ASGITransport, AsyncClient

from app.core.config import Settings
from app.login.composition import build_key_ring
from app.main import create_app


def write_private(path: Path, key: Ed25519PrivateKey) -> None:
    path.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )


class TestBuildKeyRing:
    def test_without_a_key_file_dev_gets_an_ephemeral_key(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("APP_JWT_PRIVATE_KEY_FILE", raising=False)

        first, second = build_key_ring(Settings()), build_key_ring(Settings())

        assert first.signing_kid != second.signing_kid

    def test_the_mounted_secret_is_the_signing_key(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        key = Ed25519PrivateKey.generate()
        write_private(tmp_path / "private.pem", key)
        monkeypatch.setenv("APP_JWT_PRIVATE_KEY_FILE", str(tmp_path / "private.pem"))
        monkeypatch.delenv("APP_JWT_PREVIOUS_PUBLIC_KEYS_DIR", raising=False)

        ring = build_key_ring(Settings())

        assert [k.kid for k in ring.public_keys()] == [ring.signing_kid]
        assert ring.signing_public_key.public_bytes_raw() == key.public_key().public_bytes_raw()

    def test_previous_public_keys_are_published_after_the_current_one(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        write_private(tmp_path / "private.pem", Ed25519PrivateKey.generate())
        previous = tmp_path / "previous"
        previous.mkdir()
        (previous / "old.pem").write_bytes(
            Ed25519PrivateKey.generate()
            .public_key()
            .public_bytes(
                serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
            )
        )
        monkeypatch.setenv("APP_JWT_PRIVATE_KEY_FILE", str(tmp_path / "private.pem"))
        monkeypatch.setenv("APP_JWT_PREVIOUS_PUBLIC_KEYS_DIR", str(previous))

        assert len(build_key_ring(Settings()).public_keys()) == 2


class TestApplicationWiring:
    async def test_the_real_application_serves_the_jwks_and_refuses_anonymous_me(self) -> None:
        async with AsyncClient(
            transport=ASGITransport(app=create_app()), base_url="http://t"
        ) as client:
            keys = (await client.get("/.well-known/jwks.json")).json()["keys"]
            anonymous = await client.get("/me")

        assert len(keys) == 1
        assert keys[0]["kty"] == "OKP"
        assert anonymous.status_code == 401
