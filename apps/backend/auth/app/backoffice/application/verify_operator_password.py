from dataclasses import dataclass, field
from datetime import datetime
from uuid import uuid4

from app.backoffice.application import backoffice_events as catalog
from app.backoffice.application.backoffice_errors import BackofficeRefusedError
from app.backoffice.application.unit_of_work_factory import UnitOfWorkFactory
from app.backoffice.domain.entities.login_challenge import LoginChallenge
from app.backoffice.domain.interfaces.challenge_token_generator import ChallengeTokenGenerator
from app.core.events.business_event import BusinessEvent
from app.core.events.business_event_logger import BusinessEventLogger
from app.lockout.application.lockout_service import LockoutService
from app.lockout.application.lockout_steps import STEP_FACE, STEP_OPERATOR_PASSWORD
from app.lockout.domain.entities.lockout_subject import LockoutSubject
from app.lockout.domain.enums.subject_type import SubjectType
from app.login.application.unit_of_work_factory import UnitOfWorkFactory as AccountsUnitOfWork
from app.login.domain.entities.access_token_claims import AccessTokenClaims
from app.login.domain.entities.account import Account
from app.login.domain.interfaces.access_token_signer import AccessTokenSigner
from app.login.domain.interfaces.clock import Clock
from app.login.domain.interfaces.password_verifier import PasswordVerifier

OPERATOR_ROLE = "operator"


@dataclass(frozen=True)
class BackofficeSession:
    """Jeton d'acces de l'operateur (`roles=[operator]`, `amr=[face, pwd]`). Pas de jeton de
    rafraichissement : une session du back-office ne se prolonge pas sans repasser le visage."""

    access_token: str = field(repr=False)
    expires_in: int


