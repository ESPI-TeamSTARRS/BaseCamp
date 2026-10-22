from pydantic import BaseModel


class InvitationCompleteResponse(BaseModel):
    """Le compte operateur est cree : il se connecte ensuite par les trois temps (visage, mot de passe).
    Aucun jeton n'est emis ici."""

    created: bool = True
