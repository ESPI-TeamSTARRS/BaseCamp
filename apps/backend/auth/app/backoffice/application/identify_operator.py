from dataclasses import dataclass, field

from app.backoffice.application import backoffice_events as catalog
from app.backoffice.application.unit_of_work_factory import UnitOfWorkFactory
from app.backoffice.domain.entities.login_challenge import LoginChallenge
from app.backoffice.domain.interfaces.challenge_token_generator import ChallengeTokenGenerator
from app.core.events.business_event import BusinessEvent
from app.core.events.business_event_logger import BusinessEventLogger
from app.login.application.unit_of_work_factory import UnitOfWorkFactory as AccountsUnitOfWork
from app.login.domain.interfaces.clock import Clock
from app.login.domain.interfaces.email_fingerprinter import EmailFingerprinter

OPERATOR_ROLE = "operator"
UNKNOWN_ADDRESS = "unknown"


@dataclass(frozen=True)
class Identified:
    """Defi remis au client : l'identifiant opaque (une seule fois) et sa duree de vie."""

    challenge_id: str = field(repr=False)
    expires_in: int


class IdentifyOperatorUseCase:
    """Premier temps : repond TOUJOURS par un defi, que le compte existe ou non.

    Un operateur actif obtient un vrai defi; un identifiant inconnu, un compte sans le role operateur
    ou desactive obtient un defi LEURRE, indiscernable (meme forme, meme duree de vie, meme travail
    en base : une lecture de compte puis une insertion de defi). Le visage presente ensuite sera
    refuse et comptera comme un visage faux.
    """

    def __init__(
        self,
        accounts: AccountsUnitOfWork,
        unit_of_work: UnitOfWorkFactory,
        tokens: ChallengeTokenGenerator,
        fingerprinter: EmailFingerprinter,
        clock: Clock,
        events: BusinessEventLogger,
        ttl_seconds: int,
    ) -> None:
        self._accounts = accounts
        self._unit_of_work = unit_of_work
        self._tokens = tokens
        self._fingerprinter = fingerprinter
        self._clock = clock
        self._events = events
        self._ttl = ttl_seconds

    def execute(self, email: str, client_ip: str | None = None) -> Identified:
        address = email.strip().lower()
        with self._accounts() as work:
            account = work.accounts.find_by_email(address)
        eligible = account is not None and account.role == OPERATOR_ROLE and not account.disabled
        email_hash = self._fingerprinter.fingerprint(address)
        now = self._clock.now()
        raw = self._tokens.generate()
        challenge = LoginChallenge.issue(
            self._tokens.digest(raw),
            account.id if account is not None and eligible else None,
            email_hash,
            self._fingerprinter.fingerprint(f"ip:{client_ip or UNKNOWN_ADDRESS}"),
            now,
            self._ttl,
        )
        with self._unit_of_work() as work:
            work.challenges.purge_expired(now)
            work.challenges.add(challenge)
            work.commit()
        self._events.log(
            BusinessEvent.success(
                catalog.BACKOFFICE_IDENTIFY,
                resource_type=catalog.RESOURCE_CHALLENGE,
                attributes={"email_hash": email_hash, "step": "identify"},
            )
        )
        return Identified(raw, self._ttl)
