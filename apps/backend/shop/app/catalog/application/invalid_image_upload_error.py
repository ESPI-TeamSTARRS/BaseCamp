class InvalidImageUploadError(Exception):
    """Image refusée (vide, trop lourde, type non accepté) : 422 sans effet de bord."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason
        self.message = "Image invalide."
