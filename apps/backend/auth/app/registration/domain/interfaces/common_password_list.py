from abc import ABC, abstractmethod


class CommonPasswordList(ABC):
    """Liste de mots de passe courants refuses (comparaison insensible a la casse)."""

    @abstractmethod
    def contains(self, password: str) -> bool: ...
