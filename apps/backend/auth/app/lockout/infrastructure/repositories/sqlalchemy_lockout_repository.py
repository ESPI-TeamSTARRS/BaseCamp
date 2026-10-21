from datetime import datetime

from sqlalchemy import delete, select
from sqlalchemy.dialects import postgresql, sqlite
from sqlalchemy.orm import Session

from app.lockout.domain.entities.lockout_state import LockoutState
from app.lockout.domain.interfaces.lockout_repository import LockoutRepository
from app.lockout.infrastructure.mappers.lockout_mapper import LockoutMapper
from app.lockout.infrastructure.models.login_lockout_model import LoginLockoutModel


class SqlAlchemyLockoutRepository(LockoutRepository):
    def __init__(self, session: Session) -> None:
        self._session = session

    def find(self, scope: str, subject: str) -> LockoutState | None:
        model = self._session.get(LoginLockoutModel, (scope, subject))
        return None if model is None else LockoutMapper.to_entity(model)

    def lock_for_update(self, scope: str, subject: str, now: datetime) -> LockoutState:
        self._ensure_row(scope, subject, now)
        model = self._session.execute(
            select(LoginLockoutModel)
            .where(LoginLockoutModel.scope == scope, LoginLockoutModel.subject == subject)
            .with_for_update()
            .execution_options(populate_existing=True)
        ).scalar_one()
        return LockoutMapper.to_entity(model)

    def save(self, state: LockoutState) -> None:
        model = self._session.get(LoginLockoutModel, (state.scope, state.subject))
        if model is None:
            raise LookupError("lock_for_update must run before save")
        LockoutMapper.apply(model, state)
        self._session.flush()

    def delete(self, scope: str, subject: str) -> None:
        self._session.execute(
            delete(LoginLockoutModel).where(
                LoginLockoutModel.scope == scope, LoginLockoutModel.subject == subject
            )
        )

    def purge_idle_before(self, cutoff: datetime) -> int:
        result = self._session.execute(
            delete(LoginLockoutModel).where(
                LoginLockoutModel.updated_at < cutoff,
                (LoginLockoutModel.locked_until.is_(None))
                | (LoginLockoutModel.locked_until < cutoff),
            )
        )
        return int(result.rowcount)  # type: ignore[attr-defined]

    def _ensure_row(self, scope: str, subject: str, now: datetime) -> None:
        """INSERT ... ON CONFLICT DO NOTHING : deux premiers echecs simultanes ne se heurtent pas."""
        dialect = self._session.get_bind().dialect.name
        insert = postgresql.insert if dialect == "postgresql" else sqlite.insert
        statement = (
            insert(LoginLockoutModel)
            .values(scope=scope, subject=subject, failures=0, level=0, updated_at=now)
            .on_conflict_do_nothing(index_elements=["scope", "subject"])
        )
        self._session.execute(statement)
