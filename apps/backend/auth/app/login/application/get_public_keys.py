from app.login.domain.entities.public_key import PublicKey
from app.login.domain.interfaces.public_key_set import PublicKeySet


class GetPublicKeysUseCase:
    """Cles publiques que `shop` et `payment` utilisent pour verifier un jeton sans appeler `auth`."""

    def __init__(self, keys: PublicKeySet) -> None:
        self._keys = keys

    def execute(self) -> tuple[PublicKey, ...]:
        return self._keys.public_keys()
