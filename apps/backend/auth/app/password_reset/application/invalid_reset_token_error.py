MESSAGE = "Lien de réinitialisation invalide ou expiré."


class InvalidResetTokenError(Exception):
    """Jeton inconnu, expire ou deja utilise : un seul message, pour ne rien reveler."""

    def __init__(self) -> None:
        super().__init__(MESSAGE)
        self.message = MESSAGE
