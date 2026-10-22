from fastapi import FastAPI
from sqlalchemy import Engine

from app.core.config import Settings
from app.core.events.business_event_logger import BusinessEventLogger
from app.core.logging.email_pseudonymizer import build_pseudonymizer
from app.password_reset.application.request_password_reset import RequestPasswordResetUseCase
from app.password_reset.application.reset_password import ResetPasswordUseCase
from app.password_reset.infrastructure.clients.email_password_reset_mailer import (
    EmailPasswordResetMailer,
)
from app.password_reset.infrastructure.repositories.sqlalchemy_password_reset_unit_of_work import (
    SqlAlchemyPasswordResetUnitOfWork,
)
from app.registration.domain.services.password_policy import PasswordPolicy
from app.registration.infrastructure.clients.argon2_password_hasher import Argon2PasswordHasher
from app.registration.infrastructure.clients.email_sender_factory import EmailSenderFactory
from app.registration.infrastructure.clients.file_common_password_list import (
    FileCommonPasswordList,
)
from app.registration.infrastructure.clients.hmac_email_fingerprinter import (
    HmacEmailFingerprinter,
)
from app.registration.infrastructure.clients.secure_token_generator import SecureTokenGenerator
from app.registration.infrastructure.clients.system_clock import SystemClock


def wire_password_reset(
    application: FastAPI, settings: Settings, engine: Engine, events: BusinessEventLogger
) -> None:
    """Seul endroit qui assemble les implementations d'infrastructure de la tranche."""
    tokens = SecureTokenGenerator()
    clock = SystemClock()
    mailer = EmailPasswordResetMailer(EmailSenderFactory.build(settings), settings.public_base_url)
    application.state.request_password_reset_use_case = RequestPasswordResetUseCase(
        lambda: SqlAlchemyPasswordResetUnitOfWork(engine),
        tokens,
        mailer,
        clock,
        events,
        HmacEmailFingerprinter(build_pseudonymizer(settings.log_pseudonym_key)),
    )
    application.state.reset_password_use_case = ResetPasswordUseCase(
        lambda: SqlAlchemyPasswordResetUnitOfWork(engine),
        PasswordPolicy(FileCommonPasswordList()),
        Argon2PasswordHasher(),
        tokens,
        mailer,
        clock,
        events,
    )
