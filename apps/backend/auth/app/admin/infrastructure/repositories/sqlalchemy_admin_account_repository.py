from datetime import datetime
from uuid import UUID

from sqlalchemy import Column, MetaData, Table, Uuid, delete, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.admin.domain.entities.account_page import AccountPage
from app.admin.domain.entities.managed_account import ManagedAccount
from app.admin.domain.exceptions.admin_errors import OperatorAlreadyExistsError
from app.admin.domain.interfaces.admin_account_repository import AdminAccountRepository
from app.admin.infrastructure.models.managed_account_model import ManagedAccountModel

# Table de la connexion (migration 0007), vue ici par sa seule colonne utile : aucune dependance
# vers la tranche `login`.
REFRESH_TOKENS = Table("refresh_tokens", MetaData(), Column("user_id", Uuid))
# Gabarits faciaux (migration 0010, tranche back-office), vus par leur seule cle : un compte
# desactive perd son gabarit sans dependance vers cette tranche.
FACE_TEMPLATES = Table("operator_face_templates", MetaData(), Column("account_id", Uuid))
OPERATOR = "operator"


def _entity(model: ManagedAccountModel) -> ManagedAccount:
    return ManagedAccount(
        model.id,
        model.email,
        model.role,
        model.email_verified_at is not None,
        model.disabled_at is not None,
        model.created_at,
    )


class SqlAlchemyAdminAccountRepository(AdminAccountRepository):
    def __init__(self, session: Session) -> None:
        self._session = session

    def list_page(self, limit: int, offset: int) -> AccountPage:
        total = self._session.execute(
            select(func.count()).select_from(ManagedAccountModel)
        ).scalar_one()
        models = self._session.execute(
            select(ManagedAccountModel)
            .order_by(ManagedAccountModel.created_at, ManagedAccountModel.id)
            .limit(limit)
            .offset(offset)
        ).scalars()
        return AccountPage(tuple(_entity(m) for m in models), int(total), limit, offset)

    def lock_operators(self) -> list[ManagedAccount]:
        models = self._session.execute(
            select(ManagedAccountModel)
            .where(ManagedAccountModel.role == OPERATOR, ManagedAccountModel.disabled_at.is_(None))
            .order_by(ManagedAccountModel.id)
            .with_for_update()
        ).scalars()
        return [_entity(m) for m in models]

    def find_for_update(self, account_id: UUID) -> ManagedAccount | None:
        model = self._session.execute(
            select(ManagedAccountModel)
            .where(ManagedAccountModel.id == account_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        ).scalar_one_or_none()
        return None if model is None else _entity(model)

    def set_disabled(self, account_id: UUID, disabled_at: datetime | None) -> None:
        self._session.execute(
            update(ManagedAccountModel)
            .where(ManagedAccountModel.id == account_id)
            .values(disabled_at=disabled_at)
        )

    def revoke_sessions(self, account_id: UUID) -> int:
        result = self._session.execute(
            delete(REFRESH_TOKENS).where(REFRESH_TOKENS.c.user_id == account_id)
        )
        return int(result.rowcount)  # type: ignore[attr-defined]

    def delete_face_template(self, account_id: UUID) -> bool:
        result = self._session.execute(
            delete(FACE_TEMPLATES).where(FACE_TEMPLATES.c.account_id == account_id)
        )
        return int(result.rowcount) > 0  # type: ignore[attr-defined]

    def add_operator(self, account_id: UUID, email: str, password_hash: str, now: datetime) -> None:
        self._session.add(
            ManagedAccountModel(
                id=account_id,
                email=email,
                password_hash=password_hash,
                role=OPERATOR,
                email_verified_at=now,
                disabled_at=None,
                created_at=now,
            )
        )
        try:
            self._session.flush()
        except IntegrityError:
            self._session.rollback()
            raise OperatorAlreadyExistsError from None
