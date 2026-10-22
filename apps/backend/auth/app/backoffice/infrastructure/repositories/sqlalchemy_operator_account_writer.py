from datetime import datetime
from uuid import UUID

from sqlalchemy.orm import Session

from app.admin.infrastructure.repositories.sqlalchemy_admin_account_repository import (
    SqlAlchemyAdminAccountRepository,
)
from app.backoffice.domain.interfaces.operator_account_writer import OperatorAccountWriter


class SqlAlchemyOperatorAccountWriter(OperatorAccountWriter):
    """Cree le compte dans la session de la transaction d'invitation (meme depot que `create-operator`
    : une seule facon d'ecrire un compte operateur)."""

    def __init__(self, session: Session) -> None:
        self._accounts = SqlAlchemyAdminAccountRepository(session)

    def add_operator(self, account_id: UUID, email: str, password_hash: str, now: datetime) -> None:
        self._accounts.add_operator(account_id, email, password_hash, now)
