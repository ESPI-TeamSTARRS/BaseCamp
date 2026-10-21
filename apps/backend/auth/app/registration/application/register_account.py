from collections.abc import Callable

from app.core.events.business_event import BusinessEvent
from app.core.events.business_event_logger import BusinessEventLogger
from app.registration.application import registration_events as catalog
from app.registration.application.invalid_registration_error import InvalidRegistrationError
from app.registration.application.unit_of_work_factory import UnitOfWorkFactory
from app.registration.domain.entities.user import User
from app.registration.domain.entities.verification_token import VerificationToken
from app.registration.domain.exceptions.email_already_registered_error import (
    EmailAlreadyRegisteredError,
)
from app.registration.domain.exceptions.invalid_email_error import InvalidEmailError
from app.registration.domain.exceptions.mail_delivery_error import MailDeliveryError
from app.registration.domain.exceptions.weak_password_error import WeakPasswordError
from app.registration.domain.interfaces.clock import Clock
from app.registration.domain.interfaces.email_fingerprinter import EmailFingerprinter
from app.registration.domain.interfaces.password_hasher import PasswordHasher
from app.registration.domain.interfaces.registration_mailer import RegistrationMailer
from app.registration.domain.interfaces.token_generator import TokenGenerator
from app.registration.domain.services.password_policy import PasswordPolicy
from app.registration.domain.value_objects.email_address import EmailAddress


class RegisterAccountUseCase:
    """Inscription sans enumeration : adresse libre ou deja inscrite, meme issue, meme cout.

    Le mot de passe est toujours hache avant de savoir si l'adresse existe, et le titulaire d'un
    compte existant est prevenu par email plutot que par la reponse HTTP. Chaque issue emet un
    evenement metier (jamais d'email en clair : seulement son empreinte).
    """

    def __init__(
        self,
        unit_of_work: UnitOfWorkFactory,
        password_policy: PasswordPolicy,
        hasher: PasswordHasher,
        tokens: TokenGenerator,
        mailer: RegistrationMailer,
        clock: Clock,
        events: BusinessEventLogger,
        fingerprinter: EmailFingerprinter,
    ) -> None:
        self._unit_of_work = unit_of_work
        self._password_policy = password_policy
        self._hasher = hasher
        self._tokens = tokens
        self._mailer = mailer
        self._clock = clock
        self._events = events
        self._fingerprinter = fingerprinter

    def execute(self, email: str, password: str) -> None:
        address = self._validate(email, password)
        password_hash = self._hasher.hash(password)
        try:
            user, token = self._create_account(address, password_hash)
        except EmailAlreadyRegisteredError:
            self._reject(catalog.REASON_EMAIL_ALREADY_USED, address)
            self._deliver("account_exists", lambda: self._mailer.send_account_exists(address))
            return
        self._events.log(
            BusinessEvent.success(
                catalog.ACCOUNT_REGISTERED,
                resource_type=catalog.RESOURCE_ACCOUNT,
                resource_id=str(user.id),
                attributes={"email_hash": self._fingerprinter.fingerprint(address)},
            )
        )
        self._deliver("verification", lambda: self._mailer.send_verification(address, token))

    def _validate(self, email: str, password: str) -> EmailAddress:
        violations: dict[str, str] = {}
        rules: dict[str, str] = {}
        address: EmailAddress | None = None
        try:
            address = EmailAddress.of(email)
        except InvalidEmailError as error:
            violations["email"] = error.message
            rules["email"] = error.code
        try:
            self._password_policy.validate(password)
        except WeakPasswordError as error:
            violations["password"] = error.message
            rules["password"] = error.code
        if violations or address is None:
            self._log_invalid(rules)
            raise InvalidRegistrationError(tuple(violations), tuple(violations.values()))
        return address

    def _log_invalid(self, rules: dict[str, str]) -> None:
        reason = catalog.REASON_INVALID_EMAIL if "email" in rules else catalog.REASON_WEAK_PASSWORD
        attributes = {"rule": rules.get("email") or rules["password"]}
        self._events.log(
            BusinessEvent.denied(
                catalog.REGISTRATION_REJECTED,
                reason,
                resource_type=catalog.RESOURCE_ACCOUNT,
                attributes=attributes,
            )
        )

    def _reject(self, reason: str, address: EmailAddress) -> None:
        self._events.log(
            BusinessEvent.denied(
                catalog.REGISTRATION_REJECTED,
                reason,
                resource_type=catalog.RESOURCE_ACCOUNT,
                attributes={"email_hash": self._fingerprinter.fingerprint(address)},
            )
        )

    def _create_account(self, address: EmailAddress, password_hash: str) -> tuple[User, str]:
        now = self._clock.now()
        user = User.register(address, password_hash, now)
        token = self._tokens.generate()
        with self._unit_of_work() as work:
            work.users.add(user)
            work.tokens.add(VerificationToken.issue(user.id, self._tokens.digest(token), now))
            work.commit()
        return user, token

    def _deliver(self, kind: str, send: Callable[[], None]) -> None:
        try:
            send()
        except MailDeliveryError:
            self._events.log(
                BusinessEvent.error(
                    catalog.EMAIL_DELIVERY_FAILED,
                    catalog.REASON_MAIL_DELIVERY_FAILED,
                    resource_type=catalog.RESOURCE_VERIFICATION,
                    attributes={"kind": kind},
                )
            )
