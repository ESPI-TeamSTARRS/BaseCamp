from uuid import UUID

from app.backoffice.application import backoffice_events as catalog
from app.backoffice.application.enrollment_errors import EnrollmentRefusedError
from app.backoffice.application.unit_of_work_factory import UnitOfWorkFactory
from app.backoffice.domain.exceptions.aucun_visage import AucunVisage
from app.backoffice.domain.exceptions.image_invalide import ImageInvalide
from app.backoffice.domain.interfaces.reconnaissance_faciale import ReconnaissanceFaciale
from app.backoffice.domain.value_objects.face_images import MAX_IMAGE_BYTES
from app.core.events.business_event import BusinessEvent
from app.core.events.business_event_logger import BusinessEventLogger
from app.login.application.unit_of_work_factory import UnitOfWorkFactory as AccountsUnitOfWork
from app.login.domain.interfaces.clock import Clock
from app.login.domain.interfaces.email_fingerprinter import EmailFingerprinter

OPERATOR_ROLE = "operator"
MIN_PHOTOS = 3
MAX_PHOTOS = 10
JPEG_MAGIC = b"\xff\xd8\xff"
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


class EnrollOperatorFaceUseCase:
    """Enrole le visage d'un operateur : 3 a 10 photos -> un gabarit, chiffre puis stocke.

    Commande d'exploitation seulement (aucune route). Les photos ne sont jamais ecrites sur disque ni
    journalisees : seul le gabarit (chiffre au repos) est conserve. Sans gabarit, la connexion du
    back-office est refusee. Reenroler remplace le gabarit existant.
    """

    def __init__(
        self,
        accounts: AccountsUnitOfWork,
        unit_of_work: UnitOfWorkFactory,
        recognizer: ReconnaissanceFaciale,
        fingerprinter: EmailFingerprinter,
        clock: Clock,
        events: BusinessEventLogger,
    ) -> None:
        self._accounts = accounts
        self._unit_of_work = unit_of_work
        self._recognizer = recognizer
        self._fingerprinter = fingerprinter
        self._clock = clock
        self._events = events

    def execute(self, email: str, photos: list[bytes]) -> UUID:
        address = email.strip().lower()
        email_hash = self._fingerprinter.fingerprint(address)
        with self._accounts() as work:
            account = work.accounts.find_by_email(address)
        if account is None or account.role != OPERATOR_ROLE or account.disabled:
            raise self._refuse(
                catalog.REASON_UNKNOWN_OPERATOR,
                "Aucun operateur actif avec cette adresse.",
                email_hash,
            )
        if not MIN_PHOTOS <= len(photos) <= MAX_PHOTOS:
            raise self._refuse(
                catalog.REASON_PHOTO_COUNT,
                f"Il faut de {MIN_PHOTOS} a {MAX_PHOTOS} photos.",
                email_hash,
            )
        if any(not self._readable(photo) for photo in photos):
            raise self._refuse(
                catalog.REASON_INVALID_PHOTO,
                f"Photos JPEG ou PNG de {MAX_IMAGE_BYTES // 1_048_576} Mo au plus.",
                email_hash,
            )
        try:
            template = self._recognizer.enroler(photos)
        except AucunVisage:
            raise self._refuse(
                catalog.REASON_NO_FACE, "Aucun visage detecte dans les photos.", email_hash
            ) from None
        except ImageInvalide:
            raise self._refuse(
                catalog.REASON_INVALID_PHOTO, "Une photo est illisible.", email_hash
            ) from None
        with self._unit_of_work() as work:
            work.templates.save(account.id, template, self._clock.now())
            work.commit()
        self._events.log(
            BusinessEvent.success(
                catalog.BACKOFFICE_FACE_ENROLLED,
                resource_type=catalog.RESOURCE_ACCOUNT,
                resource_id=str(account.id),
                attributes={"email_hash": email_hash, "photos": len(photos)},
            )
        )
        return account.id

    @staticmethod
    def _readable(photo: bytes) -> bool:
        """Controle sur les octets (signature et taille), comme pour les images de connexion."""
        return 0 < len(photo) <= MAX_IMAGE_BYTES and (
            photo.startswith(JPEG_MAGIC) or photo.startswith(PNG_MAGIC)
        )

    def _refuse(self, reason: str, message: str, email_hash: str) -> EnrollmentRefusedError:
        self._events.log(
            BusinessEvent.denied(
                catalog.BACKOFFICE_FACE_ENROLLMENT_REFUSED,
                reason,
                resource_type=catalog.RESOURCE_ACCOUNT,
                attributes={"email_hash": email_hash},
            )
        )
        return EnrollmentRefusedError(reason, message)
