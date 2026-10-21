"""Amorcage des clients de service : `python -m app.service_token.bootstrap`.

Commande one-shot (service compose `auth-bootstrap`), idempotente et rejouable : elle lit les
secrets dans l'environnement, les hache (argon2id) et enregistre les clients. Aucun secret n'est
ecrit dans une migration, dans le depot ni dans les journaux.
"""

import os
import sys
from collections.abc import Mapping

from sqlalchemy import Engine, create_engine

from app.core.config import Settings
from app.core.events.business_event_logger import BusinessEventLogger
from app.core.logging.structlog_business_event_logger import StructlogBusinessEventLogger
from app.service_token.application.bootstrap_service_clients import BootstrapServiceClientsUseCase
from app.service_token.domain.exceptions.invalid_declaration_error import InvalidDeclarationError
from app.service_token.infrastructure.clients.env_service_client_declarations import (
    EnvServiceClientDeclarations,
)
from app.service_token.infrastructure.hashers.argon2_secret_hasher import Argon2SecretHasher
from app.service_token.infrastructure.repositories.sqlalchemy_service_client_repository import (
    SqlAlchemyServiceClientRepository,
)

DB_CONNECT_TIMEOUT_SECONDS = 5


def run(
    engine: Engine, settings: Settings, environ: Mapping[str, str], events: BusinessEventLogger
) -> int:
    use_case = BootstrapServiceClientsUseCase(
        EnvServiceClientDeclarations(settings.service_clients, environ),
        SqlAlchemyServiceClientRepository(engine),
        Argon2SecretHasher(),
        events,
    )
    return use_case.execute()


def main() -> int:
    settings = Settings()
    engine = create_engine(
        settings.database_url, connect_args={"connect_timeout": DB_CONNECT_TIMEOUT_SECONDS}
    )
    try:
        count = run(
            engine,
            settings,
            os.environ,
            StructlogBusinessEventLogger(settings.service_name, sys.stdout),
        )
    except InvalidDeclarationError as error:
        print(f"Amorcage impossible : {error}", file=sys.stderr)
        return 1
    print(f"{count} client(s) de service amorce(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
