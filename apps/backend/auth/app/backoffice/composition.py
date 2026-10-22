from fastapi import FastAPI
from sqlalchemy import Engine

from app.backoffice.application.identify_operator import IdentifyOperatorUseCase
from app.backoffice.application.verify_face import VerifyFaceUseCase
from app.backoffice.application.verify_operator_password import VerifyOperatorPasswordUseCase
from app.backoffice.domain.interfaces.reconnaissance_faciale import ReconnaissanceFaciale
from app.backoffice.infrastructure.clients.fake_reconnaissance_faciale import (
    FakeReconnaissanceFaciale,
)
from app.backoffice.infrastructure.clients.secure_challenge_token_generator import (
    SecureChallengeTokenGenerator,
)
from app.backoffice.infrastructure.repositories.sqlalchemy_backoffice_unit_of_work import (
    SqlAlchemyBackofficeUnitOfWork,
)
from app.core.config import DEVELOPMENT_ENVIRONMENTS, Settings
from app.core.events.business_event_logger import BusinessEventLogger
from app.core.logging.email_pseudonymizer import build_pseudonymizer
from app.lockout.composition import build_lockout_service
from app.login.composition import build_key_ring
from app.login.infrastructure.clients.argon2_password_verifier import Argon2PasswordVerifier
from app.login.infrastructure.clients.hmac_email_fingerprinter import HmacEmailFingerprinter
from app.login.infrastructure.clients.jwt_access_token_signer import JwtAccessTokenSigner
from app.login.infrastructure.clients.system_clock import SystemClock
from app.login.infrastructure.repositories.sqlalchemy_unit_of_work import SqlAlchemyUnitOfWork


def build_face_recognizer(settings: Settings) -> ReconnaissanceFaciale:
    """Adaptateur de reconnaissance faciale choisi par la configuration.

    Le faux n'existe qu'en developpement (`APP_FACE_VERIFIER=fake`). Aucun adaptateur reel n'est
    encore branche (ticket du package) : sans adaptateur, le service refuse de demarrer des que le
    back-office est active, au lieu de laisser une porte sans verificateur.
    """
    if settings.face_verifier == "fake" and settings.environment in DEVELOPMENT_ENVIRONMENTS:
        return FakeReconnaissanceFaciale()
    raise RuntimeError("APP_BACKOFFICE_ENABLED needs a real face verifier adapter")


def wire_backoffice(
    application: FastAPI, settings: Settings, engine: Engine, events: BusinessEventLogger
) -> None:
    """Seul endroit qui assemble les implementations d'infrastructure de la tranche."""
    clock = SystemClock()
    tokens = SecureChallengeTokenGenerator()
    fingerprinter = HmacEmailFingerprinter(build_pseudonymizer(settings.log_pseudonym_key))
    lockout = build_lockout_service(settings, engine, events)

    def accounts() -> SqlAlchemyUnitOfWork:
        return SqlAlchemyUnitOfWork(engine)

    def unit_of_work() -> SqlAlchemyBackofficeUnitOfWork:
        return SqlAlchemyBackofficeUnitOfWork(engine)

    application.state.identify_operator_use_case = IdentifyOperatorUseCase(
        accounts,
        unit_of_work,
        tokens,
        fingerprinter,
        clock,
        events,
        settings.backoffice_challenge_ttl_seconds,
    )
    application.state.verify_face_use_case = VerifyFaceUseCase(
        unit_of_work, tokens, build_face_recognizer(settings), lockout, clock, events
    )
    application.state.verify_operator_password_use_case = VerifyOperatorPasswordUseCase(
        accounts,
        unit_of_work,
        tokens,
        Argon2PasswordVerifier(),
        JwtAccessTokenSigner(build_key_ring(settings), settings.jwt_issuer, settings.jwt_audience),
        lockout,
        clock,
        events,
        settings.access_token_ttl_seconds,
    )
