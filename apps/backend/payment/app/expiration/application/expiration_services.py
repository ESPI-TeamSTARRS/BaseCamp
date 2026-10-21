from dataclasses import dataclass

from app.expiration.application.expire_unconfirmed_intents import ExpireUnconfirmedIntentsUseCase


@dataclass(frozen=True)
class ExpirationServices:
    """Cas d'usage de la tranche, câblés dans wiring.py et lus par le point d'entrée."""

    expire: ExpireUnconfirmedIntentsUseCase
