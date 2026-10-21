from abc import ABC, abstractmethod
from collections.abc import Mapping
from typing import Any


class JwksSource(ABC):
    @abstractmethod
    def fetch(self) -> Mapping[str, Mapping[str, Any]]:
        """Cles publiques de verification publiees par `auth`, indexees par `kid`.

        Leve `VerificationKeysUnavailableError` si `auth` ne repond pas ou repond autre chose.
        """
