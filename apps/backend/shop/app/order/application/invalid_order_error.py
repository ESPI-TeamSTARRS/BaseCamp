class InvalidOrderError(Exception):
    """Commande invalide. Message fixe : aucune valeur envoyee par le client n'y figure."""

    def __init__(self, message: str, reason: str) -> None:
        super().__init__(message)
        self.message = message
        self.reason = reason
