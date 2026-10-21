from abc import ABC, abstractmethod

from app.service_token.domain.entities.service_client import ServiceClient


class ServiceClientRepository(ABC):
    @abstractmethod
    def find_by_id(self, client_id: str) -> ServiceClient | None: ...

    @abstractmethod
    def save(self, client: ServiceClient) -> None:
        """Crée le client ou remplace ses scopes et ses empreintes."""
