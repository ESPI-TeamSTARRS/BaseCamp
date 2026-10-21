class PaymentRejectedError(Exception):
    """Le service de paiement a refusé la demande (règle métier), sans être indisponible."""

    def __init__(self, conflict: bool) -> None:
        super().__init__("payment rejected")
        self.conflict = conflict  # True : une intention existe déjà pour cette commande (409)
