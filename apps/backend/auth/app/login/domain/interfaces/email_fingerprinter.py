from abc import ABC, abstractmethod


class EmailFingerprinter(ABC):
    """Empreinte non reversible d'une adresse, seule forme sous laquelle elle est journalisee."""

    @abstractmethod
    def fingerprint(self, email: str) -> str: ...
