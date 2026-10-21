class ForbiddenError(Exception):
    """Authentifie mais sans le role exige : une seule reponse, sans dire quel role manque."""

    def __init__(self) -> None:
        super().__init__("Accès refusé.")
        self.message = "Accès refusé."
