from app.core.events.business_event import BusinessEvent
from app.core.events.business_event_logger import BusinessEventLogger
from app.service_token.domain.entities.client_declaration import ClientDeclaration
from app.service_token.domain.entities.service_client import ServiceClient
from app.service_token.domain.enums.service_token_event import ServiceTokenEvent
from app.service_token.domain.interfaces.secret_hasher import SecretHasher
from app.service_token.domain.interfaces.service_client_declarations import (
    ServiceClientDeclarations,
)
from app.service_token.domain.interfaces.service_client_repository import ServiceClientRepository


class BootstrapServiceClientsUseCase:
    """Enregistre ou met à jour les clients déclarés (idempotent, secrets hachés, jamais en clair).

    Rotation : l'opérateur déclare le nouveau secret en courant et l'ancien en précédent; les deux
    restent valides jusqu'au prochain passage sans précédent. Une empreinte existante qui vérifie
    toujours le secret est conservée (pas de ré-hachage inutile).
    """

    def __init__(
        self,
        declarations: ServiceClientDeclarations,
        repository: ServiceClientRepository,
        hasher: SecretHasher,
        events: BusinessEventLogger,
    ) -> None:
        self._declarations = declarations
        self._repository = repository
        self._hasher = hasher
        self._events = events

    def execute(self) -> int:
        declared = self._declarations.list_declarations()
        for declaration in declared:
            self._repository.save(self._to_client(declaration))
            self._events.log(
                BusinessEvent.success(
                    ServiceTokenEvent.CLIENT_BOOTSTRAPPED,
                    resource_type="service_client",
                    resource_id=declaration.client_id,
                )
            )
        return len(declared)

    def _to_client(self, declaration: ClientDeclaration) -> ServiceClient:
        existing = self._repository.find_by_id(declaration.client_id)
        known = [] if existing is None else self._known_hashes(existing)
        previous = declaration.previous_secret
        return ServiceClient(
            declaration.client_id,
            declaration.scopes,
            self._hash_for(declaration.current_secret, known),
            None if previous is None else self._hash_for(previous, known),
        )

    @staticmethod
    def _known_hashes(client: ServiceClient) -> list[str]:
        hashes = [client.current_secret_hash]
        if client.previous_secret_hash is not None:
            hashes.append(client.previous_secret_hash)
        return hashes

    def _hash_for(self, secret: str, known: list[str]) -> str:
        reusable = next((h for h in known if self._hasher.verify(h, secret)), None)
        return reusable if reusable is not None else self._hasher.hash(secret)
