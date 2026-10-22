from app.login.domain.exceptions.domain_exception import DomainException


class BackofficeRefusedError(DomainException):
    """Une seule erreur pour defi inconnu, expire ou deja utilise, visage refuse, mot de passe faux,
    etape verrouillee ou compte sans droit : rien ne dit laquelle."""

    def __init__(self) -> None:
        super().__init__("backoffice_refused", "Identifiants invalides.")


class FaceImageInvalidError(DomainException):
    """Image illisible ou hors limites : 422, ne compte pas comme un echec."""

    def __init__(self) -> None:
        super().__init__("face_image_invalid", "Image invalide.")


class FaceTemplateInvalidError(DomainException):
    """Gabarit de l'operateur inexploitable : 409, journalise, ne compte pas comme un echec."""

    def __init__(self) -> None:
        super().__init__("face_template_invalid", "Verification du visage impossible.")
