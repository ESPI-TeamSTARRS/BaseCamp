from datetime import datetime

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from app.backoffice.domain.entities.operator_invitation import OperatorInvitation
from app.backoffice.domain.interfaces.invitation_repository import InvitationRepository
from app.backoffice.infrastructure.models.operator_invitation_model import (
    OperatorInvitationModel,
)


def _entity(model: OperatorInvitationModel) -> OperatorInvitation:
    return OperatorInvitation(
        model.digest,
        model.email,
        model.created_at,
        model.expires_at,
        model.consumed_at,
        model.revoked_at,
    )


class SqlAlchemyInvitationRepository(InvitationRepository):
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, invitation: OperatorInvitation) -> None:
        self._session.add(
            OperatorInvitationModel(
                digest=invitation.digest,
                email=invitation.email,
                created_at=invitation.created_at,
                expires_at=invitation.expires_at,
                consumed_at=invitation.consumed_at,
                revoked_at=invitation.revoked_at,
            )
        )
        self._session.flush()

    def find(self, digest: str) -> OperatorInvitation | None:
        model = self._session.get(OperatorInvitationModel, digest)
        return None if model is None else _entity(model)

    def claim(self, digest: str, now: datetime) -> OperatorInvitation | None:
        model = self._session.execute(
            select(OperatorInvitationModel)
            .where(OperatorInvitationModel.digest == digest)
            .with_for_update()
            .execution_options(populate_existing=True)
        ).scalar_one_or_none()
        if model is None:
            return None
        invitation = _entity(model)
        return invitation if invitation.usable(now) else None

    def mark_consumed(self, digest: str, now: datetime) -> None:
        self._session.execute(
            update(OperatorInvitationModel)
            .where(OperatorInvitationModel.digest == digest)
            .values(consumed_at=now)
        )

    def revoke_active_for(self, email: str, now: datetime) -> int:
        result = self._session.execute(
            update(OperatorInvitationModel)
            .where(
                OperatorInvitationModel.email == email,
                OperatorInvitationModel.consumed_at.is_(None),
                OperatorInvitationModel.revoked_at.is_(None),
                OperatorInvitationModel.expires_at > now,
            )
            .values(revoked_at=now)
        )
        return int(result.rowcount)  # type: ignore[attr-defined]

    def purge_before(self, cutoff: datetime) -> int:
        result = self._session.execute(
            delete(OperatorInvitationModel).where(OperatorInvitationModel.expires_at < cutoff)
        )
        return int(result.rowcount)  # type: ignore[attr-defined]
