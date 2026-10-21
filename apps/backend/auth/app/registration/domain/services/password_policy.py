from app.registration.domain.enums.weak_password_reason import WeakPasswordReason
from app.registration.domain.exceptions.weak_password_error import WeakPasswordError
from app.registration.domain.interfaces.common_password_list import CommonPasswordList

MIN_LENGTH = 12
MAX_LENGTH = 128  # borne le cout du hachage : au-dela, aucun gain de securite


class PasswordPolicy:
    """12 caracteres minimum, mots de passe courants refuses, aucune regle de composition."""

    def __init__(self, common_passwords: CommonPasswordList) -> None:
        self._common_passwords = common_passwords

    def validate(self, password: str) -> None:
        if len(password) < MIN_LENGTH:
            raise WeakPasswordError(WeakPasswordReason.TOO_SHORT)
        if len(password) > MAX_LENGTH:
            raise WeakPasswordError(WeakPasswordReason.TOO_LONG)
        if self._common_passwords.contains(password):
            raise WeakPasswordError(WeakPasswordReason.TOO_COMMON)
