class ForbiddenError(Exception):
    """Jeton valide mais droits insuffisants : une seule réponse, sans le motif interne."""

    def __init__(self) -> None:
        super().__init__("Acces refuse.")
        self.message = "Acces refuse."
