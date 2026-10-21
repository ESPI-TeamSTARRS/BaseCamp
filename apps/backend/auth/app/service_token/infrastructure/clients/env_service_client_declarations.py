import re
from collections.abc import Mapping, Sequence

from app.service_token.domain.entities.client_declaration import ClientDeclaration
from app.service_token.domain.enums.service_scope import ServiceScope
from app.service_token.domain.exceptions.invalid_declaration_error import InvalidDeclarationError
from app.service_token.domain.interfaces.service_client_declarations import (
    ServiceClientDeclarations,
)

CLIENT_ENV_PREFIX = "APP_SERVICE_CLIENT_SECRET_"
PREVIOUS_SUFFIX = "_PREVIOUS"


class EnvServiceClientDeclarations(ServiceClientDeclarations):
    """Déclarations : clients et scopes (non secrets) fournis, secrets lus dans l'environnement.

    Pour le client `shop` : `APP_SERVICE_CLIENT_SECRET_SHOP` (courant) et
    `APP_SERVICE_CLIENT_SECRET_SHOP_PREVIOUS` (précédent, optionnel, vide = absent).
    """

    def __init__(self, clients: Mapping[str, Sequence[str]], environ: Mapping[str, str]) -> None:
        self._clients = clients
        self._environ = environ

    def list_declarations(self) -> list[ClientDeclaration]:
        return [self._declaration(client_id, scopes) for client_id, scopes in self._clients.items()]

    def _declaration(self, client_id: str, scopes: Sequence[str]) -> ClientDeclaration:
        variable = CLIENT_ENV_PREFIX + re.sub(r"[^A-Z0-9]", "_", client_id.upper())
        current = self._environ.get(variable, "")
        if not current:
            raise InvalidDeclarationError(f"missing secret for client {client_id}: set {variable}")
        previous = self._environ.get(variable + PREVIOUS_SUFFIX) or None
        return ClientDeclaration(
            client_id, self._parse_scopes(client_id, scopes), current, previous
        )

    @staticmethod
    def _parse_scopes(client_id: str, scopes: Sequence[str]) -> frozenset[ServiceScope]:
        try:
            return frozenset(ServiceScope(scope) for scope in scopes)
        except ValueError as error:
            raise InvalidDeclarationError(f"unknown scope for client {client_id}") from error
