from abc import ABC, abstractmethod

from app.service_token.domain.entities.client_declaration import ClientDeclaration


class ServiceClientDeclarations(ABC):
    @abstractmethod
    def list_declarations(self) -> list[ClientDeclaration]:
        """Clients à amorcer; lève InvalidDeclarationError si une déclaration est invalide."""
