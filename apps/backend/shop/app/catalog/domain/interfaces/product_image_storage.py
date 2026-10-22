from abc import ABC, abstractmethod


class ProductImageStorage(ABC):
    """Port de stockage des images produit (bucket `product-images` en production)."""

    @abstractmethod
    def store(self, key: str, content: bytes, content_type: str) -> None:
        """Écrit l'objet; lève ImageStorageError si le stockage refuse ou ne répond pas."""
