from uuid import UUID

from app.core.events.business_event import BusinessEvent
from app.core.events.business_event_logger import BusinessEventLogger
from app.login.application import login_events as catalog
from app.login.application.account_profile import AccountProfile
from app.login.application.unauthenticated_error import UnauthenticatedError
from app.login.application.unit_of_work_factory import UnitOfWorkFactory
from app.login.domain.entities.account import Account
from app.login.domain.enums.token_rejection import TokenRejection
from app.login.domain.exceptions.access_token_rejected_error import AccessTokenRejectedError
from app.login.domain.interfaces.access_token_verifier import AccessTokenVerifier
from app.login.domain.interfaces.clock import Clock


class GetCurrentAccountUseCase:
    """Profil du titulaire d'un jeton d'acces valide, dont le compte existe et reste actif."""

    def __init__(
        self,
        unit_of_work: UnitOfWorkFactory,
        verifier: AccessTokenVerifier,
        clock: Clock,
        events: BusinessEventLogger,
    ) -> None:
        self._unit_of_work = unit_of_work
        self._verifier = verifier
        self._clock = clock
        self._events = events

    def execute(self, token: str) -> AccountProfile:
        try:
            claims = self._verifier.verify(token, self._clock.now())
        except AccessTokenRejectedError as error:
            self._reject(error.rejection, None)
            raise UnauthenticatedError from None
        account = self._find(claims.subject)
        if account is None or account.disabled:
            self._reject(TokenRejection.REVOKED, claims.subject)
            raise UnauthenticatedError
        return AccountProfile(account.id, account.email, (account.role,), account.email_verified)

    def _find(self, account_id: UUID) -> Account | None:
        with self._unit_of_work() as work:
            return work.accounts.find_by_id(account_id)

    def _reject(self, rejection: TokenRejection, account_id: UUID | None) -> None:
        self._events.log(
            BusinessEvent.denied(
                catalog.TOKEN_REJECTED,
                rejection.value,
                resource_type=catalog.RESOURCE_ACCESS_TOKEN,
                actor_type=catalog.ACTOR_USER if account_id else None,
                actor_id=str(account_id) if account_id else None,
            )
        )
