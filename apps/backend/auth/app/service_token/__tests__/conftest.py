from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    NoEncryption,
    PrivateFormat,
    PublicFormat,
)


def write_ed25519_pair(directory: Path) -> tuple[str, str]:
    """Génère une paire Ed25519 jetable pour les tests (jamais une vraie clé de service)."""
    private_key = Ed25519PrivateKey.generate()
    private_path = directory / "private.pem"
    public_path = directory / "public.pem"
    private_path.write_bytes(
        private_key.private_bytes(Encoding.PEM, PrivateFormat.PKCS8, NoEncryption())
    )
    public_path.write_bytes(
        private_key.public_key().public_bytes(Encoding.PEM, PublicFormat.SubjectPublicKeyInfo)
    )
    return str(private_path), str(public_path)


@pytest.fixture
def signing_keys(tmp_path: Path) -> tuple[str, str]:
    directory = tmp_path / "keys"
    directory.mkdir()
    return write_ed25519_pair(directory)


@pytest.fixture
def other_signing_keys(tmp_path: Path) -> tuple[str, str]:
    directory = tmp_path / "other-keys"
    directory.mkdir()
    return write_ed25519_pair(directory)
