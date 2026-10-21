class IdentityUnavailableError(Exception):
    """Les cles de verification sont illisibles et aucune n'est en cache : reessayer plus tard."""

    def __init__(self) -> None:
        super().__init__("Identification momentanément indisponible.")
        self.message = "Identification momentanément indisponible."
