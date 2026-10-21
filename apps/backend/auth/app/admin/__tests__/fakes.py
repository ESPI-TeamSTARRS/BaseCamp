"""Doublures en memoire de l'administration, partagees par les tests unitaires de la tranche."""

from dataclasses import replace
from datetime import UTC, datetime
from types import TracebackType
from typing import Self
from uuid import UUID

from app.admin.domain.entities.account_page import AccountPage
from app.admin.domain.entities.managed_account import ManagedAccount
from app.admin.domain.exceptions.admin_errors import OperatorAlreadyExistsError
from app.admin.domain.interfaces.admin_account_repository import AdminAccountRepository
from app.admin.domain.interfaces.admin_unit_of_work import AdminUnitOfWork
from app.registration.domain.interfaces.clock import Clock
from app.registration.domain.interfaces.password_hasher import PasswordHasher

START = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)


class AdminStore:
    def __init__(self, *accounts: ManagedAccount) -> None:
        self.accounts: dict[UUID, ManagedAccount] = {a.id: a for a in accounts}
        self.sessions: dict[UUID, int] = {}
        self.password_hashes: dict[UUID, str] = {}
        self.commits = 0


class FakeAdminRepository(AdminAccountRepository):
    def __init__(self, store: AdminStore) -> None:
        self._store = store

    def list_page(self, limit: int, offset: int) -> AccountPage:
        items = sorted(self._store.accounts.values(), key=lambda a: (a.created_at, str(a.id)))
        return AccountPage(tuple(items[offset : offset + limit]), len(items), limit, offset)

    def lock_operators(self) -> list[ManagedAccount]:
        return [a for a in self._store.accounts.values() if a.active_operator]

    def find_for_update(self, account_id: UUID) -> ManagedAccount | None:
        return self._store.accounts.get(account_id)

    def set_disabled(self, account_id: UUID, disabled_at: datetime | None) -> None:
        account = self._store.accounts[account_id]
        self._store.accounts[account_id] = replace(account, disabled=disabled_at is not None)

    def revoke_sessions(self, account_id: UUID) -> int:
        return self._store.sessions.pop(account_id, 0)

    def add_operator(self, account_id: UUID, email: str, password_hash: str, now: datetime) -> None:
        if any(a.email == email for a in self._store.accounts.values()):
            raise OperatorAlreadyExistsError
        self._store.accounts[account_id] = ManagedAccount(
            account_id, email, "operator", True, False, now
        )
        self._store.password_hashes[account_id] = password_hash


class FakeAdminUnitOfWork(AdminUnitOfWork):
    def __init__(self, store: AdminStore) -> None:
        self._store = store
        self.accounts = FakeAdminRepository(store)

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


class FakeClock(Clock):
    def now(self) -> datetime:
        return START


class FakeHasher(PasswordHasher):
    def hash(self, password: str) -> str:
        return "hashed::" + password[::-1]


def account(email: str, role: str = "customer", disabled: bool = False) -> ManagedAccount:
    from uuid import uuid4

    return ManagedAccount(uuid4(), email, role, True, disabled, START)
