from fastapi import FastAPI
from sqlalchemy import Engine

from app.admin.application.change_account_status import ChangeAccountStatusUseCase
from app.admin.application.create_operator import CreateOperatorUseCase
from app.admin.application.list_accounts import ListAccountsUseCase
from app.admin.infrastructure.repositories.sqlalchemy_admin_unit_of_work import (
    SqlAlchemyAdminUnitOfWork,
)
from app.core.events.business_event_logger import BusinessEventLogger
from app.registration.domain.services.password_policy import PasswordPolicy
from app.registration.infrastructure.clients.argon2_password_hasher import Argon2PasswordHasher
from app.registration.infrastructure.clients.file_common_password_list import (
    FileCommonPasswordList,
)
from app.registration.infrastructure.clients.system_clock import SystemClock


def wire_admin(application: FastAPI, engine: Engine, events: BusinessEventLogger) -> None:
    """Seul endroit qui assemble les implementations d'infrastructure de l'administration."""

    def unit_of_work() -> SqlAlchemyAdminUnitOfWork:
        return SqlAlchemyAdminUnitOfWork(engine)

    application.state.list_accounts_use_case = ListAccountsUseCase(unit_of_work, events)
    application.state.change_account_status_use_case = ChangeAccountStatusUseCase(
        unit_of_work, SystemClock(), events
    )


def build_create_operator(engine: Engine, events: BusinessEventLogger) -> CreateOperatorUseCase:
    """Pour la commande d'exploitation `create-operator` (aucune route HTTP ne la porte)."""
    return CreateOperatorUseCase(
        lambda: SqlAlchemyAdminUnitOfWork(engine),
        PasswordPolicy(FileCommonPasswordList()),
        Argon2PasswordHasher(),
        SystemClock(),
        events,
    )
