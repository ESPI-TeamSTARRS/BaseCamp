from sqlalchemy import Engine
from sqlalchemy.orm import Session

from app.service_token.domain.entities.service_client import ServiceClient
from app.service_token.domain.enums.service_scope import ServiceScope
from app.service_token.domain.interfaces.service_client_repository import ServiceClientRepository
from app.service_token.infrastructure.models.service_client_model import ServiceClientModel


class SqlAlchemyServiceClientRepository(ServiceClientRepository):
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def find_by_id(self, client_id: str) -> ServiceClient | None:
        with Session(self._engine) as session:
            model = session.get(ServiceClientModel, client_id)
            return None if model is None else _to_entity(model)

    def save(self, client: ServiceClient) -> None:
        with Session(self._engine) as session, session.begin():
            session.merge(_to_model(client))


def _to_entity(model: ServiceClientModel) -> ServiceClient:
    return ServiceClient(
        client_id=model.client_id,
        scopes=_parse_scopes(model.scopes),
        current_secret_hash=model.current_secret_hash,
        previous_secret_hash=model.previous_secret_hash,
    )


def _to_model(client: ServiceClient) -> ServiceClientModel:
    return ServiceClientModel(
        client_id=client.client_id,
        scopes=" ".join(sorted(scope.value for scope in client.scopes)),
        current_secret_hash=client.current_secret_hash,
        previous_secret_hash=client.previous_secret_hash,
    )


def _parse_scopes(stored: str) -> frozenset[ServiceScope]:
    """Les scopes inconnus (retirés du code) sont ignorés : ils ne donnent aucun droit."""
    known = {scope.value: scope for scope in ServiceScope}
    return frozenset(known[value] for value in stored.split() if value in known)
