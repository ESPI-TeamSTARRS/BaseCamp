class DomainException(Exception):
    """Erreur metier typee : code stable et message fixe (jamais de donnee saisie)."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
