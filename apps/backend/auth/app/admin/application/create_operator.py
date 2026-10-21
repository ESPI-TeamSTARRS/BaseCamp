from uuid import uuid4

from app.admin.application import admin_events as catalog
from app.admin.application.unit_of_work_factory import UnitOfWorkFactory
from app.admin.domain.exceptions.admin_errors import OperatorAlreadyExistsError
from app.core.events.business_event import BusinessEvent
from app.core.events.business_event_logger import BusinessEventLogger
from app.registration.domain.exceptions.weak_password_error import WeakPasswordError
from app.registration.domain.interfaces.clock import Clock
from app.registration.domain.interfaces.password_hasher import PasswordHasher
from app.registration.domain.services.password_policy import PasswordPolicy
from app.registration.domain.value_objects.email_address import EmailAddress


class CreateOperatorUseCase:
    """Cree un compte `operator` : seule voie de creation du role (commande d'exploitation).

    Le mot de passe suit la politique de l'inscription et est hache en argon2id; il n'est ni
    journalise ni renvoye. L'inscription publique ne produit jamais que le role `customer`.
    """

    def __init__(
        self,
        unit_of_work: UnitOfWorkFactory,
        password_policy: PasswordPolicy,
        hasher: PasswordHasher,
        clock: Clock,
        events: BusinessEventLogger,
    ) -> None:
        self._unit_of_work = unit_of_work
        self._password_policy = password_policy
        self._hasher = hasher
        self._clock = clock
        self._events = events

    def execute(self, email: str, password: str) -> str:
        """Renvoie l'identifiant du compte cree. Leve `InvalidEmailError`, `WeakPasswordError`
        ou `OperatorAlreadyExistsError`."""
        address = EmailAddress.of(email)
        try:
            self._password_policy.validate(password)
        except WeakPasswordError as error:
            self._refuse(catalog.REASON_WEAK_PASSWORD, error.code)
            raise
        account_id = uuid4()
        password_hash = self._hasher.hash(password)
        try:
            with self._unit_of_work() as work:
                work.accounts.add_operator(
                    account_id, address.value, password_hash, self._clock.now()
                )
                work.commit()
        except OperatorAlreadyExistsError:
            self._refuse(catalog.REASON_ALREADY_EXISTS, None)
            raise
        self._events.log(
            BusinessEvent.success(
                catalog.OPERATOR_CREATED,
                resource_type=catalog.RESOURCE_ACCOUNT,
                resource_id=str(account_id),
                actor_type=catalog.ACTOR_CLI,
            )
        )
        return str(account_id)

    def _refuse(self, reason: str, rule: str | None) -> None:
        self._events.log(
            BusinessEvent.denied(
                catalog.OPERATOR_CREATED,
                reason,
                resource_type=catalog.RESOURCE_ACCOUNT,
                actor_type=catalog.ACTOR_CLI,
                attributes={"rule": rule} if rule else {},
            )
        )
