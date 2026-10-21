"""Doublures en memoire des interfaces du domaine, partagees par les tests de la tranche."""

import hashlib
from datetime import UTC, datetime
from types import TracebackType
from typing import Self
from uuid import UUID, uuid4

from app.login.domain.entities.access_token_claims import AccessTokenClaims
from app.login.domain.entities.account import Account
from app.login.domain.entities.refresh_token import RefreshToken
from app.login.domain.enums.token_rejection import TokenRejection
from app.login.domain.exceptions.access_token_rejected_error import AccessTokenRejectedError
from app.login.domain.interfaces.access_token_signer import AccessTokenSigner
from app.login.domain.interfaces.access_token_verifier import AccessTokenVerifier
from app.login.domain.interfaces.account_repository import AccountRepository
from app.login.domain.interfaces.clock import Clock
from app.login.domain.interfaces.email_fingerprinter import EmailFingerprinter
from app.login.domain.interfaces.password_verifier import PasswordVerifier
from app.login.domain.interfaces.refresh_token_generator import RefreshTokenGenerator
from app.login.domain.interfaces.refresh_token_repository import RefreshTokenRepository
from app.login.domain.interfaces.unit_of_work import UnitOfWork

START = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
ACCOUNT_SECRET = "sentier-du-mont-blanc"
EMAIL = "camille@example.com"


def make_account(
    email: str = EMAIL,
    password: str = ACCOUNT_SECRET,
    role: str = "customer",
    verified: bool = True,
    disabled: bool = False,
) -> Account:
    return Account(uuid4(), email, FakePasswordVerifier.digest(password), role, verified, disabled)


class FakeStore:
    def __init__(self, *accounts: Account) -> None:
        self.accounts: dict[UUID, Account] = {account.id: account for account in accounts}
        self.refresh_tokens: list[RefreshToken] = []
        self.commits = 0


class FakeAccountRepository(AccountRepository):
    def __init__(self, store: FakeStore, updates: dict[UUID, str]) -> None:
        self._store = store
        self._updates = updates

    def find_by_email(self, email: str) -> Account | None:
        return next((a for a in self._store.accounts.values() if a.email == email), None)

    def find_by_id(self, account_id: UUID) -> Account | None:
        return self._store.accounts.get(account_id)

    def update_password_hash(self, account_id: UUID, password_hash: str) -> None:
        self._updates[account_id] = password_hash


class FakeRefreshTokenRepository(RefreshTokenRepository):
    """`add` n'est visible qu'au `commit()`; `consume` et `revoke_family` agissent aussitot."""

    def __init__(self, store: FakeStore, pending: list[RefreshToken]) -> None:
        self._store = store
        self._pending = pending

    def add(self, token: RefreshToken) -> None:
        self._pending.append(token)

    def consume(self, token_hash: str, now: datetime) -> RefreshToken | None:
        for index, token in enumerate(self._store.refresh_tokens):
            if token.token_hash == token_hash and token.used_at is None and not token.expired(now):
                self._store.refresh_tokens[index] = token.consumed(now)
                return self._store.refresh_tokens[index]
        return None

    def find_by_hash(self, token_hash: str) -> RefreshToken | None:
        return next((t for t in self._store.refresh_tokens if t.token_hash == token_hash), None)

    def revoke_family(self, family_id: UUID) -> int:
        kept = [t for t in self._store.refresh_tokens if t.family_id != family_id]
        revoked = len(self._store.refresh_tokens) - len(kept)
        self._store.refresh_tokens[:] = kept
        return revoked


class FakeUnitOfWork(UnitOfWork):
    def __init__(self, store: FakeStore) -> None:
        self._store = store
        self._pending: list[RefreshToken] = []
        self._updates: dict[UUID, str] = {}
        self.accounts = FakeAccountRepository(store, self._updates)
        self.refresh_tokens = FakeRefreshTokenRepository(store, self._pending)

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self._pending.clear()
        self._updates.clear()

    def commit(self) -> None:
        self._store.refresh_tokens.extend(self._pending)
        for account_id, password_hash in self._updates.items():
            stored = self._store.accounts[account_id]
            self._store.accounts[account_id] = Account(
                stored.id,
                stored.email,
                password_hash,
                stored.role,
                stored.email_verified,
                stored.disabled,
            )
        self._store.commits += 1


class FakeClock(Clock):
    def __init__(self) -> None:
        self.current = START

    def now(self) -> datetime:
        return self.current


class FakePasswordVerifier(PasswordVerifier):
    """Hachage deterministe ; `outdated` simule des parametres argon2id qui ont change."""

    def __init__(self, outdated: bool = False) -> None:
        self.outdated = outdated
        self.verifications = 0
        self.decoys = 0
        self.hashed: list[str] = []

    @staticmethod
    def digest(password: str) -> str:
        return "hashed::" + hashlib.sha256(password.encode()).hexdigest()

    def verify(self, password_hash: str, password: str) -> bool:
        self.verifications += 1
        return password_hash == self.digest(password)

    def verify_decoy(self, password: str) -> None:
        self.decoys += 1

    def needs_rehash(self, password_hash: str) -> bool:
        return self.outdated

    def hash(self, password: str) -> str:
        self.hashed.append(password)
        return "rehashed::" + hashlib.sha256(password.encode()).hexdigest()


class FakeRefreshTokenGenerator(RefreshTokenGenerator):
    def generate(self) -> str:
        return "raw-refresh-token"

    def digest(self, token: str) -> str:
        return hashlib.sha256(token.encode()).hexdigest()


class FakeEmailFingerprinter(EmailFingerprinter):
    def fingerprint(self, email: str) -> str:
        return "fp-" + hashlib.sha256(email.encode()).hexdigest()[:8]


class FakeAccessTokenSigner(AccessTokenSigner):
    def __init__(self) -> None:
        self.signed: list[AccessTokenClaims] = []

    def sign(self, claims: AccessTokenClaims) -> str:
        self.signed.append(claims)
        return f"signed::{claims.subject}"


class FakeAccessTokenVerifier(AccessTokenVerifier):
    """Accepte `signed::<uuid>` ; `reject` force un motif de rejet."""

    def __init__(self, reject: TokenRejection | None = None) -> None:
        self.reject = reject

    def verify(self, token: str, now: datetime) -> AccessTokenClaims:
        if self.reject is not None:
            raise AccessTokenRejectedError(self.reject)
        if not token.startswith("signed::"):
            raise AccessTokenRejectedError(TokenRejection.INVALID)
        return AccessTokenClaims(
            UUID(token.removeprefix("signed::")), ("customer",), True, now, now, "jti"
        )
