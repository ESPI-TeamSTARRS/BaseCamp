from uuid import uuid4

from app.core.events.business_event import BusinessEvent
from app.core.events.business_event_logger import BusinessEventLogger
from app.login.application import login_events as catalog
from app.login.application.login_result import LoginResult
from app.login.application.unit_of_work_factory import UnitOfWorkFactory
from app.login.domain.entities.access_token_claims import AccessTokenClaims
from app.login.domain.entities.account import Account
from app.login.domain.entities.refresh_token import RefreshToken
from app.login.domain.exceptions.invalid_credentials_error import InvalidCredentialsError
from app.login.domain.interfaces.access_token_signer import AccessTokenSigner
from app.login.domain.interfaces.clock import Clock
from app.login.domain.interfaces.email_fingerprinter import EmailFingerprinter
from app.login.domain.interfaces.password_verifier import PasswordVerifier
from app.login.domain.interfaces.refresh_token_generator import RefreshTokenGenerator


class LoginAccountUseCase:
    """Connexion sans enumeration : email inconnu, mauvais mot de passe et compte desactive
    donnent la meme erreur et coutent une verification argon2id chacun. Le motif interne
    n'existe que dans l'evenement `auth.login_failed` (attribut `cause`).
    """

    def __init__(
        self,
        unit_of_work: UnitOfWorkFactory,
        verifier: PasswordVerifier,
        signer: AccessTokenSigner,
        refresh_tokens: RefreshTokenGenerator,
        clock: Clock,
        events: BusinessEventLogger,
        fingerprinter: EmailFingerprinter,
        access_ttl_seconds: int,
        refresh_ttl_seconds: int,
    ) -> None:
        self._unit_of_work = unit_of_work
        self._verifier = verifier
        self._signer = signer
        self._refresh_tokens = refresh_tokens
        self._clock = clock
        self._events = events
        self._fingerprinter = fingerprinter
        self._access_ttl = access_ttl_seconds
        self._refresh_ttl = refresh_ttl_seconds

    def execute(self, email: str, password: str, client_ip: str | None = None) -> LoginResult:
        address = email.strip().lower()
        account = self._authenticate(address, password, client_ip)
        return self._open_session(account, password, address)

    def _authenticate(self, address: str, password: str, client_ip: str | None) -> Account:
        """Toujours exactement une verification argon2id, quelle que soit l'issue."""
        with self._unit_of_work() as work:
            account = work.accounts.find_by_email(address)
        if account is None:
            self._verifier.verify_decoy(password)
            raise self._refuse(address, None, catalog.CAUSE_UNKNOWN_ACCOUNT, client_ip)
        if not self._verifier.verify(account.password_hash, password):
            raise self._refuse(address, account, catalog.CAUSE_WRONG_PASSWORD, client_ip)
        if account.disabled:
            raise self._refuse(address, account, catalog.CAUSE_ACCOUNT_DISABLED, client_ip)
        return account

    def _refuse(
        self, address: str, account: Account | None, cause: str, client_ip: str | None
    ) -> InvalidCredentialsError:
        self._events.log(
            BusinessEvent.denied(
                catalog.LOGIN_FAILED,
                catalog.REASON_INVALID_CREDENTIALS,
                resource_type=catalog.RESOURCE_ACCOUNT,
                resource_id=str(account.id) if account else None,
                client_ip=client_ip,
                attributes={"email_hash": self._fingerprinter.fingerprint(address), "cause": cause},
            )
        )
        return InvalidCredentialsError()

    def _open_session(self, account: Account, password: str, address: str) -> LoginResult:
        now = self._clock.now()
        claims = AccessTokenClaims.issue(account, now, self._access_ttl, str(uuid4()))
        raw_refresh = self._refresh_tokens.generate()
        upgraded = self._verifier.needs_rehash(account.password_hash)
        with self._unit_of_work() as work:
            if upgraded:
                work.accounts.update_password_hash(account.id, self._verifier.hash(password))
            work.refresh_tokens.add(
                RefreshToken.issue(
                    account.id, self._refresh_tokens.digest(raw_refresh), now, self._refresh_ttl
                )
            )
            work.commit()
        self._events.log(self._succeeded(account, address, upgraded))
        return LoginResult(
            self._signer.sign(claims), self._access_ttl, raw_refresh, self._refresh_ttl
        )

    def _succeeded(self, account: Account, address: str, upgraded: bool) -> BusinessEvent:
        return BusinessEvent.success(
            catalog.LOGIN_SUCCEEDED,
            resource_type=catalog.RESOURCE_ACCOUNT,
            resource_id=str(account.id),
            actor_type=catalog.ACTOR_USER,
            actor_id=str(account.id),
            attributes={
                "email_hash": self._fingerprinter.fingerprint(address),
                "hash_upgraded": upgraded,
            },
        )
