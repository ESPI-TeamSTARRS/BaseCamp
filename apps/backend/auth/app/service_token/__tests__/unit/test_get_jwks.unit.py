from app.service_token.application.get_jwks import GetJwksUseCase
from app.service_token.domain.entities.public_jwk import PublicJwk
from app.service_token.domain.interfaces.signing_key_directory import SigningKeyDirectory


class FakeDirectory(SigningKeyDirectory):
    def public_jwk(self) -> PublicJwk:
        return PublicJwk("kid-1", "x-coordinate")


class TestGetJwks:
    def test_returns_the_public_signing_key(self) -> None:
        assert GetJwksUseCase(FakeDirectory()).execute() == [PublicJwk("kid-1", "x-coordinate")]
