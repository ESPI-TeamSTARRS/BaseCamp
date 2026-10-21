import logging
import re
from collections.abc import Iterable

REDACTED = "[REDACTED]"
MIN_SECRET_LENGTH = 8  # en dessous, un « secret » masquerait des mots courants

_BEARER = re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]+")
# 13 à 19 chiffres, séparés ou non par des espaces ou des tirets : numéros de carte.
_CARD = re.compile(r"(?<![\w-])(?:\d[ -]?){12,18}\d(?![\w-])")
_SENSITIVE_KEY = (
    r"(?:password|passwd|secret|token|api[_-]?key|authorization|card[_-]?number|pan|cvv|cvc)"
)
# "cle": "valeur", cle=valeur, 'cle': 'valeur'
_KEY_VALUE = re.compile(
    rf"(?i)([\"']?{_SENSITIVE_KEY}[\"']?\s*[:=]\s*)(\"[^\"]*\"|'[^']*'|[^\s,;}}&]+)"
)


class SecretRedactionFilter(logging.Filter):
    """Masque jetons, secrets connus, numéros de carte et valeurs sensibles dans tout log.

    Posé sur les handlers : il couvre aussi les journaux d'uvicorn et des bibliothèques.
    Il ne supprime jamais un enregistrement.
    """

    def __init__(self, secrets: Iterable[str]) -> None:
        super().__init__()
        self._secrets = sorted(
            {secret for secret in secrets if len(secret) >= MIN_SECRET_LENGTH},
            key=len,
            reverse=True,
        )

    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = self._redact(record.getMessage())
        record.args = None
        if record.exc_info and not record.exc_text:
            record.exc_text = logging.Formatter().formatException(record.exc_info)
        if record.exc_text:
            record.exc_text = self._redact(record.exc_text)
        if record.stack_info:
            record.stack_info = self._redact(record.stack_info)
        return True

    def _redact(self, text: str) -> str:
        for secret in self._secrets:
            text = text.replace(secret, REDACTED)
        text = _BEARER.sub(f"Bearer {REDACTED}", text)
        text = _KEY_VALUE.sub(lambda match: f"{match.group(1)}{REDACTED}", text)
        return _CARD.sub(REDACTED, text)
