from dataclasses import dataclass

from app.admin.domain.entities.managed_account import ManagedAccount


@dataclass(frozen=True)
class AccountPage:
    items: tuple[ManagedAccount, ...]
    total: int
    limit: int
    offset: int
