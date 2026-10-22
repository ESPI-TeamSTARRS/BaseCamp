class InvalidProductError(Exception):
    """Données de produit refusées par une règle métier; `reason` est un code stable."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason
        self.message = "Requete invalide."
