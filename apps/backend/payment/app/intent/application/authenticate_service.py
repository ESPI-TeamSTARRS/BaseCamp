import hmac

from app.intent.application.exceptions.unauthorized_service_error import UnauthorizedServiceError


class AuthenticateServiceUseCase:
    """Identifie l'appelant par son jeton statique (comparaison en temps constant)."""

    def __init__(self, tokens_by_caller: dict[str, str]) -> None:
        self._tokens_by_caller = tokens_by_caller

    def execute(self, token: str | None) -> str:
        candidate = (token or "").encode()
        caller: str | None = None
        for name, expected in self._tokens_by_caller.items():
            # Tous les jetons sont comparés : pas de sortie anticipée qui trahirait un appelant.
            matches = hmac.compare_digest(candidate, expected.encode())
            if matches and candidate and caller is None:
                caller = name
        if caller is None:
            raise UnauthorizedServiceError
        return caller
