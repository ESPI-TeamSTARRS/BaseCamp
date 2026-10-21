class UnauthenticatedError(Exception):
    """Jeton absent ou refuse : une seule reponse, sans le motif interne."""

    def __init__(self) -> None:
        super().__init__("Authentification requise.")
        self.message = "Authentification requise."
