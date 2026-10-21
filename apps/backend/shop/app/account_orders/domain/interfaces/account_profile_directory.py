from abc import ABC, abstractmethod

from app.account_orders.domain.entities.account_profile import AccountProfile


class AccountProfileDirectory(ABC):
    @abstractmethod
    def profile_of(self, token: str) -> AccountProfile | None:
        """Profil du porteur du jeton selon `auth`, ou `None` si `auth` ne repond pas ou refuse."""
