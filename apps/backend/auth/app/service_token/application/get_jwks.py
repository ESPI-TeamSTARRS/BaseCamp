from app.service_token.domain.entities.public_jwk import PublicJwk
from app.service_token.domain.interfaces.signing_key_directory import SigningKeyDirectory


class GetJwksUseCase:
    """Publie la clé publique de signature (jamais la clé privée) pour vérifier les jetons."""

    def __init__(self, key_directory: SigningKeyDirectory) -> None:
        self._key_directory = key_directory

    def execute(self) -> list[PublicJwk]:
        return [self._key_directory.public_jwk()]
