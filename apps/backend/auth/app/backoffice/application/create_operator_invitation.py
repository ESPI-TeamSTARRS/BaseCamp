from dataclasses import dataclass, field
from datetime import datetime, timedelta

from app.backoffice.application import invitation_events as catalog
from app.backoffice.application.invitation_unit_of_work_factory import (
    InvitationUnitOfWorkFactory,
)
from app.backoffice.domain.entities.operator_invitation import OperatorInvitation
from app.backoffice.domain.interfaces.challenge_token_generator import ChallengeTokenGenerator
from app.core.events.business_event import BusinessEvent
from app.core.events.business_event_logger import BusinessEventLogger
from app.login.application.unit_of_work_factory import UnitOfWorkFactory as AccountsUnitOfWork
from app.login.domain.interfaces.clock import Clock
from app.login.domain.interfaces.email_fingerprinter import EmailFingerprinter
from app.registration.domain.value_objects.email_address import EmailAddress

PURGE_AFTER = timedelta(days=1)


class InvitationAddressTakenError(Exception):
    """L'adresse a deja un compte : inutile d'inviter."""


@dataclass(frozen=True)
class CreatedInvitation:
    """Le lien est affiche une seule fois a l'administrateur IT (jamais journalise)."""

    link: str = field(repr=False)
    expires_at: datetime


class CreateOperatorInvitationUseCase:
    """Cree une invitation d'operateur : commande d'exploitation SEULEMENT (aucune route ne la cree).

    Le jeton est aleatoire (256 bits); seule son empreinte est stockee. Il est lie a l'adresse, vaut 5
    minutes au plus et ne sert qu'une fois. Inviter de nouveau la meme adresse revoque les invitations
    encore utilisables. Pas d'envoi par email : le lien est remis a la personne par l'administrateur.
    """

    def __init__(
        self,
        accounts: AccountsUnitOfWork,
        unit_of_work: InvitationUnitOfWorkFactory,
        tokens: ChallengeTokenGenerator,
        fingerprinter: EmailFingerprinter,
        clock: Clock,
        events: BusinessEventLogger,
        admin_base_url: str,
        ttl_seconds: int,
    ) -> None:
        self._accounts = accounts
        self._unit_of_work = unit_of_work
        self._tokens = tokens
        self._fingerprinter = fingerprinter
        self._clock = clock
        self._events = events
        self._base_url = admin_base_url.rstrip("/")
        self._ttl = ttl_seconds

    def execute(self, email: str) -> CreatedInvitation:
        """Leve `InvalidEmailError` (adresse mal formee) ou `InvitationAddressTakenError`."""
        address = EmailAddress.of(email).value
        email_hash = self._fingerprinter.fingerprint(address)
        with self._accounts() as work:
            existing = work.accounts.find_by_email(address)
        if existing is not None:
            self._events.log(self._refused(catalog.REASON_ACCOUNT_EXISTS, email_hash))
            raise InvitationAddressTakenError
        now = self._clock.now()
        raw = self._tokens.generate()
        invitation = OperatorInvitation.issue(self._tokens.digest(raw), address, now, self._ttl)
        with self._unit_of_work() as work:
            work.invitations.purge_before(now - PURGE_AFTER)
            revoked = work.invitations.revoke_active_for(address, now)
            work.invitations.add(invitation)
            work.commit()
        self._events.log(
            BusinessEvent.success(
                catalog.OPERATOR_INVITE_CREATED,
                resource_type=catalog.RESOURCE_INVITATION,
                actor_type=catalog.ACTOR_CLI,
                attributes={
                    "email_hash": email_hash,
                    "lifetime_seconds": int((invitation.expires_at - now).total_seconds()),
                    "previous_revoked": revoked,
                },
            )
        )
        return CreatedInvitation(f"{self._base_url}/invitation#token={raw}", invitation.expires_at)

    @staticmethod
    def _refused(reason: str, email_hash: str) -> BusinessEvent:
        return BusinessEvent.denied(
            catalog.OPERATOR_INVITE_CREATED,
            reason,
            resource_type=catalog.RESOURCE_INVITATION,
            actor_type=catalog.ACTOR_CLI,
            attributes={"email_hash": email_hash},
        )
