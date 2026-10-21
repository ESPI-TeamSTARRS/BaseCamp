from abc import ABC, abstractmethod

from app.login.domain.entities.refresh_token import RefreshToken


class RefreshTokenRepository(ABC):
    @abstractmethod
    def add(self, token: RefreshToken) -> None: ...
