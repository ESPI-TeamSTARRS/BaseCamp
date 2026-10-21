import secrets
import uuid
from datetime import datetime, timedelta

from app.core.events.business_event import BusinessEvent
from app.core.events.business_event_logger import BusinessEventLogger
from app.service_token.application.commands.issue_service_token_command import (
    IssueServiceTokenCommand,
)
from app.service_token.domain.entities.issued_token import IssuedToken
from app.service_token.domain.entities.service_client import ServiceClient
from app.service_token.domain.entities.token_claims import TokenClaims
from app.service_token.domain.enums.denial_reason import DenialReason
from app.service_token.domain.enums.service_audience import ServiceAudience
from app.service_token.domain.enums.service_scope import ServiceScope
from app.service_token.domain.enums.service_token_event import ServiceTokenEvent
from app.service_token.domain.enums.token_use import TokenUse
from app.service_token.domain.exceptions.invalid_client_credentials_error import (
    InvalidClientCredentialsError,
)
from app.service_token.domain.exceptions.rate_limit_exceeded_error import RateLimitExceededError
from app.service_token.domain.interfaces.clock import Clock
from app.service_token.domain.interfaces.rate_limiter import RateLimiter
from app.service_token.domain.interfaces.secret_hasher import SecretHasher
from app.service_token.domain.interfaces.service_client_repository import ServiceClientRepository
from app.service_token.domain.interfaces.token_signer import TokenSigner

TOKEN_TTL = timedelta(minutes=5)
RESOURCE_TYPE = "service_client"


class IssueServiceTokenUseCase:
    """Émet un jeton de service (client_credentials) après contrôle du débit puis du secret.

    Client inconnu et mauvais secret suivent le même chemin : deux vérifications d'empreinte
    (courante et précédente, contre une empreinte factice si absente), puis la même erreur.
    """

    def __init__(
        self,
        repository: ServiceClientRepository,
        hasher: SecretHasher,
        rate_limiter: RateLimiter,
        signer: TokenSigner,
        clock: Clock,
        issuer: str,
        events: BusinessEventLogger,
    ) -> None:
        self._repository = repository
        self._hasher = hasher
        self._rate_limiter = rate_limiter
        self._signer = signer
        self._clock = clock
        self._issuer = issuer
        self._events = events
        self._decoy_hash = hasher.hash(secrets.token_urlsafe(32))

    def execute(self, command: IssueServiceTokenCommand) -> IssuedToken:
        now = self._clock.now()
        decision = self._rate_limiter.hit(command.client_id, now)
        if not decision.allowed:
            self._events.log(
                BusinessEvent.denied(
                    ServiceTokenEvent.RATE_LIMITED,
                    DenialReason.RATE_LIMIT_EXCEEDED,
                    resource_type=RESOURCE_TYPE,
                    resource_id=command.client_id,
                    attributes={"retry_after_seconds": decision.retry_after_seconds},
                )
            )
            raise RateLimitExceededError(decision.retry_after_seconds)
        client = self._repository.find_by_id(command.client_id)
        secret_valid = self._secret_is_valid(client, command.client_secret)
        audience, scopes = self._parse_request(command)
        reason = self._denial_reason(client, secret_valid, audience, scopes)
        if client is None or reason is not None or audience is None or scopes is None:
            self._events.log(
                BusinessEvent.denied(
                    ServiceTokenEvent.DENIED,
                    reason or DenialReason.SCOPE_NOT_ALLOWED,
                    resource_type=RESOURCE_TYPE,
                    resource_id=command.client_id,
                )
            )
            raise InvalidClientCredentialsError
        return self._issue(client, command, scopes, now)

    def _issue(
        self,
        client: ServiceClient,
        command: IssueServiceTokenCommand,
        scopes: frozenset[ServiceScope],
        now: datetime,
    ) -> IssuedToken:
        issued_at = int(now.timestamp())
        ttl = int(TOKEN_TTL.total_seconds())
        claims = TokenClaims(
            subject=client.client_id,
            audience=command.audience,
            scopes=frozenset(scope.value for scope in scopes),
            issuer=self._issuer,
            issued_at=issued_at,
            expires_at=issued_at + ttl,
            token_id=uuid.uuid4().hex,
            token_use=TokenUse.SERVICE,
        )
        scope = " ".join(sorted(scope.value for scope in scopes))
        token = IssuedToken(self._signer.sign(claims), ttl, scope)
        self._events.log(
            BusinessEvent.success(
                ServiceTokenEvent.ISSUED,
                resource_type=RESOURCE_TYPE,
                resource_id=client.client_id,
                actor_type="service",
                actor_id=client.client_id,
                attributes={
                    "audience": claims.audience,
                    "scope": scope,
                    "jti": claims.token_id,
                    "expires_in": ttl,
                },
            )
        )
        return token

    def _secret_is_valid(self, client: ServiceClient | None, secret: str) -> bool:
        current = client.current_secret_hash if client else None
        previous = client.previous_secret_hash if client else None
        # Les deux vérifications ont toujours lieu : aucune sortie anticipée mesurable.
        current_ok = self._verify(current, secret)
        previous_ok = self._verify(previous, secret)
        return current_ok | previous_ok

    def _verify(self, secret_hash: str | None, secret: str) -> bool:
        matches = self._hasher.verify(secret_hash or self._decoy_hash, secret)
        return matches and secret_hash is not None

    @staticmethod
    def _parse_request(
        command: IssueServiceTokenCommand,
    ) -> tuple[ServiceAudience | None, frozenset[ServiceScope] | None]:
        try:
            audience: ServiceAudience | None = ServiceAudience(command.audience)
        except ValueError:
            audience = None
        try:
            scopes: frozenset[ServiceScope] | None = frozenset(
                ServiceScope(scope) for scope in command.scope.split()
            )
        except ValueError:
            scopes = None
        return audience, scopes

    @staticmethod
    def _denial_reason(
        client: ServiceClient | None,
        secret_valid: bool,
        audience: ServiceAudience | None,
        scopes: frozenset[ServiceScope] | None,
    ) -> DenialReason | None:
        """Motif interne (journal seulement); precedence : client, secret, audience, scope."""
        if client is None:
            return DenialReason.UNKNOWN_CLIENT
        if not secret_valid:
            return DenialReason.INVALID_SECRET
        if audience is None:
            return DenialReason.UNKNOWN_AUDIENCE
        if not scopes or not scopes <= client.scopes:
            return DenialReason.SCOPE_NOT_ALLOWED
        if any(scope.audience is not audience for scope in scopes):
            return DenialReason.SCOPE_NOT_ALLOWED
        return None
