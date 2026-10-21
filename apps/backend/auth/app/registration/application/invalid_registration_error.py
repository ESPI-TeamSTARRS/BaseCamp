class InvalidRegistrationError(Exception):
    """Inscription refusee : champs fautifs et messages fixes, jamais la valeur saisie."""

    def __init__(self, fields: tuple[str, ...], messages: tuple[str, ...]) -> None:
        super().__init__("Inscription invalide.")
        self.fields = fields
        self.messages = messages