class VerifyOperatorPasswordUseCase:
    """Troisieme et dernier temps : le mot de passe, jamais avant le visage.

    Le defi est PRIS (usage unique) : un mot de passe faux, un defi sans `face_ok`, une etape
    verrouillee le detruisent. Un defi sans `face_ok` est refuse meme avec le bon mot de passe, sans
    compter comme un mot de passe faux (le visiteur n'est pas arrive jusque-la), et paie la meme
    verification argon2id. Au succes, tous les compteurs de la personne et de son adresse sont remis a
    zero en une transaction et le jeton portant `operator` et `amr` est emis : c'est la seule porte
    qui delivre ce role.
    """

    def __init__(
        self,
        accounts: AccountsUnitOfWork,
        unit_of_work: UnitOfWorkFactory,
        tokens: ChallengeTokenGenerator,
        verifier: PasswordVerifier,
        signer: AccessTokenSigner,
        lockout: LockoutService,
        clock: Clock,
        events: BusinessEventLogger,
        access_ttl_seconds: int,
    ) -> None:
        self._accounts = accounts
        self._unit_of_work = unit_of_work
        self._tokens = tokens
        self._verifier = verifier
        self._signer = signer
        self._lockout = lockout
        self._clock = clock
        self._events = events
        self._access_ttl = access_ttl_seconds

    def execute(
        self, challenge_id: str, password: str, client_ip: str | None = None
    ) -> BackofficeSession:
        now = self._clock.now()
        with self._unit_of_work() as work:
            challenge = work.challenges.take(self._tokens.digest(challenge_id), now)
            work.commit()
        if challenge is None:
            self._verifier.verify_decoy(password)
            raise self._refuse(catalog.REASON_INVALID_CHALLENGE, None, client_ip, None)
        if not challenge.face_ok or challenge.decoy:
            self._verifier.verify_decoy(password)
            raise self._refuse(catalog.REASON_FACE_REQUIRED, challenge, client_ip, None)
        if self._locked(challenge, now):
            self._verifier.verify_decoy(password)
            self._events.log(self._lock_event(challenge, client_ip))
            raise self._refuse(catalog.REASON_STEP_LOCKED, challenge, client_ip, None)
        account = self._account_of(challenge)
        if account is None or account.disabled or account.role != OPERATOR_ROLE:
            self._verifier.verify_decoy(password)
            cause = catalog.CAUSE_ACCOUNT_DISABLED
            raise self._failed(challenge, client_ip, cause, now)
        if not self._verifier.verify(account.password_hash, password):
            raise self._failed(challenge, client_ip, catalog.REASON_WRONG_PASSWORD, now)
        return self._open_session(account, challenge, now)

    def _account_of(self, challenge: LoginChallenge) -> Account | None:
        if challenge.account_id is None:
            return None
        with self._accounts() as work:
            return work.accounts.find_by_id(challenge.account_id)

    def _open_session(
        self, account: Account, challenge: LoginChallenge, now: datetime
    ) -> BackofficeSession:
        self._lockout.clear(
            [
                LockoutSubject(STEP_OPERATOR_PASSWORD, challenge.email_hash),
                LockoutSubject(STEP_FACE, challenge.email_hash),
                LockoutSubject(
                    STEP_OPERATOR_PASSWORD, challenge.address_hash, SubjectType.SOURCE_ADDRESS
                ),
                LockoutSubject(STEP_FACE, challenge.address_hash, SubjectType.SOURCE_ADDRESS),
            ]
        )
        claims = AccessTokenClaims.issue_operator(account, now, self._access_ttl, str(uuid4()))
        self._events.log(
            BusinessEvent.success(
                catalog.BACKOFFICE_PASSWORD_RESULT,
                resource_type=catalog.RESOURCE_ACCOUNT,
                resource_id=str(account.id),
                actor_type=catalog.ACTOR_USER,
                actor_id=str(account.id),
                attributes={"email_hash": challenge.email_hash, "step": STEP_OPERATOR_PASSWORD},
            )
        )
        return BackofficeSession(self._signer.sign(claims), self._access_ttl)

    def _locked(self, challenge: LoginChallenge, now: datetime) -> bool:
        by_account = self._lockout.check(STEP_OPERATOR_PASSWORD, challenge.email_hash, now)
        by_address = self._lockout.check(
            STEP_OPERATOR_PASSWORD, challenge.address_hash, now, SubjectType.SOURCE_ADDRESS
        )
        return by_account.locked or by_address.locked

    def _failed(
        self, challenge: LoginChallenge, client_ip: str | None, cause: str, now: datetime
    ) -> BackofficeRefusedError:
        account_status = self._lockout.record_failure(
            STEP_OPERATOR_PASSWORD, challenge.email_hash, now, client_ip=client_ip
        )
        address_status = self._lockout.record_failure(
            STEP_OPERATOR_PASSWORD,
            challenge.address_hash,
            now,
            SubjectType.SOURCE_ADDRESS,
            client_ip,
        )
        if account_status.just_locked or address_status.just_locked:
            self._events.log(self._lock_event(challenge, client_ip))
        return self._refuse(catalog.REASON_WRONG_PASSWORD, challenge, client_ip, cause)

    def _lock_event(self, challenge: LoginChallenge, client_ip: str | None) -> BusinessEvent:
        return BusinessEvent.denied(
            catalog.BACKOFFICE_LOCKOUT,
            catalog.REASON_STEP_LOCKED,
            resource_type=catalog.RESOURCE_CHALLENGE,
            client_ip=client_ip,
            attributes={
                "email_hash": challenge.email_hash,
                "step": STEP_OPERATOR_PASSWORD,
            },
        )

    def _refuse(
        self,
        reason: str,
        challenge: LoginChallenge | None,
        client_ip: str | None,
        cause: str | None,
    ) -> BackofficeRefusedError:
        attributes: dict[str, str | bool | int | float | None] = {"step": STEP_OPERATOR_PASSWORD}
        if challenge is not None:
            attributes["email_hash"] = challenge.email_hash
        if cause:
            attributes["cause"] = cause
        self._events.log(
            BusinessEvent.denied(
                catalog.BACKOFFICE_PASSWORD_RESULT,
                reason,
                resource_type=catalog.RESOURCE_CHALLENGE,
                client_ip=client_ip,
                attributes=attributes,
            )
        )
        return BackofficeRefusedError()
