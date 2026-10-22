from datetime import datetime
from uuid import UUID, uuid4

from app.admin.domain.exceptions.admin_errors import OperatorAlreadyExistsError
from app.backoffice.application import invitation_events as catalog
from app.backoffice.application.invitation_errors import (
    InvitationPasswordError,
    InvitationPhotoError,
    InvitationRefusedError,
)
from app.backoffice.application.invitation_unit_of_work_factory import (
    InvitationUnitOfWorkFactory,
)
from app.backoffice.domain.entities.operator_invitation import OperatorInvitation
from app.backoffice.domain.exceptions.aucun_visage import AucunVisage
from app.backoffice.domain.exceptions.image_invalide import ImageInvalide
from app.backoffice.domain.interfaces.challenge_token_generator import ChallengeTokenGenerator
from app.backoffice.domain.interfaces.reconnaissance_faciale import ReconnaissanceFaciale
from app.backoffice.domain.value_objects.face_images import validate_enrollment_photos
from app.core.events.business_event import BusinessEvent
from app.core.events.business_event_logger import BusinessEventLogger
from app.lockout.application.lockout_service import LockoutService
from app.lockout.application.lockout_steps import STEP_INVITATION
from app.lockout.domain.entities.lockout_subject import LockoutSubject
from app.lockout.domain.enums.subject_type import SubjectType
from app.login.domain.interfaces.clock import Clock
from app.login.domain.interfaces.email_fingerprinter import EmailFingerprinter
from app.registration.domain.exceptions.weak_password_error import WeakPasswordError
from app.registration.domain.interfaces.password_hasher import PasswordHasher
from app.registration.domain.services.password_policy import PasswordPolicy

UNKNOWN_ADDRESS = "unknown"


