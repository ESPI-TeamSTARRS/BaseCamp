import re
from collections.abc import Mapping

from app.core.events.business_event import Scalar

MASK = "[masked]"
_SENSITIVE_TOKENS = frozenset(
    {
        "password",
        "passwd",
        "token",
        "authorization",
        "secret",
        "card",
        "pan",
        "cvv",
        "cvc",
        "idempotency",
        "cookie",
        "apikey",
    }
)
_EMAIL = re.compile(r"[\w.+-]++@[\w-]++(?:\.[\w-]++)++")
_CARD_CANDIDATE = re.compile(r"(?<![\w-])(?:\d[ -]?){12,18}\d(?![\w-])")
_MIN_CARD_DIGITS = 13


def _luhn_valid(digits: str) -> bool:
    total = 0
    for index, char in enumerate(reversed(digits)):
        value = int(char)
        if index % 2 == 1:
            value = value * 2 - 9 if value > 4 else value * 2
        total += value
    return total % 10 == 0


def _mask_card(match: re.Match[str]) -> str:
    digits = re.sub(r"\D", "", match.group())
    return "[card]" if len(digits) >= _MIN_CARD_DIGITS and _luhn_valid(digits) else match.group()


class EventSanitizer:
    """Filet de securite : masque les cles sensibles, les emails et les numeros de carte."""

    def attributes(self, values: Mapping[str, Scalar]) -> dict[str, Scalar]:
        return {key: self._value(key, value) for key, value in values.items()}

    def text(self, value: str) -> str:
        return _CARD_CANDIDATE.sub(_mask_card, _EMAIL.sub("[email]", value))

    def _value(self, key: str, value: Scalar) -> Scalar:
        if self._is_sensitive(key):
            return MASK
        return self.text(value) if isinstance(value, str) else value

    @staticmethod
    def _is_sensitive(key: str) -> bool:
        lowered = key.lower()
        return "api_key" in lowered or bool(set(lowered.split("_")) & _SENSITIVE_TOKENS)
