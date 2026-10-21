from app.account_orders.application import account_order_events as catalog
from app.account_orders.domain.interfaces.account_profile_directory import AccountProfileDirectory
from app.account_orders.domain.interfaces.guest_order_linker import GuestOrderLinker
from app.core.events.business_event import BusinessEvent
from app.core.events.business_event_logger import BusinessEventLogger
from app.customer_identity.domain.entities.customer import Customer
from app.order.domain.interfaces.email_pseudonymizer import EmailPseudonymizer


class LinkGuestOrdersUseCase:
    """Rattache a un compte ses commandes invitees passees avec la meme adresse, si elle est VERIFIEE.

    Le jeton ne porte pas l'adresse (donnee personnelle) : elle vient d'`auth` (`GET /me` avec le
    jeton du client), qui dit aussi si elle est verifiee. Une adresse non verifiee ne rattache rien
    (sinon n'importe qui pourrait s'approprier les commandes d'une adresse qu'il ne possede pas).
    `auth` injoignable : rien n'est rattache cette fois (la tentative suivante reessaiera), sans
    effet sur le reste. Idempotent : seules les commandes encore sans compte sont touchees.
    """

    def __init__(
        self,
        directory: AccountProfileDirectory,
        linker: GuestOrderLinker,
        events: BusinessEventLogger,
        pseudonymizer: EmailPseudonymizer,
    ) -> None:
        self._directory = directory
        self._linker = linker
        self._events = events
        self._pseudonymizer = pseudonymizer

    def execute(self, customer: Customer) -> int:
        if not customer.email_verified:
            return self._skip(customer, catalog.REASON_EMAIL_NOT_VERIFIED)
        profile = self._directory.profile_of(customer.token)
        if profile is None:
            return self._skip(customer, catalog.REASON_PROFILE_UNAVAILABLE)
        if not profile.email_verified:
            return self._skip(customer, catalog.REASON_EMAIL_NOT_VERIFIED)
        linked = self._linker.link(str(customer.id), profile.email)
        if linked:
            self._events.log(
                BusinessEvent.success(
                    catalog.GUEST_ORDERS_LINKED,
                    resource_type=catalog.RESOURCE_ORDER,
                    actor_type=catalog.ACTOR_USER,
                    actor_id=str(customer.id),
                    attributes={
                        "count": linked,
                        "email_hash": self._pseudonymizer.pseudonymize(profile.email),
                    },
                )
            )
        return linked

    def execute_best_effort(self, customer: Customer) -> int:
        """Comme `execute`, mais ne leve jamais : un echec ne doit pas faire echouer l'appelant
        (un achat deja valide, une liste a servir)."""
        try:
            return self.execute(customer)
        except Exception:
            return self._skip(customer, catalog.REASON_LINK_FAILED)

    def _skip(self, customer: Customer, reason: str) -> int:
        self._events.log(
            BusinessEvent.denied(
                catalog.LINK_SKIPPED,
                reason,
                resource_type=catalog.RESOURCE_ORDER,
                actor_type=catalog.ACTOR_USER,
                actor_id=str(customer.id),
            )
        )
        return 0
