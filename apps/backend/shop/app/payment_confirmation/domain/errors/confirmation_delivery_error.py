class ConfirmationDeliveryError(Exception):
    """L'email n'a pas pu être remis (serveur d'envoi arrêté, refus, délai dépassé).

    `reason` est un code stable pour le journal (`http_403`, `timeout`, `connection_error`,
    `invalid_response`, `not_configured`, `delivery_failed`) : jamais l'adresse, le corps ni le secret.
    """

    def __init__(self, reason: str = "delivery_failed") -> None:
        super().__init__(reason)
        self.reason = reason
