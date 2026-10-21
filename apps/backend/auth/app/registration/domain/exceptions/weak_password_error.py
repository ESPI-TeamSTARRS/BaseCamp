from app.registration.domain.enums.weak_password_reason import WeakPasswordReason
from app.registration.domain.exceptions.domain_exception import DomainException

_MESSAGES = {
    WeakPasswordReason.TOO_SHORT: "Le mot de passe doit contenir au moins 12 caractères.",
    WeakPasswordReason.TOO_LONG: "Le mot de passe ne doit pas dépasser 128 caractères.",
    WeakPasswordReason.TOO_COMMON: "Ce mot de passe est trop courant, choisissez-en un autre.",
}


class WeakPasswordError(DomainException):
    def __init__(self, reason: WeakPasswordReason) -> None:
        super().__init__(reason.value, _MESSAGES[reason])
        self.reason = reason
