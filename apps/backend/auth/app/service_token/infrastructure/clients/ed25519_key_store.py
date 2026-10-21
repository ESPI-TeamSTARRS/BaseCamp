import base64
import hashlib
import json
from functools import cached_property
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    PublicFormat,
    load_pem_public_key,
)

from app.service_token.domain.entities.public_jwk import PublicJwk
from app.service_token.domain.interfaces.signing_key_directory import SigningKeyDirectory


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


class Ed25519KeyStore(SigningKeyDirectory):
    """Paire de clés Ed25519 montée en secrets Docker, lue paresseusement (au premier usage).

    Seuls les chemins sont conservés : la clé privée n'est jamais journalisée ni exposée, et
    l'identifiant `kid` est l'empreinte RFC 7638 de la clé publique.
    """

    def __init__(self, private_key_path: str, public_key_path: str) -> None:
        self._private_key_path = Path(private_key_path)
        self._public_key_path = Path(public_key_path)

    @cached_property
    def private_key_pem(self) -> bytes:
        return self._private_key_path.read_bytes()

    @cached_property
    def public_key_pem(self) -> bytes:
        return self._public_key_path.read_bytes()

    @cached_property
    def _public_x(self) -> str:
        public_key = load_pem_public_key(self.public_key_pem)
        if not isinstance(public_key, Ed25519PublicKey):
            raise TypeError("the signing public key must be an Ed25519 key")
        raw = public_key.public_bytes(Encoding.Raw, PublicFormat.Raw)
        return _b64url(raw)

    @cached_property
    def key_id(self) -> str:
        members = {"crv": "Ed25519", "kty": "OKP", "x": self._public_x}
        canonical = json.dumps(members, separators=(",", ":"), sort_keys=True).encode("ascii")
        return _b64url(hashlib.sha256(canonical).digest())

    def public_jwk(self) -> PublicJwk:
        return PublicJwk(key_id=self.key_id, x=self._public_x)
