from app.core.events.business_event import BusinessEvent
from app.core.events.business_event_logger import BusinessEventLogger
from app.service_token.domain.entities.token_claims import TokenClaims
from app.service_token.domain.enums.service_token_event import ServiceTokenEvent
from app.service_token.domain.enums.token_use import TokenUse
from app.service_token.domain.exceptions.invalid_token_error import InvalidTokenError
from app.service_token.domain.interfaces.clock import Clock
from app.service_token.domain.interfaces.token_decoder import TokenDecoder


class VerifyTokenUseCase:
    """Vérifie un jeton signé par `auth` pour un usage donné (service ou client).

    Un jeton n'est accepté que si sa nature (`token_use`) correspond à l'usage attendu : un jeton
    client ne passe jamais pour un jeton de service, et inversement, même signés par la même clé.
    Le refus ne détaille jamais la cause à l'appelant (elle est journalisée sans le jeton).
    """

    def __init__(
        self,
        decoder: TokenDecoder,
        clock: Clock,
        expected_use: TokenUse,
        issuer: str,
        events: BusinessEventLogger,
    ) -> None:
        self._decoder = decoder
        self._clock = clock
        self._expected_use = expected_use
        self._issuer = issuer
        self._events = events

    def execute(self, token: str, audience: str, required_scope: str | None = None) -> TokenClaims:
        claims = self._decoder.decode(token)
        reason = self._refusal_reason(claims, audience, required_scope)
        if reason is not None:
            self._events.log(
                BusinessEvent.denied(
                    ServiceTokenEvent.VERIFICATION_DENIED, reason, resource_type="service_token"
                )
            )
            raise InvalidTokenError
        return claims

    def _refusal_reason(
        self, claims: TokenClaims, audience: str, required_scope: str | None
    ) -> str | None:
        now = int(self._clock.now().timestamp())
        checks = (
            ("expired", claims.expires_at <= now),
            ("issued_in_future", claims.issued_at > now),
            ("issuer", claims.issuer != self._issuer),
            ("token_use", claims.token_use is not self._expected_use),
            ("audience", claims.audience != audience),
            ("scope", required_scope is not None and required_scope not in claims.scopes),
        )
        return next((reason for reason, failed in checks if failed), None)
