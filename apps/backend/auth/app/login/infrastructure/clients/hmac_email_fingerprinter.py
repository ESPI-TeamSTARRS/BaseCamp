from app.core.logging.email_pseudonymizer import EmailPseudonymizer
from app.login.domain.interfaces.email_fingerprinter import EmailFingerprinter


class HmacEmailFingerprinter(EmailFingerprinter):
    """HMAC-SHA256 tronque (`APP_LOG_PSEUDONYM_KEY`) : correlable entre evenements, jamais reversible."""

    def __init__(self, pseudonymizer: EmailPseudonymizer) -> None:
        self._pseudonymizer = pseudonymizer

    def fingerprint(self, email: str) -> str:
        return self._pseudonymizer.pseudonymize(email)
