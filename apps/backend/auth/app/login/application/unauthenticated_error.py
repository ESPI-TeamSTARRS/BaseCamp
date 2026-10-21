class UnauthenticatedError(Exception):
    """Jeton absent, expire, falsifie ou revoque : une seule reponse, sans le motif interne."""

    def __init__(self) -> None:
        super().__init__("Authentification requise.")
        self.message = "Authentification requise."
