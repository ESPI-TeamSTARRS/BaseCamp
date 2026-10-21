from typing import Protocol


class EmailPseudonymizer(Protocol):
    """Empreinte non reversible d'un email, pour les logs (l'email n'est jamais journalisé)."""

    def pseudonymize(self, email: str) -> str: ...
