class ProductNotFoundError(Exception):
    """Produit introuvable. Le message est fixe : le slug demande n'y est jamais reflechi."""

    def __init__(self) -> None:
        super().__init__("Produit introuvable.")
        self.message = "Produit introuvable."
