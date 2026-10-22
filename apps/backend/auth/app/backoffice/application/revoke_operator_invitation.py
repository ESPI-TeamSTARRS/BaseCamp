from app.backoffice.application import invitation_events as catalog
from app.backoffice.application.invitation_unit_of_work_factory import (
    InvitationUnitOfWorkFactory,
)
from app.core.events.business_event import BusinessEvent
from app.core.events.business_event_logger import BusinessEventLogger
from app.login.domain.interfaces.clock import Clock
from app.login.domain.interfaces.email_fingerprinter import EmailFingerprinter
from app.registration.domain.value_objects.email_address import EmailAddress


class RevokeOperatorInvitationUseCase:
    """Revoque les invitations encore utilisables d'une adresse (commande d'exploitation)."""

    def __init__(
        self,
        unit_of_work: InvitationUnitOfWorkFactory,
        fingerprinter: EmailFingerprinter,
        clock: Clock,
        events: BusinessEventLogger,
    ) -> None:
        self._unit_of_work = unit_of_work
        self._fingerprinter = fingerprinter
        self._clock = clock
        self._events = events

    def execute(self, email: str) -> int:
        """Renvoie le nombre d'invitations revoquees (0 si aucune n'etait utilisable)."""
        address = EmailAddress.of(email).value
        with self._unit_of_work() as work:
            revoked = work.invitations.revoke_active_for(address, self._clock.now())
            work.commit()
        self._events.log(
            BusinessEvent.success(
                catalog.OPERATOR_INVITE_REVOKED,
                resource_type=catalog.RESOURCE_INVITATION,
                actor_type=catalog.ACTOR_CLI,
                attributes={
                    "email_hash": self._fingerprinter.fingerprint(address),
                    "revoked": revoked,
                },
            )
        )
        return revoked
