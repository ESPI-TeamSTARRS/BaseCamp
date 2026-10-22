from abc import ABC, abstractmethod
from uuid import UUID


class TemplateCipher(ABC):
    """Chiffrement au repos des gabarits faciaux (donnee biometrique).

    Le gabarit est lie au compte : un gabarit recopie sur une autre ligne ne se dechiffre pas.
    """

    @abstractmethod
    def encrypt(self, account_id: UUID, template: bytes) -> bytes: ...

    @abstractmethod
    def decrypt(self, account_id: UUID, stored: bytes) -> bytes:
        """Leve `GabaritInvalide` si le contenu est altere, d'une autre cle ou d'un autre compte."""
