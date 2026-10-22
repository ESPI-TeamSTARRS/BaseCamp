import os
from uuid import UUID

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.backoffice.domain.exceptions.gabarit_invalide import GabaritInvalide
from app.backoffice.domain.interfaces.template_cipher import TemplateCipher

KEY_BYTES = 32  # AES-256
NONCE_BYTES = 12
FORMAT_VERSION = b"\x01"


class AesGcmTemplateCipher(TemplateCipher):
    """AES-256-GCM : `version (1 octet) | nonce (12 octets) | chiffre + etiquette`.

    L'identifiant du compte est une donnee authentifiee : le chiffre ne se dechiffre que pour ce
    compte. Un nonce neuf par chiffrement. La cle vient de l'environnement (secret monte), jamais du depot.
    """

    def __init__(self, key: bytes) -> None:
        if len(key) != KEY_BYTES:
            raise ValueError("face template key must be 32 bytes")
        self._aead = AESGCM(key)

    def encrypt(self, account_id: UUID, template: bytes) -> bytes:
        nonce = os.urandom(NONCE_BYTES)
        return FORMAT_VERSION + nonce + self._aead.encrypt(nonce, template, account_id.bytes)

    def decrypt(self, account_id: UUID, stored: bytes) -> bytes:
        header = len(FORMAT_VERSION) + NONCE_BYTES
        if len(stored) <= header or stored[: len(FORMAT_VERSION)] != FORMAT_VERSION:
            raise GabaritInvalide
        nonce = stored[len(FORMAT_VERSION) : header]
        try:
            return self._aead.decrypt(nonce, stored[header:], account_id.bytes)
        except InvalidTag:
            raise GabaritInvalide from None
