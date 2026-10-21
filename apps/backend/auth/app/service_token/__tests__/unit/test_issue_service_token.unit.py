from datetime import UTC, datetime

import pytest

from app.core.__tests__.in_memory_business_event_logger import InMemoryBusinessEventLogger
from app.core.events.outcome import Outcome
from app.service_token.application.commands.issue_service_token_command import (
    IssueServiceTokenCommand,
)
from app.service_token.application.issue_service_token import IssueServiceTokenUseCase
from app.service_token.domain.entities.rate_limit_decision import RateLimitDecision
from app.service_token.domain.entities.service_client import ServiceClient
from app.service_token.domain.entities.token_claims import TokenClaims
from app.service_token.domain.enums.service_scope import ServiceScope
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

NOW = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
CURRENT = "current-secret-0123456789-0123456789"
PREVIOUS = "previous-secret-0123456789-0123456789"
WRONG = "wrong-secret-0123456789-0123456789-0"
SIGNED_TOKEN = "header.payload.signature-do-not-log"


class FakeHasher(SecretHasher):
    def __init__(self) -> None:
        self.verify_calls = 0

    def hash(self, secret: str) -> str:
        return f"hash:{secret}"

    def verify(self, secret_hash: str, secret: str) -> bool:
        self.verify_calls += 1
        return secret_hash == f"hash:{secret}"


class FakeRepository(ServiceClientRepository):
    def __init__(self, *clients: ServiceClient) -> None:
        self.clients = {client.client_id: client for client in clients}
        self.lookups = 0

    def find_by_id(self, client_id: str) -> ServiceClient | None:
        self.lookups += 1
        return self.clients.get(client_id)

    def save(self, client: ServiceClient) -> None:
        self.clients[client.client_id] = client


class FakeLimiter(RateLimiter):
    def __init__(self, blocked: set[str] | None = None) -> None:
        self.blocked = blocked or set()
        self.hits: list[str] = []

    def hit(self, client_id: str, now: datetime) -> RateLimitDecision:
        self.hits.append(client_id)
        if client_id in self.blocked:
            return RateLimitDecision(allowed=False, retry_after_seconds=42)
        return RateLimitDecision(allowed=True, retry_after_seconds=0)


class FakeSigner(TokenSigner):
    def __init__(self) -> None:
        self.claims: list[TokenClaims] = []

    def sign(self, claims: TokenClaims) -> str:
        self.claims.append(claims)
        return SIGNED_TOKEN


class FixedClock(Clock):
    def now(self) -> datetime:
        return NOW


def _client(
    client_id: str = "shop",
    scopes: frozenset[ServiceScope] = frozenset({ServiceScope.PAYMENTS_WRITE}),
    previous: str | None = PREVIOUS,
) -> ServiceClient:
    return ServiceClient(
        client_id, scopes, f"hash:{CURRENT}", None if previous is None else f"hash:{previous}"
    )


def _command(
    client_id: str = "shop",
    secret: str = CURRENT,
    audience: str = "payment",
    scope: str = "payments:write",
) -> IssueServiceTokenCommand:
    return IssueServiceTokenCommand(client_id, secret, audience, scope)


class Setup:
    def __init__(self, *clients: ServiceClient, blocked: set[str] | None = None) -> None:
        self.hasher = FakeHasher()
        self.repository = FakeRepository(*clients)
        self.limiter = FakeLimiter(blocked)
        self.signer = FakeSigner()
        self.events = InMemoryBusinessEventLogger()
        self.use_case = IssueServiceTokenUseCase(
            self.repository,
            self.hasher,
            self.limiter,
            self.signer,
            FixedClock(),
            "basecamp-auth",
            self.events,
        )


class TestIssue:
    def test_issues_a_five_minute_token_with_the_expected_claims(self) -> None:
        setup = Setup(_client())

        issued = setup.use_case.execute(_command())

        assert issued.access_token == SIGNED_TOKEN
        assert issued.expires_in == 300
        assert issued.scope == "payments:write"
        claims = setup.signer.claims[0]
        assert claims.subject == "shop"
        assert claims.audience == "payment"
        assert claims.scopes == frozenset({"payments:write"})
        assert claims.issuer == "basecamp-auth"
        assert claims.issued_at == int(NOW.timestamp())
        assert claims.expires_at == claims.issued_at + 300
        assert claims.token_use is TokenUse.SERVICE
        assert claims.token_id

    def test_each_token_has_a_distinct_identifier(self) -> None:
        setup = Setup(_client())

        setup.use_case.execute(_command())
        setup.use_case.execute(_command())

        assert setup.signer.claims[0].token_id != setup.signer.claims[1].token_id

    def test_the_previous_secret_is_still_accepted_during_rotation(self) -> None:
        setup = Setup(_client())

        issued = setup.use_case.execute(_command(secret=PREVIOUS))

        assert issued.access_token == SIGNED_TOKEN

    def test_a_client_without_previous_secret_only_accepts_the_current_one(self) -> None:
        setup = Setup(_client(previous=None))

        assert setup.use_case.execute(_command()).access_token == SIGNED_TOKEN
        with pytest.raises(InvalidClientCredentialsError):
            setup.use_case.execute(_command(secret=PREVIOUS))


