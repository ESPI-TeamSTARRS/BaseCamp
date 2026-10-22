import base64
import binascii
from pathlib import Path

from app.backoffice.infrastructure.clients.aes_gcm_template_cipher import (
    KEY_BYTES,
    AesGcmTemplateCipher,
)


def load_template_cipher(path: str) -> AesGcmTemplateCipher:
    """Lit la cle (32 octets en base64) du secret monte; echoue vite si elle manque ou est mauvaise.

    Le contenu de la cle n'apparait jamais dans un message d'erreur.
    """
    try:
        raw = Path(path).read_text(encoding="ascii").strip()
    except (OSError, UnicodeError):
        raise ValueError("face template key file is missing or unreadable") from None
    try:
        key = base64.b64decode(raw, validate=True)
    except (binascii.Error, ValueError):
        raise ValueError("face template key must be base64") from None
    if len(key) != KEY_BYTES:
        raise ValueError("face template key must be 32 bytes")
    return AesGcmTemplateCipher(key)
