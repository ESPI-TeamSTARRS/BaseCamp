class InvalidImageError(Exception):
    """Fichier refusé; `reason` est un code stable (`too_large`, `unsupported_type`, `empty`)."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason
