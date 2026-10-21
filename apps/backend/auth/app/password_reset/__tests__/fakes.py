"""Doublures en memoire des interfaces de la tranche, partagees par ses tests."""

from datetime import datetime
from types import TracebackType
from typing import Self
from uuid import UUID, uuid4

from sqlalchemy import Engine, text

from app.password_reset.domain.entities.password_reset_token import PasswordResetToken
from app.password_reset.domain.entities.resettable_account import ResettableAccount
from app.password_reset.domain.interfaces.account_repository import AccountRepository
from app.password_reset.domain.interfaces.password_reset_mailer import PasswordResetMailer
from app.password_reset.domain.interfaces.password_reset_unit_of_work import (
    PasswordResetUnitOfWork,
)
from app.password_reset.domain.interfaces.request_throttle import RequestThrottle
from app.password_reset.domain.interfaces.reset_token_repository import ResetTokenRepository
from app.password_reset.domain.interfaces.session_revoker import SessionRevoker
from app.registration.domain.exceptions.mail_delivery_error import MailDeliveryError
from app.registration.domain.value_objects.email_address import EmailAddress


class ResetStore:
    def __init__(self) -> None:
        self.accounts: dict[UUID, ResettableAccount] = {}
        self.password_hashes: dict[UUID, str] = {}
        self.tokens: dict[str, PasswordResetToken] = {}
        self.attempts: dict[str, int] = {}
        self.revocations: list[tuple[UUID, datetime]] = []
        self.live_sessions = 2
        self.commits = 0
        self.max_attempts = 3

    def add_account(self, email: str) -> UUID:
        account = ResettableAccount(uuid4(), EmailAddress.of(email))
        self.accounts[account.id] = account
        self.password_hashes[account.id] = "old-hash"
        return account.id


class FakeAccountRepository(AccountRepository):
    def __init__(self, store: ResetStore) -> None:
        self._store = store

    def find_by_email(self, email: EmailAddress) -> ResettableAccount | None:
        return next((a for a in self._store.accounts.values() if a.email == email), None)

    def find_by_id(self, user_id: UUID) -> ResettableAccount | None:
        return self._store.accounts.get(user_id)

    def change_password(self, user_id: UUID, password_hash: str) -> None:
        self._store.password_hashes[user_id] = password_hash


class FakeResetTokenRepository(ResetTokenRepository):
    def __init__(self, store: ResetStore) -> None:
        self._store = store

    def replace(self, token: PasswordResetToken, now: datetime) -> None:
        for key, existing in list(self._store.tokens.items()):
            if existing.user_id == token.user_id and existing.is_usable(now):
                self._store.tokens[key] = existing.mark_used(now)
        self._store.tokens[token.token_hash] = token

    def consume(self, token_hash: str, now: datetime) -> UUID | None:
        token = self._store.tokens.get(token_hash)
        if token is None or not token.is_usable(now):
            return None
        self._store.tokens[token_hash] = token.mark_used(now)
        return token.user_id


class FakeRequestThrottle(RequestThrottle):
    def __init__(self, store: ResetStore) -> None:
        self._store = store

    def allow(self, fingerprint: str, now: datetime) -> bool:
        count = self._store.attempts.get(fingerprint, 0)
        if count >= self._store.max_attempts:
            return False
        self._store.attempts[fingerprint] = count + 1
        return True


class FakeSessionRevoker(SessionRevoker):
    def __init__(self, store: ResetStore) -> None:
        self._store = store

    def revoke_all(self, user_id: UUID, now: datetime) -> int:
        self._store.revocations.append((user_id, now))
        return self._store.live_sessions


class FakeResetUnitOfWork(PasswordResetUnitOfWork):
    """Les ecritures ne sont visibles qu'apres `commit()` pour les mots de passe et les sessions."""

    def __init__(self, store: ResetStore) -> None:
        self._store = store
        self.accounts = FakeAccountRepository(store)
        self.tokens = FakeResetTokenRepository(store)
        self.throttle = FakeRequestThrottle(store)
        self.sessions = FakeSessionRevoker(store)

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


class FakeResetMailer(PasswordResetMailer):
    def __init__(self, fail: bool = False) -> None:
        self.fail = fail
        self.links: list[tuple[str, str]] = []
        self.changes: list[str] = []

    def send_reset_link(self, to: EmailAddress, token: str) -> None:
        if self.fail:
            raise MailDeliveryError
        self.links.append((to.value, token))

    def send_password_changed(self, to: EmailAddress) -> None:
        if self.fail:
            raise MailDeliveryError
        self.changes.append(to.value)


REFRESH_TOKENS_DDL = (
    "CREATE TABLE refresh_tokens (id CHAR(32) PRIMARY KEY, user_id CHAR(32) NOT NULL, "
    "token_hash VARCHAR(64) NOT NULL UNIQUE, created_at DATETIME NOT NULL, "
    "expires_at DATETIME NOT NULL)"
)


def create_refresh_tokens(engine: Engine) -> None:
    """Table de la connexion (migration 0007), creee a la main : cette tranche ne l'importe pas."""
    with engine.begin() as connection:
        connection.execute(text(REFRESH_TOKENS_DDL))


def add_refresh_token(engine: Engine, user_id: UUID, digest: str) -> None:
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO refresh_tokens VALUES (:id, :user_id, :digest, "
                "'2026-01-01 12:00:00', '2026-01-08 12:00:00')"
            ),
            {"id": uuid4().hex, "user_id": user_id.hex, "digest": digest},
        )
