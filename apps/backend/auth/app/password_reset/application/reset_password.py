from app.core.events.business_event import BusinessEvent
from app.core.events.business_event_logger import BusinessEventLogger
from app.password_reset.application import password_reset_events as catalog
from app.password_reset.application.invalid_new_password_error import InvalidNewPasswordError
from app.password_reset.application.invalid_reset_token_error import InvalidResetTokenError
from app.password_reset.application.unit_of_work_factory import UnitOfWorkFactory
from app.password_reset.domain.interfaces.password_reset_mailer import PasswordResetMailer
from app.registration.domain.exceptions.mail_delivery_error import MailDeliveryError
from app.registration.domain.exceptions.weak_password_error import WeakPasswordError
from app.registration.domain.interfaces.clock import Clock
from app.registration.domain.interfaces.password_hasher import PasswordHasher
from app.registration.domain.interfaces.token_generator import TokenGenerator
from app.registration.domain.services.password_policy import PasswordPolicy
from app.registration.domain.value_objects.email_address import EmailAddress


class ResetPasswordUseCase:
    """Remplace le mot de passe : jeton consomme, hachage, sessions revoquees, en une transaction.

    La politique de mot de passe est celle de l'inscription (`PasswordPolicy`). Un mot de passe
    refuse ne consomme pas le jeton. L'email de notification part apres la validation.
    """

    def __init__(
        self,
        unit_of_work: UnitOfWorkFactory,
        password_policy: PasswordPolicy,
        hasher: PasswordHasher,
        tokens: TokenGenerator,
        mailer: PasswordResetMailer,
        clock: Clock,
        events: BusinessEventLogger,
    ) -> None:
        self._unit_of_work = unit_of_work
        self._password_policy = password_policy
        self._hasher = hasher
        self._tokens = tokens
        self._mailer = mailer
        self._clock = clock
        self._events = events

    def execute(self, token: str, new_password: str) -> None:
        self._check_policy(new_password)
        password_hash = self._hasher.hash(new_password)
        now = self._clock.now()
        with self._unit_of_work() as work:
            user_id = work.tokens.consume(self._tokens.digest(token), now)
            if user_id is None:
                self._events.log(
                    BusinessEvent.denied(
                        catalog.RESET_REJECTED,
                        catalog.REASON_INVALID_TOKEN,
                        resource_type=catalog.RESOURCE_PASSWORD_RESET,
                    )
                )
                raise InvalidResetTokenError
            work.accounts.change_password(user_id, password_hash)
            work.sessions.revoke_all(user_id, now)
            account = work.accounts.find_by_id(user_id)
            work.commit()
        self._events.log(
            BusinessEvent.success(
                catalog.RESET_COMPLETED,
                resource_type=catalog.RESOURCE_ACCOUNT,
                resource_id=str(user_id),
            )
        )
        if account is not None:
            self._notify(account.email)

    def _check_policy(self, password: str) -> None:
        try:
            self._password_policy.validate(password)
        except WeakPasswordError as error:
            self._events.log(
                BusinessEvent.denied(
                    catalog.RESET_REJECTED,
                    catalog.REASON_WEAK_PASSWORD,
                    resource_type=catalog.RESOURCE_ACCOUNT,
                    attributes={"rule": error.code},
                )
            )
            raise InvalidNewPasswordError(error.message) from None

    def _notify(self, email: EmailAddress) -> None:
        try:
            self._mailer.send_password_changed(email)
        except MailDeliveryError:
            self._events.log(
                BusinessEvent.error(
                    catalog.EMAIL_DELIVERY_FAILED,
                    catalog.REASON_MAIL_DELIVERY_FAILED,
                    resource_type=catalog.RESOURCE_ACCOUNT,
                    attributes={"kind": catalog.KIND_PASSWORD_CHANGED},
                )
            )
