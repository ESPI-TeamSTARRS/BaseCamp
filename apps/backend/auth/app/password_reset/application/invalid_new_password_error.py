class InvalidNewPasswordError(Exception):
    """Mot de passe non conforme : champ fautif et message fixe, jamais la valeur saisie."""

    def __init__(self, message: str) -> None:
        super().__init__("Mot de passe invalide.")
        self.fields = ("password",)
        self.messages = (message,)
