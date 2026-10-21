import base64
import hashlib
import json
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from app.login.infrastructure.clients.ed25519_key_ring import Ed25519KeyRing


def write_private(path: Path, key: Ed25519PrivateKey) -> None:
    path.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )


def write_public(path: Path, key: Ed25519PrivateKey) -> None:
    path.write_bytes(
        key.public_key().public_bytes(
            serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
        )
    )


def b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


class TestKid:
    def test_the_kid_is_the_rfc7638_thumbprint_of_the_public_key(self) -> None:
        key = Ed25519PrivateKey.generate()
        x = b64(key.public_key().public_bytes_raw())
        canonical = json.dumps({"crv": "Ed25519", "kty": "OKP", "x": x}, separators=(",", ":"))

        ring = Ed25519KeyRing(key)

        assert ring.signing_kid == b64(hashlib.sha256(canonical.encode()).digest())
        assert [(k.kid, k.x) for k in ring.public_keys()] == [(ring.signing_kid, x)]


class TestFromFiles:
    def test_loads_the_private_key_and_previous_public_keys(self, tmp_path: Path) -> None:
        current, previous = Ed25519PrivateKey.generate(), Ed25519PrivateKey.generate()
        write_private(tmp_path / "jwt-private.pem", current)
        previous_dir = tmp_path / "previous"
        previous_dir.mkdir()
        write_public(previous_dir / "2025.pem", previous)
        (previous_dir / "notes.txt").write_text("ignore", encoding="utf-8")

        ring = Ed25519KeyRing.from_files(tmp_path / "jwt-private.pem", previous_dir)

        assert ring.signing_kid == Ed25519KeyRing(current).signing_kid
        assert [k.kid for k in ring.public_keys()] == [
            Ed25519KeyRing(current).signing_kid,
            Ed25519KeyRing(previous).signing_kid,
        ]

    def test_the_previous_directory_is_optional(self, tmp_path: Path) -> None:
        write_private(tmp_path / "jwt-private.pem", Ed25519PrivateKey.generate())

        assert len(Ed25519KeyRing.from_files(tmp_path / "jwt-private.pem", None).public_keys()) == 1

    def test_a_missing_private_key_stops_the_startup(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            Ed25519KeyRing.from_files(tmp_path / "absent.pem", None)

    def test_a_key_of_another_type_is_refused_without_echoing_its_content(
        self, tmp_path: Path
    ) -> None:
        (tmp_path / "bad.pem").write_text("-----BEGIN NOT A KEY-----", encoding="utf-8")

        with pytest.raises(ValueError, match="Ed25519") as raised:
            Ed25519KeyRing.from_files(tmp_path / "bad.pem", None)

        assert "BEGIN" not in str(raised.value)

    def test_the_ring_never_shows_the_private_key(self) -> None:
        key = Ed25519PrivateKey.generate()
        secret = b64(key.private_bytes_raw())

        ring = Ed25519KeyRing(key)

        assert secret not in repr(ring)
