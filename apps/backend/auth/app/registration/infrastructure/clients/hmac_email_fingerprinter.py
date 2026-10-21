from app.core.logging.email_pseudonymizer import EmailPseudonymizer
from app.registration.domain.interfaces.email_fingerprinter import EmailFingerprinter
from app.registration.domain.value_objects.email_address import EmailAddress


class HmacEmailFingerprinter(EmailFingerprinter):
    """HMAC-SHA256 tronque (`APP_LOG_PSEUDONYM_KEY`) : correlable entre evenements, jamais reversible."""

    def __init__(self, pseudonymizer: EmailPseudonymizer) -> None:
        self._pseudonymizer = pseudonymizer

    def fingerprint(self, email: EmailAddress) -> str:
        return self._pseudonymizer.pseudonymize(email.value)
