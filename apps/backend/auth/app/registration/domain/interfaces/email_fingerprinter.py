from abc import ABC, abstractmethod

from app.registration.domain.value_objects.email_address import EmailAddress


class EmailFingerprinter(ABC):
    """Empreinte non reversible d'une adresse, seule forme sous laquelle elle est journalisee."""

    @abstractmethod
    def fingerprint(self, email: EmailAddress) -> str: ...
