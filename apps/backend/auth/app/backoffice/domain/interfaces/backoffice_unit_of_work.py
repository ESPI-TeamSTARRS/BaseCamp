from abc import ABC, abstractmethod
from types import TracebackType
from typing import Self

from app.backoffice.domain.interfaces.challenge_repository import ChallengeRepository
from app.backoffice.domain.interfaces.face_template_repository import FaceTemplateRepository


class BackofficeUnitOfWork(ABC):
    """Une transaction : tout est valide par `commit()`, sinon annule en sortie du bloc."""

    challenges: ChallengeRepository
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
