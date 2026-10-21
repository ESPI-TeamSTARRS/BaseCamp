from collections.abc import Callable
from datetime import datetime

from app.caller_identity.application import caller_events as catalog
from app.caller_identity.application.caller_errors import (
    CallerForbiddenError,
    CallerUnauthorizedError,
    IdentityUnavailableError,
)
from app.caller_identity.domain.entities.caller import Caller
from app.caller_identity.domain.entities.caller_requirement import CallerRequirement
from app.caller_identity.domain.enums.token_kind import TokenKind
from app.caller_identity.domain.exceptions.token_rejected_error import (
    TokenRejectedError,
    TokenRejection,
)
from app.caller_identity.domain.exceptions.verification_keys_unavailable_error import (
    VerificationKeysUnavailableError,
)
from app.caller_identity.domain.interfaces.token_verifier import TokenVerifier
from app.core.events.business_event import BusinessEvent
from app.core.events.business_event_logger import BusinessEventLogger
from app.core.events.outcome import Outcome


class AuthenticateCallerUseCase:
    """Identifie l'appelant par son jeton signe par `auth` et controle ce que la route exige.

    Verification locale (cles publiques JWKS en cache) : aucun appel a `auth` par requete. Echecs :
    - jeton absent, invalide, expire, falsifie, mauvaise audience, jeton client rejoue sur une route
      de service : `CallerUnauthorizedError` (401, meme reponse; le motif n'est que dans le journal);
    - jeton authentique sans le scope (service) ou le role operateur (client) : `CallerForbiddenError`;
    - cles illisibles sans cache : `IdentityUnavailableError`.
    """

    def __init__(
        self,
        verifier: TokenVerifier,
        clock_now: Callable[[], datetime],
        events: BusinessEventLogger,
    ) -> None:
        self._verifier = verifier
        self._now = clock_now
        self._events = events

    def execute(
        self, token: str | None, requirement: CallerRequirement, client_ip: str | None = None
    ) -> Caller:
        if not token:
            self._reject(TokenRejection.MISSING, client_ip)
        try:
            caller = self._verifier.verify(token or "", self._now())
        except TokenRejectedError as error:
            self._reject(error.rejection, client_ip)
        except VerificationKeysUnavailableError:
            self._events.log(
                BusinessEvent.error(catalog.KEYS_UNAVAILABLE, catalog.REASON_KEYS_UNAVAILABLE)
            )
            raise IdentityUnavailableError from None
        if caller.kind is TokenKind.CLIENT and not requirement.accepts_clients:
            self._events.log(
                BusinessEvent.denied(
                    catalog.AUTHENTICATED, catalog.REASON_CLIENT_TOKEN_REFUSED, client_ip=client_ip
                )
            )
            raise CallerUnauthorizedError
        if not requirement.accepts(caller):
            self._forbid(caller, requirement, client_ip)
        self._events.log(
            BusinessEvent.success(
                catalog.AUTHENTICATED, actor_type=caller.actor_type, actor_id=caller.subject
            )
        )
        return caller

    def _reject(self, rejection: TokenRejection, client_ip: str | None) -> None:
        self._events.log(
            BusinessEvent(
                event=catalog.AUTHENTICATED,
                outcome=Outcome.DENIED,
                reason=catalog.REASON_INVALID_TOKEN,
                client_ip=client_ip,
                attributes={"cause": rejection.value},
            )
        )
        raise CallerUnauthorizedError

    def _forbid(
        self, caller: Caller, requirement: CallerRequirement, client_ip: str | None
    ) -> None:
        reason = (
            catalog.REASON_MISSING_SCOPE
            if caller.kind is TokenKind.SERVICE
            else catalog.REASON_ROLE_REQUIRED
        )
        self._events.log(
            BusinessEvent.denied(
                catalog.FORBIDDEN,
                reason,
                actor_type=caller.actor_type,
                actor_id=caller.subject,
                client_ip=client_ip,
                attributes={"required": requirement.scope},
            )
        )
        raise CallerForbiddenError
