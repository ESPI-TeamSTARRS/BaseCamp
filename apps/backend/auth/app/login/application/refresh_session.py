from datetime import datetime
from uuid import uuid4

from app.core.events.business_event import BusinessEvent
from app.core.events.business_event_logger import BusinessEventLogger
from app.login.application import login_events as catalog
from app.login.application.invalid_refresh_token_error import InvalidRefreshTokenError
from app.login.application.login_result import LoginResult
from app.login.application.unit_of_work_factory import UnitOfWorkFactory
from app.login.domain.entities.access_token_claims import AccessTokenClaims
from app.login.domain.interfaces.access_token_signer import AccessTokenSigner
from app.login.domain.interfaces.clock import Clock
from app.login.domain.interfaces.refresh_token_generator import RefreshTokenGenerator
from app.login.domain.interfaces.unit_of_work import UnitOfWork


class RefreshSessionUseCase:
    """Echange un jeton de rafraichissement contre un nouveau couple de jetons (rotation).

    Le jeton presente est consomme atomiquement; s'il l'a deja ete, c'est un rejeu : toute la
    famille est revoquee. Toute autre cause d'echec (inconnu, expire, compte desactive ou
    disparu) donne la meme erreur; le motif n'existe que dans l'evenement journalise.
    """

    def __init__(
        self,
        unit_of_work: UnitOfWorkFactory,
        signer: AccessTokenSigner,
        refresh_tokens: RefreshTokenGenerator,
        clock: Clock,
        events: BusinessEventLogger,
        access_ttl_seconds: int,
        refresh_ttl_seconds: int,
    ) -> None:
        self._unit_of_work = unit_of_work
        self._signer = signer
        self._refresh_tokens = refresh_tokens
        self._clock = clock
        self._events = events
        self._access_ttl = access_ttl_seconds
        self._refresh_ttl = refresh_ttl_seconds

    def execute(self, raw_token: str, client_ip: str | None = None) -> LoginResult:
        now = self._clock.now()
        digest = self._refresh_tokens.digest(raw_token)
        with self._unit_of_work() as work:
            consumed = work.refresh_tokens.consume(digest, now)
            if consumed is None:
                self._reject_unusable(work, digest, now, client_ip)
                raise InvalidRefreshTokenError
            account = work.accounts.find_by_id(consumed.user_id)
            if account is None or account.disabled:
                work.refresh_tokens.revoke_family(consumed.family_id)
                work.commit()
                self._deny(catalog.CAUSE_ACCOUNT_DISABLED, str(consumed.user_id), client_ip)
                raise InvalidRefreshTokenError
            raw_next = self._refresh_tokens.generate()
            work.refresh_tokens.add(
                consumed.successor(self._refresh_tokens.digest(raw_next), now, self._refresh_ttl)
            )
            work.commit()
        claims = AccessTokenClaims.issue(account, now, self._access_ttl, str(uuid4()))
        self._events.log(
            BusinessEvent.success(
                catalog.TOKEN_REFRESHED,
                resource_type=catalog.RESOURCE_ACCOUNT,
                resource_id=str(account.id),
                actor_type=catalog.ACTOR_USER,
                actor_id=str(account.id),
                client_ip=client_ip,
            )
        )
        return LoginResult(self._signer.sign(claims), self._access_ttl, raw_next, self._refresh_ttl)

    def _reject_unusable(
        self, work: UnitOfWork, digest: str, now: datetime, client_ip: str | None
    ) -> None:
        """Jeton non consommable : rejeu (famille revoquee), expire ou inconnu."""
        known = work.refresh_tokens.find_by_hash(digest)
        if known is None:
            self._deny(catalog.CAUSE_UNKNOWN_TOKEN, None, client_ip)
        elif known.used_at is not None and not known.expired(now):
            work.refresh_tokens.revoke_family(known.family_id)
            work.commit()
            self._events.log(
                BusinessEvent.denied(
                    catalog.REFRESH_REUSE_DETECTED,
                    catalog.REASON_REFRESH_REUSED,
                    resource_type=catalog.RESOURCE_ACCOUNT,
                    resource_id=str(known.user_id),
                    client_ip=client_ip,
                )
            )
        else:
            self._deny(catalog.CAUSE_EXPIRED_TOKEN, str(known.user_id), client_ip)

    def _deny(self, cause: str, account_id: str | None, client_ip: str | None) -> None:
        self._events.log(
            BusinessEvent.denied(
                catalog.REFRESH_REJECTED,
                catalog.REASON_INVALID_REFRESH_TOKEN,
                resource_type=catalog.RESOURCE_REFRESH_TOKEN,
                client_ip=client_ip,
                attributes={"cause": cause, "account_id": account_id},
            )
        )
