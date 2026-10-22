from types import TracebackType
from typing import Self

from sqlalchemy import Engine
from sqlalchemy.orm import Session

from app.backoffice.domain.interfaces.backoffice_unit_of_work import BackofficeUnitOfWork
from app.backoffice.domain.interfaces.template_cipher import TemplateCipher
from app.backoffice.infrastructure.repositories.sqlalchemy_challenge_repository import (
    SqlAlchemyChallengeRepository,
)
from app.backoffice.infrastructure.repositories.sqlalchemy_face_template_repository import (
    SqlAlchemyFaceTemplateRepository,
)


class SqlAlchemyBackofficeUnitOfWork(BackofficeUnitOfWork):
    """Une session courte par transaction (aucun etat partage entre requetes)."""

    def __init__(self, engine: Engine, cipher: TemplateCipher) -> None:
        self._session = Session(engine, expire_on_commit=False)
        self.challenges = SqlAlchemyChallengeRepository(self._session)
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
