import pytest

from app.intent.application.authenticate_service import AuthenticateServiceUseCase
from app.intent.application.exceptions.unauthorized_service_error import UnauthorizedServiceError


class TestAuthenticateServiceUseCase:
    def test_returns_the_caller_owning_the_token(self) -> None:
        use_case = AuthenticateServiceUseCase({"shop": "tok-shop-1234", "admin": "tok-admin-9999"})

        assert use_case.execute("tok-admin-9999") == "admin"

    @pytest.mark.parametrize("token", [None, "", "wrong", "tok-shop-123", "tok-shop-12345"])
    def test_rejects_missing_or_invalid_tokens(self, token: str | None) -> None:
        use_case = AuthenticateServiceUseCase({"shop": "tok-shop-1234"})

        with pytest.raises(UnauthorizedServiceError):
            use_case.execute(token)

    def test_rejects_everything_when_no_token_is_configured(self) -> None:
        with pytest.raises(UnauthorizedServiceError):
            AuthenticateServiceUseCase({}).execute("anything")

    def test_ignores_configured_empty_tokens(self) -> None:
        with pytest.raises(UnauthorizedServiceError):
            AuthenticateServiceUseCase({"shop": ""}).execute("")
