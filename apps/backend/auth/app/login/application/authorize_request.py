from app.core.events.business_event import BusinessEvent
from app.core.events.business_event_logger import BusinessEventLogger
from app.login.application import login_events as catalog
from app.login.application.forbidden_error import ForbiddenError
from app.login.application.principal import Principal
from app.login.application.unauthenticated_error import UnauthenticatedError
from app.login.application.unit_of_work_factory import UnitOfWorkFactory
from app.login.domain.enums.token_rejection import TokenRejection
from app.login.domain.exceptions.access_token_rejected_error import AccessTokenRejectedError
from app.login.domain.interfaces.access_token_verifier import AccessTokenVerifier
from app.login.domain.interfaces.clock import Clock


class AuthorizeRequestUseCase:
    """Identifie l'appelant par son jeton signe et verifie qu'il porte l'un des roles exiges.

    Les roles viennent des claims du jeton verifie (jamais d'un parametre du client). En plus, le
    compte doit exister, etre actif et avoir toujours ce role en base : un compte desactive ou
    retrograde perd l'acces aussitot, sans attendre l'expiration du jeton. Jeton absent, invalide
    ou compte inactif : `UnauthenticatedError` (401). Role insuffisant : `ForbiddenError` (403).
    """

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

    def execute(self, token: str, required_roles: frozenset[str]) -> Principal:
        try:
            claims = self._verifier.verify(token, self._clock.now())
        except AccessTokenRejectedError as error:
            self._reject(error.rejection)
            raise UnauthenticatedError from None
        with self._unit_of_work() as work:
            account = work.accounts.find_by_id(claims.subject)
        if account is None or account.disabled:
            self._reject(TokenRejection.REVOKED, str(claims.subject))
            raise UnauthenticatedError
        principal = Principal(claims.subject, tuple(r for r in claims.roles if r == account.role))
        if not principal.has_any(required_roles):
            self._events.log(
                BusinessEvent.denied(
                    catalog.ACCESS_DENIED,
                    catalog.REASON_ROLE_REQUIRED,
                    resource_type=catalog.RESOURCE_ACCESS_TOKEN,
                    actor_type=catalog.ACTOR_USER,
                    actor_id=str(claims.subject),
                    attributes={"required": ",".join(sorted(required_roles))},
                )
            )
            raise ForbiddenError
        return principal

    def _reject(self, rejection: TokenRejection, account_id: str | None = None) -> None:
        self._events.log(
            BusinessEvent.denied(
                catalog.TOKEN_REJECTED,
                rejection.value,
                resource_type=catalog.RESOURCE_ACCESS_TOKEN,
                actor_type=catalog.ACTOR_USER if account_id else None,
                actor_id=account_id,
            )
        )
