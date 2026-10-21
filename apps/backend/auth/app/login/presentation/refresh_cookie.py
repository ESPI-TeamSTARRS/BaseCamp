from fastapi import Response

REFRESH_COOKIE = "refresh_token"
REFRESH_COOKIE_PATH = (
    "/api/auth"  # le navigateur ne l'envoie qu'aux routes d'auth, via la passerelle
)


def set_refresh_cookie(response: Response, value: str, max_age: int) -> None:
    response.set_cookie(
        REFRESH_COOKIE,
        value,
        max_age=max_age,
        path=REFRESH_COOKIE_PATH,
        secure=True,
        httponly=True,
        samesite="strict",
    )


def clear_refresh_cookie(response: Response) -> None:
    response.delete_cookie(
        REFRESH_COOKIE,
        path=REFRESH_COOKIE_PATH,
        secure=True,
        httponly=True,
        samesite="strict",
    )