class CompleteOperatorInvitationUseCase:
    """Route publique : la personne invitee choisit son mot de passe et enregistre son visage.

    Ordre (le moins cher d'abord, rien d'ecrit avant la fin) :
    1. adresse bloquee ou jeton inconnu, expire, revoque, utilise : meme refus generique (et l'echec
       compte dans le verrouillage de l'adresse, etape `invitation`);
    2. mot de passe (politique de l'inscription) puis 3 a 10 photos : 422, ne compte pas;
    3. calcul du gabarit hors transaction : aucun visage, photo illisible : 422, ne compte pas, le
       jeton n'est PAS consomme et aucun compte n'est cree;
    4. UNE transaction : jeton verrouille et reverifie, compte operateur, gabarit chiffre, jeton
       consomme. Un compte deja cree entre-temps donne le refus generique.
    Les photos restent en memoire; seul le gabarit chiffre est conserve.
    """

    def __init__(
        self,
        unit_of_work: InvitationUnitOfWorkFactory,
        tokens: ChallengeTokenGenerator,
        password_policy: PasswordPolicy,
        hasher: PasswordHasher,
        recognizer: ReconnaissanceFaciale,
        lockout: LockoutService,
        fingerprinter: EmailFingerprinter,
        clock: Clock,
        events: BusinessEventLogger,
    ) -> None:
        self._unit_of_work = unit_of_work
        self._tokens = tokens
        self._password_policy = password_policy
        self._hasher = hasher
        self._recognizer = recognizer
        self._lockout = lockout
        self._fingerprinter = fingerprinter
        self._clock = clock
        self._events = events

    def execute(
        self, token: str, password: str, photos: list[bytes], client_ip: str | None = None
    ) -> UUID:
        now = self._clock.now()
        address_hash = self._fingerprinter.fingerprint(f"ip:{client_ip or UNKNOWN_ADDRESS}")
        if self._lockout.check(
            STEP_INVITATION, address_hash, now, SubjectType.SOURCE_ADDRESS
        ).locked:
            raise self._refuse(catalog.REASON_STEP_LOCKED, client_ip, None)
        digest = self._tokens.digest(token)
        with self._unit_of_work() as work:
            invitation = work.invitations.find(digest)
        if invitation is None or not invitation.usable(now):
            self._count_failure(address_hash, now, client_ip)
            raise self._refuse(catalog.REASON_INVALID_TOKEN, client_ip, None)
        email_hash = self._fingerprinter.fingerprint(invitation.email)
        self._check_password(password, email_hash, client_ip)
        template = self._template_of(photos, email_hash, client_ip)
        account_id = uuid4()
        password_hash = self._hasher.hash(password)
        try:
            self._create(invitation, account_id, password_hash, template, now)
        except (InvitationRefusedError, OperatorAlreadyExistsError):
            self._count_failure(address_hash, now, client_ip)
            raise self._refuse(catalog.REASON_ACCOUNT_EXISTS, client_ip, email_hash) from None
        self._lockout.clear(
            [LockoutSubject(STEP_INVITATION, address_hash, SubjectType.SOURCE_ADDRESS)]
        )
        self._events.log(
            BusinessEvent.success(
                catalog.OPERATOR_INVITE_CONSUMED,
                resource_type=catalog.RESOURCE_ACCOUNT,
                resource_id=str(account_id),
                attributes={"email_hash": email_hash, "photos": len(photos)},
            )
        )
        return account_id

    def _check_password(self, password: str, email_hash: str, client_ip: str | None) -> None:
        try:
            self._password_policy.validate(password)
        except WeakPasswordError as error:
            self._events.log(self._denied(catalog.REASON_WEAK_PASSWORD, client_ip, email_hash))
            raise InvitationPasswordError(error.code, error.message) from None

    def _template_of(self, photos: list[bytes], email_hash: str, client_ip: str | None) -> bytes:
        try:
            validate_enrollment_photos(photos)
        except ImageInvalide:
            reason = (
                catalog.REASON_PHOTO_COUNT
                if not 3 <= len(photos) <= 10
                else catalog.REASON_INVALID_PHOTO
            )
            self._events.log(self._denied(reason, client_ip, email_hash))
            message = (
                "Il faut de 3 à 10 photos."
                if reason == catalog.REASON_PHOTO_COUNT
                else "Photos JPEG ou PNG de 1 Mo au plus."
            )
            raise InvitationPhotoError(reason, message) from None
        try:
            return self._recognizer.enroler(photos)
        except AucunVisage:
            self._events.log(self._denied(catalog.REASON_NO_FACE, client_ip, email_hash))
            raise InvitationPhotoError(
                catalog.REASON_NO_FACE, "Aucun visage détecté dans les photos."
            ) from None
        except ImageInvalide:
            self._events.log(self._denied(catalog.REASON_INVALID_PHOTO, client_ip, email_hash))
            raise InvitationPhotoError(
                catalog.REASON_INVALID_PHOTO, "Une photo est illisible."
            ) from None

    def _create(
        self,
        invitation: OperatorInvitation,
        account_id: UUID,
        password_hash: str,
        template: bytes,
        now: datetime,
    ) -> None:
        with self._unit_of_work() as work:
            claimed = work.invitations.claim(invitation.digest, now)
            if claimed is None:
                raise InvitationRefusedError
            work.operators.add_operator(account_id, claimed.email, password_hash, now)
            work.templates.save(account_id, template, now)
            work.invitations.mark_consumed(claimed.digest, now)
            work.commit()

    def _count_failure(self, address_hash: str, now: datetime, client_ip: str | None) -> None:
        self._lockout.record_failure(
            STEP_INVITATION, address_hash, now, SubjectType.SOURCE_ADDRESS, client_ip
        )

    def _refuse(
        self, reason: str, client_ip: str | None, email_hash: str | None
    ) -> InvitationRefusedError:
        self._events.log(self._denied(reason, client_ip, email_hash))
        return InvitationRefusedError()

    @staticmethod
    def _denied(reason: str, client_ip: str | None, email_hash: str | None) -> BusinessEvent:
        attributes = {"email_hash": email_hash} if email_hash else {}
        return BusinessEvent.denied(
            catalog.OPERATOR_INVITE_REFUSED,
            reason,
            resource_type=catalog.RESOURCE_INVITATION,
            client_ip=client_ip,
            attributes=attributes,
        )
