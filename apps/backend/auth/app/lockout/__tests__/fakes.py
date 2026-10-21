"""Doublures en memoire du verrouillage, partagees par les tests de la tranche et de ses appelants."""

from datetime import UTC, datetime, timedelta
from types import TracebackType
from typing import Self

from app.lockout.domain.entities.lockout_policy import LockoutPolicy
from app.lockout.domain.entities.lockout_state import LockoutState
from app.lockout.domain.interfaces.lockout_repository import LockoutRepository
from app.lockout.domain.interfaces.lockout_unit_of_work import LockoutUnitOfWork

START = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
FIVE_IN_FIFTEEN = LockoutPolicy(
    max_failures=5,
    window=timedelta(minutes=15),
    durations=(timedelta(minutes=15), timedelta(minutes=30), timedelta(minutes=60)),
    memory=timedelta(hours=24),
)


class LockoutStore:
    def __init__(self) -> None:
        self.rows: dict[tuple[str, str], LockoutState] = {}
        self.commits = 0


class FakeLockoutRepository(LockoutRepository):
    def __init__(self, store: LockoutStore) -> None:
        self._store = store

    def find(self, scope: str, subject: str) -> LockoutState | None:
        return self._store.rows.get((scope, subject))

    def lock_for_update(self, scope: str, subject: str, now: datetime) -> LockoutState:
        return self._store.rows.get((scope, subject)) or LockoutState(
            scope, subject, updated_at=now
        )

    def save(self, state: LockoutState) -> None:
        self._store.rows[(state.scope, state.subject)] = state

    def delete(self, scope: str, subject: str) -> None:
        self._store.rows.pop((scope, subject), None)

    def purge_idle_before(self, cutoff: datetime) -> int:
        stale = [
            key
            for key, state in self._store.rows.items()
            if state.updated_at is not None
            and state.updated_at < cutoff
            and (state.locked_until is None or state.locked_until < cutoff)
        ]
        for key in stale:
            del self._store.rows[key]
        return len(stale)


class FakeLockoutUnitOfWork(LockoutUnitOfWork):
    def __init__(self, store: LockoutStore) -> None:
        self._store = store
        self.lockouts = FakeLockoutRepository(store)

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        return None

    def commit(self) -> None:
        self._store.commits += 1
