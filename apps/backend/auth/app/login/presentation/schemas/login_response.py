from pydantic import BaseModel


class LoginResponse(BaseModel):
    """Le jeton d'acces va dans le corps (garde en memoire par le front) ; le rafraichissement, en cookie."""

    access_token: str
    token_type: str = "Bearer"  # noqa: S105
    expires_in: int
