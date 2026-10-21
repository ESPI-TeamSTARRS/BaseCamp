MESSAGES = {
    "order_already_paid": "Commande deja payee.",
    "order_expired": "Commande expiree.",
    "no_pending_payment": "Aucun paiement en attente pour cette commande.",
}


class OrderNotPayableError(Exception):
    """La commande ne peut pas être payée dans son état actuel (409)."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason
        self.message = MESSAGES[reason]
