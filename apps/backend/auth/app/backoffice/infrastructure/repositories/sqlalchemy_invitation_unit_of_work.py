from types import TracebackType
from typing import Self

from sqlalchemy import Engine
from sqlalchemy.orm import Session

from app.backoffice.domain.interfaces.invitation_unit_of_work import InvitationUnitOfWork
from app.backoffice.domain.interfaces.template_cipher import TemplateCipher
from app.backoffice.infrastructure.repositories.sqlalchemy_face_template_repository import (
    SqlAlchemyFaceTemplateRepository,
)
from app.backoffice.infrastructure.repositories.sqlalchemy_invitation_repository import (
    SqlAlchemyInvitationRepository,
)
from app.backoffice.infrastructure.repositories.sqlalchemy_operator_account_writer import (
    SqlAlchemyOperatorAccountWriter,
)


class SqlAlchemyInvitationUnitOfWork(InvitationUnitOfWork):
    """Une session courte par transaction : compte, gabarit chiffre et jeton consomme ensemble."""

    def __init__(self, engine: Engine, cipher: TemplateCipher) -> None:
        self._session = Session(engine, expire_on_commit=False)
        self.invitations = SqlAlchemyInvitationRepository(self._session)
        self.operators = SqlAlchemyOperatorAccountWriter(self._session)
        self.templates = SqlAlchemyFaceTemplateRepository(self._session, cipher)

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self._session.rollback()
        self._session.close()

    def commit(self) -> None:
        self._session.commit()
