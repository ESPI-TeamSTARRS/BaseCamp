"""Doublures en memoire des interfaces du domaine, partagees par les tests de la tranche."""

import hashlib
from datetime import UTC, datetime
from types import TracebackType
from typing import Self
from uuid import UUID

from app.registration.domain.entities.user import User
from app.registration.domain.entities.verification_token import VerificationToken
from app.registration.domain.exceptions.email_already_registered_error import (
    EmailAlreadyRegisteredError,
)
from app.registration.domain.exceptions.mail_delivery_error import MailDeliveryError
from app.registration.domain.interfaces.clock import Clock
from app.registration.domain.interfaces.common_password_list import CommonPasswordList
from app.registration.domain.interfaces.email_fingerprinter import EmailFingerprinter
from app.registration.domain.interfaces.password_hasher import PasswordHasher
from app.registration.domain.interfaces.registration_mailer import RegistrationMailer
from app.registration.domain.interfaces.token_generator import TokenGenerator
from app.registration.domain.interfaces.unit_of_work import UnitOfWork
from app.registration.domain.interfaces.user_repository import UserRepository
from app.registration.domain.interfaces.verification_token_repository import (
    VerificationTokenRepository,
)
from app.registration.domain.value_objects.email_address import EmailAddress

START = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)


class FakeStore:
    def __init__(self) -> None:
        self.users: dict[str, User] = {}
        self.tokens: dict[str, VerificationToken] = {}
        self.commits = 0


class FakeUserRepository(UserRepository):
    def __init__(self, store: FakeStore, pending: list[User]) -> None:
        self._store = store
        self._pending = pending

    def add(self, user: User) -> None:
        if user.email.value in self._store.users:
            raise EmailAlreadyRegisteredError
        self._pending.append(user)

    def mark_email_verified(self, user_id: UUID, now: datetime) -> None:
        for email, user in self._store.users.items():
            if user.id == user_id:
                self._store.users[email] = User(
                    user.id, user.email, user.password_hash, user.role, now, user.created_at
                )


class FakeVerificationTokenRepository(VerificationTokenRepository):
    def __init__(self, store: FakeStore, pending: list[VerificationToken]) -> None:
        self._store = store
        self._pending = pending

    def add(self, token: VerificationToken) -> None:
        self._pending.append(token)

    def consume(self, token_hash: str, now: datetime) -> UUID | None:
        token = self._store.tokens.get(token_hash)
        if token is None or not token.is_usable(now):
            return None
        self._store.tokens[token_hash] = token.mark_used(now)
        return token.user_id


class FakeUnitOfWork(UnitOfWork):
    def __init__(self, store: FakeStore) -> None:
        self._store = store
        self._pending_users: list[User] = []
        self._pending_tokens: list[VerificationToken] = []
        self.users = FakeUserRepository(store, self._pending_users)
        self.tokens = FakeVerificationTokenRepository(store, self._pending_tokens)

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self._pending_users.clear()
        self._pending_tokens.clear()

    def commit(self) -> None:
        for user in self._pending_users:
            self._store.users[user.email.value] = user
        for token in self._pending_tokens:
            self._store.tokens[token.token_hash] = token
        self._store.commits += 1


class FakeClock(Clock):
    def __init__(self) -> None:
        self.current = START

    def now(self) -> datetime:
        return self.current


class FakePasswordHasher(PasswordHasher):
    def __init__(self) -> None:
        self.calls = 0

    def hash(self, password: str) -> str:
        self.calls += 1
        return "hashed::" + hashlib.sha256(password.encode()).hexdigest()


class FakeTokenGenerator(TokenGenerator):
    def __init__(self) -> None:
        self._counter = 0

    def generate(self) -> str:
        self._counter += 1
        return f"raw-token-{self._counter}"

    def digest(self, token: str) -> str:
        return hashlib.sha256(token.encode()).hexdigest()


class FakeCommonPasswordList(CommonPasswordList):
    def contains(self, password: str) -> bool:
        return password.lower() == "motdepasse1234"


class FakeEmailFingerprinter(EmailFingerprinter):
    def fingerprint(self, email: EmailAddress) -> str:
        return "fp-" + hashlib.sha256(email.value.encode()).hexdigest()[:8]


class FakeMailer(RegistrationMailer):
    def __init__(self, fail: bool = False) -> None:
        self.fail = fail
        self.verifications: list[tuple[str, str]] = []
        self.already_exists: list[str] = []

    def send_verification(self, to: EmailAddress, token: str) -> None:
        if self.fail:
            raise MailDeliveryError
        self.verifications.append((to.value, token))

    def send_account_exists(self, to: EmailAddress) -> None:
        if self.fail:
            raise MailDeliveryError
        self.already_exists.append(to.value)
