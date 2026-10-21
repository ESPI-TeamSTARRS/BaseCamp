from dataclasses import dataclass

from app.account_orders.domain.entities.account_order import AccountOrder


@dataclass(frozen=True)
class AccountOrderPage:
    items: tuple[AccountOrder, ...]
    total: int
    limit: int
    offset: int
