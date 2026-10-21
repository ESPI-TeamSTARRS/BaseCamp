from app.core.events.business_event import BusinessEvent
from app.core.events.business_event_logger import BusinessEventLogger
from app.password_reset.application import password_reset_events as catalog
from app.password_reset.application.pending_reset_email import PendingResetEmail
from app.password_reset.application.unit_of_work_factory import UnitOfWorkFactory
from app.password_reset.domain.entities.password_reset_token import PasswordResetToken
from app.password_reset.domain.interfaces.password_reset_mailer import PasswordResetMailer
from app.registration.domain.exceptions.invalid_email_error import InvalidEmailError
from app.registration.domain.exceptions.mail_delivery_error import MailDeliveryError
from app.registration.domain.interfaces.clock import Clock
from app.registration.domain.interfaces.email_fingerprinter import EmailFingerprinter
from app.registration.domain.interfaces.token_generator import TokenGenerator
from app.registration.domain.value_objects.email_address import EmailAddress


class RequestPasswordResetUseCase:
    """Demande de lien : la reponse HTTP ne depend ni de l'existence du compte ni de la messagerie.

    `execute` fait le travail en base (identique, compte connu ou non, sauf l'emission du jeton)
    et rend l'email a envoyer; `deliver` l'envoie apres la reponse. Chaque issue emet un evenement
    metier (jamais d'email en clair : seulement son empreinte).
    """

    def __init__(
        self,
        unit_of_work: UnitOfWorkFactory,
        tokens: TokenGenerator,
        mailer: PasswordResetMailer,
        clock: Clock,
        events: BusinessEventLogger,
        fingerprinter: EmailFingerprinter,
    ) -> None:
        self._unit_of_work = unit_of_work
        self._tokens = tokens
        self._mailer = mailer
        self._clock = clock
        self._events = events
        self._fingerprinter = fingerprinter

    def execute(self, email: str) -> PendingResetEmail | None:
        try:
            address = EmailAddress.of(email)
        except InvalidEmailError:
            self._reject(catalog.REASON_INVALID_EMAIL)
            return None
        fingerprint = self._fingerprinter.fingerprint(address)
        now = self._clock.now()
        token = self._tokens.generate()  # genere pour tous : meme cout, compte connu ou non
        with self._unit_of_work() as work:
            if not work.throttle.allow(fingerprint, now):
                self._reject(catalog.REASON_RATE_LIMITED, fingerprint)
                return None
            account = work.accounts.find_by_email(address)
            if account is not None:
                digest = self._tokens.digest(token)
                work.tokens.replace(PasswordResetToken.issue(account.id, digest, now), now)
            work.commit()
        if account is None:
            self._reject(catalog.REASON_UNKNOWN_ACCOUNT, fingerprint)
            return None
        self._events.log(
            BusinessEvent.success(
                catalog.RESET_REQUESTED,
                resource_type=catalog.RESOURCE_ACCOUNT,
                resource_id=str(account.id),
                attributes={"email_hash": fingerprint},
            )
        )
        return PendingResetEmail(address, token)

    def deliver(self, pending: PendingResetEmail) -> None:
        try:
            self._mailer.send_reset_link(pending.to, pending.token)
        except MailDeliveryError:
            self._events.log(
                BusinessEvent.error(
                    catalog.EMAIL_DELIVERY_FAILED,
                    catalog.REASON_MAIL_DELIVERY_FAILED,
                    resource_type=catalog.RESOURCE_PASSWORD_RESET,
                    attributes={"kind": catalog.KIND_RESET_LINK},
                )
            )

    def _reject(self, reason: str, fingerprint: str | None = None) -> None:
        attributes = {"email_hash": fingerprint} if fingerprint else {}
        self._events.log(
            BusinessEvent.denied(
                catalog.RESET_REJECTED,
                reason,
                resource_type=catalog.RESOURCE_ACCOUNT,
                attributes=attributes,
            )
        )
