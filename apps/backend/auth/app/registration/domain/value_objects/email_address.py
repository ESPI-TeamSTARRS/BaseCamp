import re
from dataclasses import dataclass

from app.registration.domain.exceptions.invalid_email_error import InvalidEmailError

MAX_LENGTH = 254
MAX_LOCAL_PART_LENGTH = 64
_LABEL = r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?"
_LOCAL = r"[a-z0-9.!#$%&*+/=?^_{|}~'-]+"
_PATTERN = re.compile(rf"{_LOCAL}@{_LABEL}(?:\.{_LABEL})+")


@dataclass(frozen=True)
class EmailAddress:
    """Adresse normalisee (minuscules). Aucun espace ni retour a la ligne : sure en en-tete SMTP."""

    value: str

    @classmethod
    def of(cls, raw: str) -> "EmailAddress":
        candidate = raw.strip().lower()
        local_part = candidate.partition("@")[0]
        valid = (
            len(candidate) <= MAX_LENGTH
            and len(local_part) <= MAX_LOCAL_PART_LENGTH
            and _PATTERN.fullmatch(candidate) is not None
        )
        if not valid:
            raise InvalidEmailError
        return cls(candidate)
