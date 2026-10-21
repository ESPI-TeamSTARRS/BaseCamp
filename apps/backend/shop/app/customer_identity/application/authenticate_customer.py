from app.core.events.business_event import BusinessEvent
from app.core.events.business_event_logger import BusinessEventLogger
from app.customer_identity.application import identity_events as catalog
from app.customer_identity.application.identity_unavailable_error import IdentityUnavailableError
from app.customer_identity.application.unauthenticated_error import UnauthenticatedError
from app.customer_identity.domain.entities.customer import Customer
from app.customer_identity.domain.exceptions.client_token_rejected_error import (
    ClientTokenRejectedError,
)
from app.customer_identity.domain.exceptions.verification_keys_unavailable_error import (
    VerificationKeysUnavailableError,
)
from app.customer_identity.domain.interfaces.client_token_verifier import ClientTokenVerifier
from app.customer_identity.domain.interfaces.clock import Clock


class AuthenticateCustomerUseCase:
    """Identifie un client par son jeton d'acces signe par `auth` (verification locale, par JWKS).

    - `require` : route reservee aux clients connectes. Sans jeton ou jeton refuse : 401 generique;
      cles illisibles : `IdentityUnavailableError` (503).
    - `optional` : route ouverte aux invites (passage de commande). Sans jeton, avec un jeton refuse
      ou sans cle lisible, l'appelant est traite en invite : un achat n'est jamais bloque par
      l'identification. Le rejet reste journalise.
    """

    def __init__(
        self, verifier: ClientTokenVerifier, clock: Clock, events: BusinessEventLogger
    ) -> None:
        self._verifier = verifier
        self._clock = clock
        self._events = events

    def require(self, token: str | None) -> Customer:
        if not token:
            raise UnauthenticatedError
        try:
            return self._verifier.verify(token, self._clock.now())
        except ClientTokenRejectedError as error:
            self._log_rejection(error.rejection.value)
            raise UnauthenticatedError from None
        except VerificationKeysUnavailableError:
            self._log_unavailable()
            raise IdentityUnavailableError from None

    def optional(self, token: str | None) -> Customer | None:
        if not token:
            return None
        try:
            return self._verifier.verify(token, self._clock.now())
        except ClientTokenRejectedError as error:
            self._log_rejection(error.rejection.value)
        except VerificationKeysUnavailableError:
            self._log_unavailable()
        return None

    def _log_rejection(self, reason: str) -> None:
        self._events.log(
            BusinessEvent.denied(
                catalog.TOKEN_REJECTED, reason, resource_type=catalog.RESOURCE_ACCESS_TOKEN
            )
        )

    def _log_unavailable(self) -> None:
        self._events.log(
            BusinessEvent.error(
                catalog.KEYS_UNAVAILABLE,
                catalog.REASON_KEYS_UNAVAILABLE,
                resource_type=catalog.RESOURCE_ACCESS_TOKEN,
            )
        )
