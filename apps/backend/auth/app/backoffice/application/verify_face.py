from datetime import datetime

from app.backoffice.application import backoffice_events as catalog
from app.backoffice.application.backoffice_errors import (
    BackofficeRefusedError,
    FaceImageInvalidError,
    FaceTemplateInvalidError,
)
from app.backoffice.application.unit_of_work_factory import UnitOfWorkFactory
from app.backoffice.domain.entities.login_challenge import LoginChallenge
from app.backoffice.domain.exceptions.gabarit_invalide import GabaritInvalide
from app.backoffice.domain.exceptions.image_invalide import ImageInvalide
from app.backoffice.domain.interfaces.challenge_token_generator import ChallengeTokenGenerator
from app.backoffice.domain.interfaces.reconnaissance_faciale import ReconnaissanceFaciale
from app.backoffice.domain.value_objects.face_images import validate_face_images
from app.core.events.business_event import BusinessEvent
from app.core.events.business_event_logger import BusinessEventLogger
from app.lockout.application.lockout_service import LockoutService
from app.lockout.application.lockout_steps import STEP_FACE
from app.lockout.domain.enums.subject_type import SubjectType
from app.login.domain.interfaces.clock import Clock


class VerifyFaceUseCase:
    """Deuxieme temps : le visage, avant le mot de passe.

    Le defi est PRIS (usage unique) : il ne survit qu'a un visage accepte (il est alors remis avec
    `face_ok`) ou a une image illisible (erreur du client, pas un echec). Tout le reste le detruit :
    visage refuse (compte dans le verrouillage de l'etape `face`, par compte et par adresse), etape
    verrouillee, gabarit invalide (409, journalise, ne compte pas). Un defi leurre ou un operateur sans
    gabarit sont refuses comme un visage faux. Le verificateur repond oui ou non : aucun score.
    Plusieurs images : le visage est accepte si l'une d'elles est reconnue.
    """

    def __init__(
        self,
        unit_of_work: UnitOfWorkFactory,
        tokens: ChallengeTokenGenerator,
        recognizer: ReconnaissanceFaciale,
        lockout: LockoutService,
        clock: Clock,
        events: BusinessEventLogger,
    ) -> None:
        self._unit_of_work = unit_of_work
        self._tokens = tokens
        self._recognizer = recognizer
        self._lockout = lockout
        self._clock = clock
        self._events = events

    def execute(self, challenge_id: str, images: list[bytes], client_ip: str | None = None) -> None:
        try:
            captures = validate_face_images(images)
        except ImageInvalide:
            raise FaceImageInvalidError from None
        now = self._clock.now()
        digest = self._tokens.digest(challenge_id)
        with self._unit_of_work() as work:
            challenge = work.challenges.take(digest, now)
            work.commit()
        if challenge is None:
            raise self._refuse(catalog.REASON_INVALID_CHALLENGE, "", client_ip, None)
        if self._locked(challenge, now):
            self._events.log(self._lock_event(challenge, client_ip))
            raise self._refuse(catalog.REASON_STEP_LOCKED, challenge.email_hash, client_ip, None)
        template = self._template_or_refuse(challenge, client_ip)
        if template is None:
            cause = catalog.CAUSE_UNKNOWN_ACCOUNT if challenge.decoy else catalog.CAUSE_NO_TEMPLATE
            raise self._failed(challenge, client_ip, cause, now)
        if not self._recognized(captures, template, challenge, client_ip):
            raise self._failed(challenge, client_ip, catalog.CAUSE_NO_MATCH, now)
        with self._unit_of_work() as work:
            work.challenges.add(challenge.with_face_ok())
            work.commit()
        self._events.log(
            BusinessEvent.success(
                catalog.BACKOFFICE_FACE_RESULT,
                resource_type=catalog.RESOURCE_CHALLENGE,
                attributes={"email_hash": challenge.email_hash, "step": STEP_FACE},
            )
        )

    def _template_or_refuse(self, challenge: LoginChallenge, client_ip: str | None) -> bytes | None:
        """Gabarit de l'operateur; un gabarit qui ne se dechiffre pas est un gabarit invalide (409)."""
        try:
            return self._template_of(challenge)
        except GabaritInvalide:
            self._events.log(
                BusinessEvent.denied(
                    catalog.BACKOFFICE_FACE_RESULT,
                    catalog.REASON_INVALID_TEMPLATE,
                    resource_type=catalog.RESOURCE_CHALLENGE,
                    client_ip=client_ip,
                    attributes={"email_hash": challenge.email_hash, "step": STEP_FACE},
                )
            )
            raise FaceTemplateInvalidError from None

    def _template_of(self, challenge: LoginChallenge) -> bytes | None:
        if challenge.account_id is None:
            return None
        with self._unit_of_work() as work:
            return work.templates.find(challenge.account_id)

    def _recognized(
        self,
        captures: tuple[bytes, ...],
        template: bytes,
        challenge: LoginChallenge,
        client_ip: str | None,
    ) -> bool:
        try:
            return any(self._recognizer.verifier(capture, template) for capture in captures)
        except ImageInvalide:
            self._give_back(challenge)
            raise FaceImageInvalidError from None
        except GabaritInvalide:
            self._events.log(
                BusinessEvent.denied(
                    catalog.BACKOFFICE_FACE_RESULT,
                    catalog.REASON_INVALID_TEMPLATE,
                    resource_type=catalog.RESOURCE_CHALLENGE,
                    client_ip=client_ip,
                    attributes={"email_hash": challenge.email_hash, "step": STEP_FACE},
                )
            )
            raise FaceTemplateInvalidError from None

    def _give_back(self, challenge: LoginChallenge) -> None:
        """Image illisible : le defi reste utilisable (ce n'est pas un echec du visiteur)."""
        with self._unit_of_work() as work:
            work.challenges.add(challenge)
            work.commit()

    def _locked(self, challenge: LoginChallenge, now: datetime) -> bool:
        by_account = self._lockout.check(STEP_FACE, challenge.email_hash, now)
        by_address = self._lockout.check(
            STEP_FACE, challenge.address_hash, now, SubjectType.SOURCE_ADDRESS
        )
        return by_account.locked or by_address.locked

    def _failed(
        self,
        challenge: LoginChallenge,
        client_ip: str | None,
        cause: str,
        now: datetime,
    ) -> BackofficeRefusedError:
        account_status = self._lockout.record_failure(
            STEP_FACE, challenge.email_hash, now, client_ip=client_ip
        )
        address_status = self._lockout.record_failure(
            STEP_FACE,
            challenge.address_hash,
            now,
            SubjectType.SOURCE_ADDRESS,
            client_ip,
        )
        if account_status.just_locked or address_status.just_locked:
            self._events.log(self._lock_event(challenge, client_ip))
        return self._refuse(catalog.REASON_FACE_REFUSED, challenge.email_hash, client_ip, cause)

    def _lock_event(self, challenge: LoginChallenge, client_ip: str | None) -> BusinessEvent:
        return BusinessEvent.denied(
            catalog.BACKOFFICE_LOCKOUT,
            catalog.REASON_STEP_LOCKED,
            resource_type=catalog.RESOURCE_CHALLENGE,
            client_ip=client_ip,
            attributes={"email_hash": challenge.email_hash, "step": STEP_FACE},
        )

    def _refuse(
        self, reason: str, email_hash: str, client_ip: str | None, cause: str | None
    ) -> BackofficeRefusedError:
        attributes: dict[str, str | bool | int | float | None] = {"step": STEP_FACE}
        if email_hash:
            attributes["email_hash"] = email_hash
        if cause:
            attributes["cause"] = cause
        self._events.log(
            BusinessEvent.denied(
                catalog.BACKOFFICE_FACE_RESULT,
                reason,
                resource_type=catalog.RESOURCE_CHALLENGE,
                client_ip=client_ip,
                attributes=attributes,
            )
        )
        return BackofficeRefusedError()
