class InvalidCartError(Exception):
    """Panier invalide. Le message est fixe : aucune valeur envoyee par le client n'y figure."""

    def __init__(self, message: str, reason: str = "invalid_cart") -> None:
        super().__init__(message)
        self.message = message
        self.reason = reason
