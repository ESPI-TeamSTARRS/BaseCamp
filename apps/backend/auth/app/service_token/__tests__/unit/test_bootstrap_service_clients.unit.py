import pytest

from app.core.__tests__.in_memory_business_event_logger import InMemoryBusinessEventLogger
from app.service_token.application.bootstrap_service_clients import BootstrapServiceClientsUseCase
from app.service_token.domain.entities.client_declaration import ClientDeclaration
from app.service_token.domain.entities.service_client import ServiceClient
from app.service_token.domain.enums.service_scope import ServiceScope
from app.service_token.domain.exceptions.invalid_declaration_error import InvalidDeclarationError
from app.service_token.domain.interfaces.secret_hasher import SecretHasher
from app.service_token.domain.interfaces.service_client_declarations import (
    ServiceClientDeclarations,
)
from app.service_token.domain.interfaces.service_client_repository import ServiceClientRepository

S1 = "secret-one-0123456789-0123456789-01"
S2 = "secret-two-0123456789-0123456789-01"
SCOPES = frozenset({ServiceScope.PAYMENTS_WRITE})


class CountingHasher(SecretHasher):
    def __init__(self) -> None:
        self.hash_calls = 0

    def hash(self, secret: str) -> str:
        self.hash_calls += 1
        # Empreintes salées : deux hachages du même secret diffèrent.
        return f"hash{self.hash_calls}:{secret}"

    def verify(self, secret_hash: str, secret: str) -> bool:
        return secret_hash.split(":", 1)[1] == secret


class MemoryRepository(ServiceClientRepository):
    def __init__(self) -> None:
        self.clients: dict[str, ServiceClient] = {}

    def find_by_id(self, client_id: str) -> ServiceClient | None:
        return self.clients.get(client_id)

    def save(self, client: ServiceClient) -> None:
        self.clients[client.client_id] = client


class StaticDeclarations(ServiceClientDeclarations):
    def __init__(self, *declarations: ClientDeclaration, error: bool = False) -> None:
        self.declarations = list(declarations)
        self._error = error

    def list_declarations(self) -> list[ClientDeclaration]:
        if self._error:
            raise InvalidDeclarationError("broken")
        return self.declarations


def _run(
    declarations: StaticDeclarations,
    repository: MemoryRepository,
    hasher: CountingHasher,
    events: InMemoryBusinessEventLogger | None = None,
) -> int:
    use_case = BootstrapServiceClientsUseCase(
        declarations, repository, hasher, events or InMemoryBusinessEventLogger()
    )
    return use_case.execute()


class TestBootstrap:
    def test_registers_a_client_with_hashed_secrets_never_clear_text(self) -> None:
        repository = MemoryRepository()
        declarations = StaticDeclarations(ClientDeclaration("shop", SCOPES, S1, S2))

        count = _run(declarations, repository, CountingHasher())

        client = repository.clients["shop"]
        assert count == 1
        assert client.scopes == SCOPES
        assert client.current_secret_hash.endswith(S1)
        assert client.current_secret_hash != S1
        assert client.previous_secret_hash is not None
        assert client.previous_secret_hash != S2

    def test_is_idempotent_and_does_not_rehash_unchanged_secrets(self) -> None:
        repository = MemoryRepository()
        hasher = CountingHasher()
        declarations = StaticDeclarations(ClientDeclaration("shop", SCOPES, S1))
        _run(declarations, repository, hasher)
        first = repository.clients["shop"]

        _run(declarations, repository, hasher)

        assert repository.clients["shop"] == first
        assert hasher.hash_calls == 1

    def test_rotation_keeps_the_old_secret_valid_as_previous(self) -> None:
        repository = MemoryRepository()
        hasher = CountingHasher()
        _run(StaticDeclarations(ClientDeclaration("shop", SCOPES, S1)), repository, hasher)
        old_hash = repository.clients["shop"].current_secret_hash

        _run(StaticDeclarations(ClientDeclaration("shop", SCOPES, S2, S1)), repository, hasher)

        client = repository.clients["shop"]
        assert client.current_secret_hash.endswith(S2)
        assert client.previous_secret_hash == old_hash

    def test_dropping_the_previous_secret_revokes_it(self) -> None:
        repository = MemoryRepository()
        hasher = CountingHasher()
        _run(StaticDeclarations(ClientDeclaration("shop", SCOPES, S2, S1)), repository, hasher)

        _run(StaticDeclarations(ClientDeclaration("shop", SCOPES, S2)), repository, hasher)

        assert repository.clients["shop"].previous_secret_hash is None

    def test_scopes_follow_the_declaration(self) -> None:
        repository = MemoryRepository()
        hasher = CountingHasher()
        _run(StaticDeclarations(ClientDeclaration("shop", SCOPES, S1)), repository, hasher)

        _run(StaticDeclarations(ClientDeclaration("shop", frozenset(), S1)), repository, hasher)

        assert repository.clients["shop"].scopes == frozenset()

    def test_invalid_declarations_stop_the_bootstrap_before_any_write(self) -> None:
        repository = MemoryRepository()

        with pytest.raises(InvalidDeclarationError):
            _run(StaticDeclarations(error=True), repository, CountingHasher())

        assert repository.clients == {}


class TestBusinessEvents:
    def test_each_bootstrapped_client_emits_an_event_without_any_secret(self) -> None:
        events = InMemoryBusinessEventLogger()
        declarations = StaticDeclarations(ClientDeclaration("shop", SCOPES, S1, S2))

        _run(declarations, MemoryRepository(), CountingHasher(), events)

        [event] = events.events
        assert event.event == "auth.service_client_bootstrapped"
        assert event.outcome.value == "success"
        assert (event.resource_type, event.resource_id) == ("service_client", "shop")
        assert S1 not in repr(event)
        assert S2 not in repr(event)
