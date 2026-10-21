from typing import ClassVar


class ProductConflictError(Exception):
    """Conflit d'état : version périmée, produit archivé, doublon ou trop d'images (409)."""

    MESSAGES: ClassVar[dict[str, str]] = {
        "stale_version": "Version perimee.",
        "product_archived": "Produit archive.",
        "duplicate_product": "Produit deja existant.",
        "too_many_images": "Nombre maximal d'images atteint.",
    }

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason
        self.message = self.MESSAGES[reason]
