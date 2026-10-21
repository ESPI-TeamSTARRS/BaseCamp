from pydantic import BaseModel


class FaceResponse(BaseModel):
    """Le visage est accepte : le defi peut servir une fois pour le mot de passe. Aucun score."""

    face_ok: bool = True
