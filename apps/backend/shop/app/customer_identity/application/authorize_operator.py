from app.core.events.business_event import BusinessEvent
from app.core.events.business_event_logger import BusinessEventLogger
from app.customer_identity.application import identity_events as catalog
from app.customer_identity.application.forbidden_error import ForbiddenError
from app.customer_identity.application.identity_unavailable_error import IdentityUnavailableError
from app.customer_identity.application.unauthenticated_error import UnauthenticatedError
from app.customer_identity.domain.entities.operator import Operator
from app.customer_identity.domain.exceptions.client_token_rejected_error import (
    ClientTokenRejectedError,
)
from app.customer_identity.domain.exceptions.verification_keys_unavailable_error import (
    VerificationKeysUnavailableError,
)
from app.customer_identity.domain.interfaces.clock import Clock
from app.customer_identity.domain.interfaces.operator_token_verifier import OperatorTokenVerifier

OPERATOR_ROLE = "operator"


class AuthorizeOperatorUseCase:
    """Garde des routes d'administration : jeton d'`auth` vérifié par JWKS, rôle `operator` et second facteur.

    - Sans jeton, jeton refusé (signature, expiration, audience…) : `UnauthenticatedError` (401).
    - Jeton valide sans le rôle `operator`, ou sans la méthode `required_amr` dans `amr` : `ForbiddenError` (403).
    - Clés illisibles : `IdentityUnavailableError` (503) — jamais un accès par défaut.
    """

    def __init__(
        self,
        verifier: OperatorTokenVerifier,
        clock: Clock,
        events: BusinessEventLogger,
        required_amr: str,
    ) -> None:
        self._verifier = verifier
        self._clock = clock
        self._events = events
        self._required_amr = required_amr

    def require(self, token: str | None) -> Operator:
        if not token:
            raise UnauthenticatedError
        operator = self._verified(token)
        if OPERATOR_ROLE not in operator.roles:
            self._deny(catalog.REASON_NOT_OPERATOR)
        if self._required_amr not in operator.authentication_methods:
            self._deny(catalog.REASON_SECOND_FACTOR_MISSING)
        return operator

    def _verified(self, token: str) -> Operator:
        try:
            return self._verifier.verify_operator(token, self._clock.now())
        except ClientTokenRejectedError as error:
            self._events.log(
                BusinessEvent.denied(
                    catalog.TOKEN_REJECTED,
                    error.rejection.value,
                    resource_type=catalog.RESOURCE_ACCESS_TOKEN,
                )
            )
            raise UnauthenticatedError from None
        except VerificationKeysUnavailableError:
            self._events.log(
                BusinessEvent.error(
                    catalog.KEYS_UNAVAILABLE,
                    catalog.REASON_KEYS_UNAVAILABLE,
                    resource_type=catalog.RESOURCE_ACCESS_TOKEN,
                )
            )
            raise IdentityUnavailableError from None

    def _deny(self, reason: str) -> None:
        self._events.log(
            BusinessEvent.denied(
                catalog.OPERATOR_ACCESS_DENIED, reason, resource_type=catalog.RESOURCE_ACCESS_TOKEN
            )
        )
        raise ForbiddenError
