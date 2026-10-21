class ImageStorageUnavailableError(Exception):
    """Le stockage d'images ne répond pas : 503, rien n'a été modifié côté produit."""

    def __init__(self) -> None:
        super().__init__("Stockage des images indisponible.")
        self.message = "Stockage des images indisponible."
