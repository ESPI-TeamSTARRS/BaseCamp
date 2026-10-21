from datetime import datetime
from uuid import UUID

from sqlalchemy.orm import Session

from app.backoffice.domain.interfaces.face_template_repository import FaceTemplateRepository
from app.backoffice.infrastructure.models.operator_face_template_model import (
    OperatorFaceTemplateModel,
)


class SqlAlchemyFaceTemplateRepository(FaceTemplateRepository):
    def __init__(self, session: Session) -> None:
        self._session = session

    def find(self, account_id: UUID) -> bytes | None:
        model = self._session.get(OperatorFaceTemplateModel, account_id)
        return None if model is None else bytes(model.template)

    def save(self, account_id: UUID, template: bytes, now: datetime) -> None:
        self._session.merge(
            OperatorFaceTemplateModel(account_id=account_id, template=template, updated_at=now)
        )
        self._session.flush()
