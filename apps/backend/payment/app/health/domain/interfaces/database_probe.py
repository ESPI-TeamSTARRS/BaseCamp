from abc import ABC, abstractmethod


class DatabaseProbe(ABC):
    """Verifie que la base de donnees repond (ne leve jamais d'exception)."""

    @abstractmethod
    def is_available(self) -> bool: ...
