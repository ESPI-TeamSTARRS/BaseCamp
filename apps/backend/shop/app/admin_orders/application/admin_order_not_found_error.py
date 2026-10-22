class AdminOrderNotFoundError(Exception):
    def __init__(self) -> None:
        super().__init__("Commande introuvable.")
        self.message = "Commande introuvable."
