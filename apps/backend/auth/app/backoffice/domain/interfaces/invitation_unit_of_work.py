from abc import ABC, abstractmethod
from types import TracebackType
from typing import Self

from app.backoffice.domain.interfaces.face_template_repository import FaceTemplateRepository
from app.backoffice.domain.interfaces.invitation_repository import InvitationRepository
from app.backoffice.domain.interfaces.operator_account_writer import OperatorAccountWriter


class InvitationUnitOfWork(ABC):
    """Une transaction : compte, gabarit et consommation du jeton sont valides ensemble par
    `commit()`, sinon annules en sortie du bloc."""

    invitations: InvitationRepository
    operators: OperatorAccountWriter
    templates: FaceTemplateRepository

    @abstractmethod
    def __enter__(self) -> Self: ...

    @abstractmethod
    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None: ...

    @abstractmethod
    def commit(self) -> None: ...