class TestRefusals:
    @pytest.mark.parametrize(
        "command",
        [
            _command(secret=WRONG),
            _command(client_id="unknown"),
            _command(scope="payments:read"),
            _command(scope="unknown:scope"),
            _command(scope=""),
            _command(audience="shop"),
            _command(audience="unknown"),
            _command(audience=""),
        ],
        ids=[
            "bad-secret",
            "unknown-client",
            "scope-not-granted-to-client",
            "unknown-scope",
            "empty-scope",
            "audience-does-not-match-scope",
            "unknown-audience",
            "empty-audience",
        ],
    )
    def test_refuses_with_the_single_generic_error_and_signs_nothing(
        self, command: IssueServiceTokenCommand
    ) -> None:
        setup = Setup(_client())

        with pytest.raises(InvalidClientCredentialsError):
            setup.use_case.execute(command)

        assert setup.signer.claims == []

    def test_a_scope_not_granted_to_the_client_is_refused(self) -> None:
        setup = Setup(_client(scopes=frozenset()))

        with pytest.raises(InvalidClientCredentialsError):
            setup.use_case.execute(_command())

    def test_unknown_client_and_bad_secret_do_the_same_hashing_work(self) -> None:
        unknown = Setup(_client())
        bad_secret = Setup(_client())

        with pytest.raises(InvalidClientCredentialsError):
            unknown.use_case.execute(_command(client_id="unknown"))
        with pytest.raises(InvalidClientCredentialsError):
            bad_secret.use_case.execute(_command(secret=WRONG))

        assert unknown.hasher.verify_calls == bad_secret.hasher.verify_calls == 2

    def test_a_client_without_previous_secret_still_does_two_verifications(self) -> None:
        setup = Setup(_client(previous=None))

        setup.use_case.execute(_command())

        assert setup.hasher.verify_calls == 2


class TestRateLimit:
    def test_exceeding_the_limit_is_refused_before_any_hashing(self) -> None:
        setup = Setup(_client(), blocked={"shop"})

        with pytest.raises(RateLimitExceededError) as raised:
            setup.use_case.execute(_command())

        assert raised.value.retry_after_seconds == 42
        assert setup.hasher.verify_calls == 0
        assert setup.repository.lookups == 0

    def test_another_client_is_unaffected_by_a_blocked_client(self) -> None:
        setup = Setup(_client(), _client("billing"), blocked={"shop"})

        issued = setup.use_case.execute(_command(client_id="billing"))

        assert issued.access_token == SIGNED_TOKEN

    def test_the_presented_client_id_is_counted_even_when_unknown(self) -> None:
        setup = Setup(_client())

        with pytest.raises(InvalidClientCredentialsError):
            setup.use_case.execute(_command(client_id="ghost"))

        assert setup.limiter.hits == ["ghost"]


class TestBusinessEvents:
    def test_issuance_emits_the_issued_event_without_secret_or_token(self) -> None:
        setup = Setup(_client())

        setup.use_case.execute(_command())

        [event] = setup.events.events
        assert event.event == "auth.service_token_issued"
        assert event.outcome is Outcome.SUCCESS
        assert event.reason is None
        assert (event.resource_type, event.resource_id) == ("service_client", "shop")
        assert (event.actor_type, event.actor_id) == ("service", "shop")
        assert event.attributes == {
            "audience": "payment",
            "scope": "payments:write",
            "jti": setup.signer.claims[0].token_id,
            "expires_in": 300,
        }
        assert _no_sensitive_value(setup)

    @pytest.mark.parametrize(
        ("command", "reason"),
        [
            (_command(client_id="ghost"), "unknown_client"),
            (_command(secret=WRONG), "invalid_secret"),
            (_command(scope="payments:read"), "scope_not_allowed"),
            (_command(scope="unknown:scope"), "scope_not_allowed"),
            (_command(scope=""), "scope_not_allowed"),
            (_command(audience="unknown"), "unknown_audience"),
            (_command(audience=""), "unknown_audience"),
        ],
    )
    def test_each_denial_has_its_own_internal_reason(
        self, command: IssueServiceTokenCommand, reason: str
    ) -> None:
        setup = Setup(_client())

        with pytest.raises(InvalidClientCredentialsError):
            setup.use_case.execute(command)

        [event] = setup.events.events
        assert event.event == "auth.service_token_denied"
        assert event.outcome is Outcome.DENIED
        assert event.reason == reason
        assert (event.resource_type, event.resource_id) == ("service_client", command.client_id)
        assert _no_sensitive_value(setup)

    def test_a_secret_error_takes_precedence_over_a_scope_error(self) -> None:
        setup = Setup(_client())

        with pytest.raises(InvalidClientCredentialsError):
            setup.use_case.execute(_command(secret=WRONG, scope="payments:read"))

        assert setup.events.events[0].reason == "invalid_secret"

    def test_rate_limiting_emits_a_denied_event_with_the_wait(self) -> None:
        setup = Setup(_client(), blocked={"shop"})

        with pytest.raises(RateLimitExceededError):
            setup.use_case.execute(_command())

        [event] = setup.events.events
        assert event.event == "auth.service_rate_limited"
        assert event.outcome is Outcome.DENIED
        assert event.reason == "rate_limit_exceeded"
        assert event.resource_id == "shop"
        assert event.attributes == {"retry_after_seconds": 42}


def _no_sensitive_value(setup: Setup) -> bool:
    dump = repr(setup.events.events)
    return not any(secret in dump for secret in (CURRENT, PREVIOUS, WRONG, SIGNED_TOKEN))
