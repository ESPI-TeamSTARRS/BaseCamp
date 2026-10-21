class InvalidWebhookPayloadError(Exception):
    """Corps signé mais illisible ou incohérent; `reason` est un code stable, jamais le contenu reçu."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason
