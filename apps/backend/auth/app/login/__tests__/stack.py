"""Application reelle (routes, crypto, SQL) sur SQLite en memoire pour les tests d'integration."""

from uuid import UUID, uuid4

from argon2 import PasswordHasher as Argon2
from fastapi import FastAPI
from sqlalchemy import Engine, text

from app.core.events.business_event_logger import BusinessEventLogger
from app.lockout.__tests__.fakes import FIVE_IN_FIFTEEN
from app.lockout.application.lockout_service import LockoutService
from app.lockout.infrastructure.repositories.sqlalchemy_lockout_unit_of_work import (
    SqlAlchemyLockoutUnitOfWork,
)
from app.login.__tests__.fakes import FakeClock, FakeEmailFingerprinter
from app.login.__tests__.schema import insert_user, migrated_engine
from app.login.application.authorize_request import AuthorizeRequestUseCase
from app.login.application.get_current_account import GetCurrentAccountUseCase
from app.login.application.get_public_keys import GetPublicKeysUseCase
from app.login.application.login_account import LoginAccountUseCase
from app.login.application.logout_session import LogoutSessionUseCase
from app.login.application.refresh_session import RefreshSessionUseCase
from app.login.infrastructure.clients.argon2_password_verifier import Argon2PasswordVerifier
from app.login.infrastructure.clients.ed25519_key_ring import Ed25519KeyRing
from app.login.infrastructure.clients.jwt_access_token_signer import JwtAccessTokenSigner
from app.login.infrastructure.clients.jwt_access_token_verifier import JwtAccessTokenVerifier
from app.login.infrastructure.clients.secure_refresh_token_generator import (
    SecureRefreshTokenGenerator,
)
from app.login.infrastructure.repositories.sqlalchemy_unit_of_work import SqlAlchemyUnitOfWork
from app.main import create_app

ISSUER = "basecamp-auth"
AUDIENCE = "basecamp-client-api"
ACCOUNT_SECRET = "sentier-du-mont-blanc"
EMAIL = "camille@example.com"
OWASP_ARGON2 = Argon2(time_cost=2, memory_cost=19456, parallelism=1)


class LoginStack:
    def __init__(self, events: BusinessEventLogger, keys: Ed25519KeyRing | None = None) -> None:
        self.engine: Engine = migrated_engine()
        self.clock = FakeClock()
        self.keys = keys or Ed25519KeyRing.generate()
        self.verifier = Argon2PasswordVerifier(OWASP_ARGON2)
        self.application: FastAPI = create_app()
        factory = lambda: SqlAlchemyUnitOfWork(self.engine)  # noqa: E731
        access_verifier = JwtAccessTokenVerifier(self.keys, ISSUER, AUDIENCE)
        self.application.state.login_account_use_case = LoginAccountUseCase(
            factory,
            self.verifier,
            JwtAccessTokenSigner(self.keys, ISSUER, AUDIENCE),
            SecureRefreshTokenGenerator(),
            self.clock,
            events,
            FakeEmailFingerprinter(),
            LockoutService(
                lambda: SqlAlchemyLockoutUnitOfWork(self.engine), FIVE_IN_FIFTEEN, events
            ),
            900,
            604800,
        )
        refresh_tokens = SecureRefreshTokenGenerator()
        self.application.state.refresh_session_use_case = RefreshSessionUseCase(
            factory,
            JwtAccessTokenSigner(self.keys, ISSUER, AUDIENCE),
            refresh_tokens,
            self.clock,
            events,
            900,
            604800,
        )
        self.application.state.logout_session_use_case = LogoutSessionUseCase(
            factory, refresh_tokens, events
        )
        self.application.state.authorize_request_use_case = AuthorizeRequestUseCase(
            factory, access_verifier, self.clock, events
        )
        self.application.state.get_current_account_use_case = GetCurrentAccountUseCase(
            factory, access_verifier, self.clock, events
        )
        self.application.state.get_public_keys_use_case = GetPublicKeysUseCase(self.keys)

    def add_account(
        self,
        email: str = EMAIL,
        password: str = ACCOUNT_SECRET,
        role: str = "customer",
        verified: bool = True,
        disabled: bool = False,
        user_id: UUID | None = None,
    ) -> UUID:
        user_id = user_id or uuid4()
        insert_user(
            self.engine, user_id, email, self.verifier.hash(password), role, verified, disabled
        )
        return user_id

    def scalar(self, sql: str) -> object:
        with self.engine.connect() as connection:
            return connection.execute(text(sql)).scalar_one()

    def column(self, sql: str) -> list[object]:
        with self.engine.connect() as connection:
            return list(connection.execute(text(sql)).scalars())
