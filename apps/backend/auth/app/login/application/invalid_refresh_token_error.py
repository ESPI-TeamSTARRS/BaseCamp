class InvalidRefreshTokenError(Exception):
    """Jeton de rafraichissement absent, inconnu, expire, rejoue ou d'un compte desactive.

    Une seule reponse, sans le motif interne (il n'existe que dans l'evenement journalise).
    """

    def __init__(self) -> None:
        super().__init__("Session expirée.")
        self.message = "Session expirée."
