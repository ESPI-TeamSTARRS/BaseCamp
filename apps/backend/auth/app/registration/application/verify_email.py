from app.core.events.business_event import BusinessEvent
from app.core.events.business_event_logger import BusinessEventLogger
from app.registration.application import registration_events as catalog
from app.registration.application.invalid_verification_token_error import (
    InvalidVerificationTokenError,
)
from app.registration.application.unit_of_work_factory import UnitOfWorkFactory
from app.registration.domain.interfaces.clock import Clock
from app.registration.domain.interfaces.token_generator import TokenGenerator


class VerifyEmailUseCase:
    """Confirme l'adresse : le jeton est consomme et l'email marque verifie dans une transaction."""

    def __init__(
        self,
        unit_of_work: UnitOfWorkFactory,
        tokens: TokenGenerator,
        clock: Clock,
        events: BusinessEventLogger,
    ) -> None:
        self._unit_of_work = unit_of_work
        self._tokens = tokens
        self._clock = clock
        self._events = events

    def execute(self, token: str) -> None:
        now = self._clock.now()
        with self._unit_of_work() as work:
            user_id = work.tokens.consume(self._tokens.digest(token), now)
            if user_id is None:
                self._events.log(
                    BusinessEvent.denied(
                        catalog.EMAIL_VERIFICATION_FAILED,
                        catalog.REASON_INVALID_TOKEN,
                        resource_type=catalog.RESOURCE_VERIFICATION,
                    )
                )
                raise InvalidVerificationTokenError
            work.users.mark_email_verified(user_id, now)
            work.commit()
        self._events.log(
            BusinessEvent.success(
                catalog.EMAIL_VERIFIED,
                resource_type=catalog.RESOURCE_ACCOUNT,
                resource_id=str(user_id),
            )
        )
