class InvalidCatalogQueryError(Exception):
    """Requete de catalogue invalide. Le message est fixe : l'entree n'y est jamais reflechie."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message
