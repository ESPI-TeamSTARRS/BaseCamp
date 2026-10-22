from fastapi import FastAPI
from sqlalchemy import Engine

from app.backoffice.application.complete_operator_invitation import (
    CompleteOperatorInvitationUseCase,
)
from app.backoffice.application.create_operator_invitation import (
    CreateOperatorInvitationUseCase,
)
from app.backoffice.application.enroll_operator_face import EnrollOperatorFaceUseCase
from app.backoffice.application.identify_operator import IdentifyOperatorUseCase
from app.backoffice.application.revoke_operator_invitation import (
    RevokeOperatorInvitationUseCase,
)
from app.backoffice.application.verify_face import VerifyFaceUseCase
from app.backoffice.application.verify_operator_password import VerifyOperatorPasswordUseCase
from app.backoffice.domain.interfaces.reconnaissance_faciale import ReconnaissanceFaciale
from app.backoffice.infrastructure.clients.face_template_key_file import load_template_cipher
from app.backoffice.infrastructure.clients.fake_reconnaissance_faciale import (
    FakeReconnaissanceFaciale,
)
from app.backoffice.infrastructure.clients.secure_challenge_token_generator import (
    SecureChallengeTokenGenerator,
)
from app.backoffice.infrastructure.repositories.sqlalchemy_backoffice_unit_of_work import (
    SqlAlchemyBackofficeUnitOfWork,
)
from app.backoffice.infrastructure.repositories.sqlalchemy_invitation_unit_of_work import (
    SqlAlchemyInvitationUnitOfWork,
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
from app.registration.domain.services.password_policy import PasswordPolicy
from app.registration.infrastructure.clients.argon2_password_hasher import Argon2PasswordHasher
from app.registration.infrastructure.clients.file_common_password_list import (
    FileCommonPasswordList,
)


def build_face_recognizer(settings: Settings) -> ReconnaissanceFaciale:
    """Adaptateur de reconnaissance faciale choisi par la configuration.

    Le faux n'existe qu'en developpement (`APP_FACE_VERIFIER=fake`). Aucun adaptateur reel n'est
    encore branche (ticket du package) : sans adaptateur, le service refuse de demarrer des que le
    back-office est active, au lieu de laisser une porte sans verificateur.
    """
    if settings.face_verifier == "fake" and settings.environment in DEVELOPMENT_ENVIRONMENTS:
        return FakeReconnaissanceFaciale()
    if settings.face_verifier == "visage-id":
        try:
            from app.backoffice.infrastructure.clients.visage_id_reconnaissance import (
                VisageIdReconnaissance,
            )
        except ImportError:
            raise RuntimeError("APP_FACE_VERIFIER=visage-id needs the visage-id package") from None
        return VisageIdReconnaissance(settings.face_threshold)
    raise RuntimeError("APP_BACKOFFICE_ENABLED needs a real face verifier adapter")


def build_enrollment(
    settings: Settings, engine: Engine, events: BusinessEventLogger
) -> EnrollOperatorFaceUseCase:
    """Cas d'usage de la commande `enroll-face` (le verificateur reel, jamais le faux hors dev)."""
    cipher = load_template_cipher(settings.face_template_key_file)
    return EnrollOperatorFaceUseCase(
        lambda: SqlAlchemyUnitOfWork(engine),
        lambda: SqlAlchemyBackofficeUnitOfWork(engine, cipher),
        build_face_recognizer(settings),
        HmacEmailFingerprinter(build_pseudonymizer(settings.log_pseudonym_key)),
        SystemClock(),
        events,
    )


def build_invitation_creation(
    settings: Settings, engine: Engine, events: BusinessEventLogger
) -> CreateOperatorInvitationUseCase:
    """Cas d'usage de `create-operator-invite` (commande d'exploitation, aucune route)."""
    cipher = load_template_cipher(settings.face_template_key_file)
    return CreateOperatorInvitationUseCase(
        lambda: SqlAlchemyUnitOfWork(engine),
        lambda: SqlAlchemyInvitationUnitOfWork(engine, cipher),
        SecureChallengeTokenGenerator(),
        HmacEmailFingerprinter(build_pseudonymizer(settings.log_pseudonym_key)),
        SystemClock(),
        events,
        settings.admin_base_url,
        settings.operator_invite_ttl_seconds,
    )


def build_invitation_revocation(
    settings: Settings, engine: Engine, events: BusinessEventLogger
) -> RevokeOperatorInvitationUseCase:
    """Cas d'usage de `revoke-operator-invite`."""
    cipher = load_template_cipher(settings.face_template_key_file)
    return RevokeOperatorInvitationUseCase(
        lambda: SqlAlchemyInvitationUnitOfWork(engine, cipher),
        HmacEmailFingerprinter(build_pseudonymizer(settings.log_pseudonym_key)),
        SystemClock(),
        events,
    )


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

    cipher = load_template_cipher(settings.face_template_key_file)

    def unit_of_work() -> SqlAlchemyBackofficeUnitOfWork:
        return SqlAlchemyBackofficeUnitOfWork(engine, cipher)

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
    application.state.complete_operator_invitation_use_case = CompleteOperatorInvitationUseCase(
        lambda: SqlAlchemyInvitationUnitOfWork(engine, cipher),
        tokens,
        PasswordPolicy(FileCommonPasswordList()),
        Argon2PasswordHasher(),
        build_face_recognizer(settings),
        lockout,
        fingerprinter,
        clock,
        events,
    )
