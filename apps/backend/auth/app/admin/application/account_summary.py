from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from app.admin.domain.entities.account_page import AccountPage
from app.admin.domain.entities.managed_account import ManagedAccount


@dataclass(frozen=True)
class AccountSummary:
    """Ce que l'administration expose d'un compte (jamais le hachage du mot de passe)."""

    id: UUID
    email: str
    role: str
    email_verified: bool
    disabled: bool
    created_at: datetime

    @classmethod
    def of(cls, account: ManagedAccount) -> "AccountSummary":
        return cls(
            account.id,
            account.email,
            account.role,
            account.email_verified,
            account.disabled,
            account.created_at,
        )


@dataclass(frozen=True)
class AccountPageSummary:
    items: tuple[AccountSummary, ...]
    total: int
    limit: int
    offset: int

    @classmethod
    def of(cls, page: AccountPage) -> "AccountPageSummary":
        return cls(
            tuple(AccountSummary.of(a) for a in page.items), page.total, page.limit, page.offset
        )
