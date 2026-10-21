from datetime import datetime
from uuid import UUID

from sqlalchemy import LargeBinary, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.backoffice.infrastructure.models.backoffice_base import BackofficeBase
from app.backoffice.infrastructure.models.utc_date_time import UtcDateTime


class OperatorFaceTemplateModel(BackofficeBase):
    """Gabarit facial serialise d'un operateur (donnee biometrique : jamais journalise)."""

    __tablename__ = "operator_face_templates"

    account_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    template: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(UtcDateTime, nullable=False)
