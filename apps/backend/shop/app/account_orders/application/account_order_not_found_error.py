class AccountOrderNotFoundError(Exception):
    """Commande inconnue OU d'un autre compte : une seule reponse, sans les distinguer."""

    def __init__(self) -> None:
        super().__init__("Commande introuvable.")
        self.message = "Commande introuvable."
