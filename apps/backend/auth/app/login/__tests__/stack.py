"""Application reelle (routes, crypto, SQL) sur SQLite en memoire pour les tests d'integration."""

from uuid import UUID, uuid4

from argon2 import PasswordHasher as Argon2
from fastapi import FastAPI
from sqlalchemy import Engine, text

from app.core.events.business_event_logger import BusinessEventLogger
from app.login.__tests__.fakes import FakeClock, FakeEmailFingerprinter
from app.login.__tests__.schema import insert_user, migrated_engine
from app.login.application.get_current_account import GetCurrentAccountUseCase
from app.login.application.get_public_keys import GetPublicKeysUseCase
from app.login.application.login_account import LoginAccountUseCase
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
PASSWORD = "sentier-du-mont-blanc"
EMAIL = "camille@example.com"
CHEAP_ARGON2 = Argon2(time_cost=1, memory_cost=8, parallelism=1)


class LoginStack:
    def __init__(self, events: BusinessEventLogger, keys: Ed25519KeyRing | None = None) -> None:
        self.engine: Engine = migrated_engine()
        self.clock = FakeClock()
        self.keys = keys or Ed25519KeyRing.generate()
        self.verifier = Argon2PasswordVerifier(CHEAP_ARGON2)
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
            900,
            604800,
        )
        self.application.state.get_current_account_use_case = GetCurrentAccountUseCase(
            factory, access_verifier, self.clock, events
        )
        self.application.state.get_public_keys_use_case = GetPublicKeysUseCase(self.keys)

    def add_account(
        self,
        email: str = EMAIL,
        password: str = PASSWORD,
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
