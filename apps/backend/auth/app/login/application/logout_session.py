from app.core.events.business_event import BusinessEvent
from app.core.events.business_event_logger import BusinessEventLogger
from app.login.application import login_events as catalog
from app.login.application.unit_of_work_factory import UnitOfWorkFactory
from app.login.domain.interfaces.refresh_token_generator import RefreshTokenGenerator


class LogoutSessionUseCase:
    """Revoque la famille du jeton de rafraichissement presente; idempotent.

    Un jeton absent, inconnu ou deja revoque ne produit ni erreur ni evenement : l'appel est
    sans effet et ne revele rien. Le jeton d'acces deja emis expire seul (15 minutes au plus).
    """

    def __init__(
        self,
        unit_of_work: UnitOfWorkFactory,
        refresh_tokens: RefreshTokenGenerator,
        events: BusinessEventLogger,
    ) -> None:
        self._unit_of_work = unit_of_work
        self._refresh_tokens = refresh_tokens
        self._events = events

    def execute(self, raw_token: str | None, client_ip: str | None = None) -> None:
        if not raw_token:
            return
        with self._unit_of_work() as work:
            known = work.refresh_tokens.find_by_hash(self._refresh_tokens.digest(raw_token))
            if known is None:
                return
            revoked = work.refresh_tokens.revoke_family(known.family_id)
            work.commit()
        self._events.log(
            BusinessEvent.success(
                catalog.LOGOUT_COMPLETED,
                resource_type=catalog.RESOURCE_ACCOUNT,
                resource_id=str(known.user_id),
                actor_type=catalog.ACTOR_USER,
                actor_id=str(known.user_id),
                client_ip=client_ip,
                attributes={"sessions_revoked": revoked},
            )
        )
