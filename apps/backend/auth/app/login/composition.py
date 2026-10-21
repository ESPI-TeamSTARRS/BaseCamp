from pathlib import Path

from fastapi import FastAPI
from sqlalchemy import Engine

from app.core.config import Settings
from app.core.events.business_event_logger import BusinessEventLogger
from app.core.logging.email_pseudonymizer import build_pseudonymizer
from app.lockout.composition import build_lockout_service
from app.login.application.authorize_request import AuthorizeRequestUseCase
from app.login.application.get_current_account import GetCurrentAccountUseCase
from app.login.application.get_public_keys import GetPublicKeysUseCase
from app.login.application.login_account import LoginAccountUseCase
from app.login.application.logout_session import LogoutSessionUseCase
from app.login.application.refresh_session import RefreshSessionUseCase
from app.login.infrastructure.clients.argon2_password_verifier import Argon2PasswordVerifier
from app.login.infrastructure.clients.ed25519_key_ring import (
    Ed25519KeyRing,
    LazyEd25519KeyRing,
)
from app.login.infrastructure.clients.hmac_email_fingerprinter import HmacEmailFingerprinter
from app.login.infrastructure.clients.jwt_access_token_signer import JwtAccessTokenSigner
from app.login.infrastructure.clients.jwt_access_token_verifier import JwtAccessTokenVerifier
from app.login.infrastructure.clients.secure_refresh_token_generator import (
    SecureRefreshTokenGenerator,
)
from app.login.infrastructure.clients.system_clock import SystemClock
from app.login.infrastructure.repositories.sqlalchemy_unit_of_work import SqlAlchemyUnitOfWork
from app.service_token.infrastructure.clients.ed25519_key_store import Ed25519KeyStore


def build_key_ring(settings: Settings) -> Ed25519KeyRing:
    """Meme cle privee (secret monte) que les jetons de service, lue au premier usage."""
    key_store = Ed25519KeyStore(settings.jwt_private_key_file, settings.jwt_public_key_file)
    previous = settings.jwt_previous_public_keys_dir
    previous_dir = Path(previous) if previous else None
    return LazyEd25519KeyRing(
        lambda: Ed25519KeyRing.from_pem(key_store.private_key_pem, previous_dir)
    )


def wire_login(
    application: FastAPI, settings: Settings, engine: Engine, events: BusinessEventLogger
) -> None:
    """Seul endroit qui assemble les implementations d'infrastructure de la tranche."""
    keys = build_key_ring(settings)
    clock = SystemClock()

    def unit_of_work() -> SqlAlchemyUnitOfWork:
        return SqlAlchemyUnitOfWork(engine)

    application.state.login_account_use_case = LoginAccountUseCase(
        unit_of_work,
        Argon2PasswordVerifier(),
        JwtAccessTokenSigner(keys, settings.jwt_issuer, settings.jwt_audience),
        SecureRefreshTokenGenerator(),
        clock,
        events,
        HmacEmailFingerprinter(build_pseudonymizer(settings.log_pseudonym_key)),
        build_lockout_service(settings, engine, events),
        settings.access_token_ttl_seconds,
        settings.refresh_token_ttl_seconds,
    )
    refresh_tokens = SecureRefreshTokenGenerator()
    application.state.refresh_session_use_case = RefreshSessionUseCase(
        unit_of_work,
        JwtAccessTokenSigner(keys, settings.jwt_issuer, settings.jwt_audience),
        refresh_tokens,
        clock,
        events,
        settings.access_token_ttl_seconds,
        settings.refresh_token_ttl_seconds,
    )
    application.state.logout_session_use_case = LogoutSessionUseCase(
        unit_of_work, refresh_tokens, events
    )
    application.state.authorize_request_use_case = AuthorizeRequestUseCase(
        unit_of_work,
        JwtAccessTokenVerifier(keys, settings.jwt_issuer, settings.jwt_audience),
        clock,
        events,
    )
    application.state.get_current_account_use_case = GetCurrentAccountUseCase(
        unit_of_work,
        JwtAccessTokenVerifier(keys, settings.jwt_issuer, settings.jwt_audience),
        clock,
        events,
    )
    application.state.get_public_keys_use_case = GetPublicKeysUseCase(keys)
