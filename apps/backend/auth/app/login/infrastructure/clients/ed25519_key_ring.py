import base64
import hashlib
import json
from collections.abc import Sequence
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

from app.login.domain.entities.public_key import PublicKey
from app.login.domain.interfaces.public_key_set import PublicKeySet

KEY_ERROR = "Key must be an Ed25519 key in PEM format"


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def _public_key(key: Ed25519PublicKey) -> PublicKey:
    """`kid` = empreinte RFC 7638 de la cle publique : stable, sans table a maintenir."""
    x = _b64url(key.public_bytes_raw())
    canonical = json.dumps({"crv": "Ed25519", "kty": "OKP", "x": x}, separators=(",", ":"))
    return PublicKey(_b64url(hashlib.sha256(canonical.encode()).digest()), x)


class Ed25519KeyRing(PublicKeySet):
    """Cle de signature courante et cles precedentes (verification seule) pendant une rotation.

    La cle privee n'est jamais affichee ni journalisee : `repr` ne donne que le `kid`.
    """

    def __init__(
        self,
        signing_key: Ed25519PrivateKey,
        previous_public_keys: Sequence[Ed25519PublicKey] = (),
    ) -> None:
        self._signing_key = signing_key
        self._current = _public_key(signing_key.public_key())
        self._verification: dict[str, Ed25519PublicKey] = {
            self._current.kid: signing_key.public_key()
        }
        self._order = [self._current]
        for key in previous_public_keys:
            published = _public_key(key)
            if published.kid not in self._verification:
                self._verification[published.kid] = key
                self._order.append(published)

    @classmethod
    def generate(cls) -> "Ed25519KeyRing":
        """Cle ephemere, reservee au developpement et aux tests (rien n'est persiste)."""
        return cls(Ed25519PrivateKey.generate())

    @classmethod
    def from_files(cls, private_key_path: Path, previous_keys_dir: Path | None) -> "Ed25519KeyRing":
        private = cls._load_private(private_key_path)
        previous = [] if previous_keys_dir is None else cls._load_previous(previous_keys_dir)
        return cls(private, previous)

    @staticmethod
    def _load_private(path: Path) -> Ed25519PrivateKey:
        try:
            key = serialization.load_pem_private_key(path.read_bytes(), password=None)
        except ValueError:
            raise ValueError(KEY_ERROR) from None
        if not isinstance(key, Ed25519PrivateKey):
            raise ValueError(KEY_ERROR)
        return key

    @staticmethod
    def _load_previous(directory: Path) -> list[Ed25519PublicKey]:
        keys: list[Ed25519PublicKey] = []
        for path in sorted(directory.glob("*.pem")):
            try:
                key = serialization.load_pem_public_key(path.read_bytes())
            except ValueError:
                raise ValueError(KEY_ERROR) from None
            if not isinstance(key, Ed25519PublicKey):
                raise ValueError(KEY_ERROR)
            keys.append(key)
        return keys

    @property
    def signing_kid(self) -> str:
        return self._current.kid

    @property
    def signing_key(self) -> Ed25519PrivateKey:
        return self._signing_key

    @property
    def signing_public_key(self) -> Ed25519PublicKey:
        return self._signing_key.public_key()

    def verification_key(self, kid: str) -> Ed25519PublicKey | None:
        return self._verification.get(kid)

    def public_keys(self) -> tuple[PublicKey, ...]:
        return tuple(self._order)

    def __repr__(self) -> str:
        return f"Ed25519KeyRing(kid={self.signing_kid!r}, keys={len(self._order)})"
