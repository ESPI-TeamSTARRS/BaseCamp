from fastapi import FastAPI
from sqlalchemy import Engine

from app.core.config import Settings
from app.core.events.business_event_logger import BusinessEventLogger
from app.core.logging.email_pseudonymizer import build_pseudonymizer
from app.registration.application.register_account import RegisterAccountUseCase
from app.registration.application.verify_email import VerifyEmailUseCase
from app.registration.domain.services.password_policy import PasswordPolicy
from app.registration.infrastructure.clients.argon2_password_hasher import Argon2PasswordHasher
from app.registration.infrastructure.clients.email_registration_mailer import (
    EmailRegistrationMailer,
)
from app.registration.infrastructure.clients.email_sender_factory import EmailSenderFactory
from app.registration.infrastructure.clients.file_common_password_list import (
    FileCommonPasswordList,
)
from app.registration.infrastructure.clients.hmac_email_fingerprinter import (
    HmacEmailFingerprinter,
)
from app.registration.infrastructure.clients.secure_token_generator import SecureTokenGenerator
from app.registration.infrastructure.clients.system_clock import SystemClock
from app.registration.infrastructure.repositories.sqlalchemy_unit_of_work import (
    SqlAlchemyUnitOfWork,
)


def wire_registration(
    application: FastAPI, settings: Settings, engine: Engine, events: BusinessEventLogger
) -> None:
    """Seul endroit qui assemble les implementations d'infrastructure de la tranche."""
    tokens = SecureTokenGenerator()
    clock = SystemClock()
    mailer = EmailRegistrationMailer(EmailSenderFactory.build(settings), settings.public_base_url)
    application.state.register_account_use_case = RegisterAccountUseCase(
        lambda: SqlAlchemyUnitOfWork(engine),
        PasswordPolicy(FileCommonPasswordList()),
        Argon2PasswordHasher(),
        tokens,
        mailer,
        clock,
        events,
        HmacEmailFingerprinter(build_pseudonymizer(settings.log_pseudonym_key)),
    )
    application.state.verify_email_use_case = VerifyEmailUseCase(
        lambda: SqlAlchemyUnitOfWork(engine), tokens, clock, events
    )
