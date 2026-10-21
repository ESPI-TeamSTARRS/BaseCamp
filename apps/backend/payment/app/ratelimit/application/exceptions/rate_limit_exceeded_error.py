class RateLimitExceededError(Exception):
    """L'appelant a épuisé son budget de requêtes pour cette route dans la fenêtre courante."""

    def __init__(self, retry_after_seconds: int) -> None:
        super().__init__("rate limit exceeded")
        self.retry_after_seconds = retry_after_seconds
