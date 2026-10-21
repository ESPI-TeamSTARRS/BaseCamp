class InvalidWebhookSignatureError(Exception):
    """Signature absente, mal formée, hors fenêtre de temps ou fausse; `reason` est un code stable."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason
