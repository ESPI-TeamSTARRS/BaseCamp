from dataclasses import replace
from uuid import UUID

from app.admin.application import admin_events as catalog
from app.admin.application.account_summary import AccountSummary
from app.admin.application.unit_of_work_factory import UnitOfWorkFactory
from app.admin.domain.exceptions.admin_errors import (
    AccountNotFoundError,
    AdminError,
    CannotDisableLastOperatorError,
    CannotDisableSelfError,
)
from app.core.events.business_event import BusinessEvent
from app.core.events.business_event_logger import BusinessEventLogger
from app.registration.domain.interfaces.clock import Clock


class ChangeAccountStatusUseCase:
    """Desactive ou reactive un compte, au nom d'un operateur.

    Desactiver revoque aussitot tous les jetons de rafraichissement du compte (il ne peut plus se
    connecter ni se rafraichir; son jeton d'acces expire seul, 15 minutes au plus, et `/me` le
    refuse deja). Un operateur ne peut pas se desactiver lui-meme ni desactiver le dernier
    operateur actif. Les deux operations sont idempotentes. Chaque issue est journalisee.
    """

    def __init__(
        self, unit_of_work: UnitOfWorkFactory, clock: Clock, events: BusinessEventLogger
    ) -> None:
        self._unit_of_work = unit_of_work
        self._clock = clock
        self._events = events

    def disable(
        self, operator_id: UUID, target_id: UUID, client_ip: str | None = None
    ) -> AccountSummary:
        now = self._clock.now()
        try:
            with self._unit_of_work() as work:
                operators = work.accounts.lock_operators()
                target = work.accounts.find_for_update(target_id)
                if target is None:
                    raise AccountNotFoundError
                if target.id == operator_id:
                    raise CannotDisableSelfError
                if target.active_operator and len(operators) <= 1:
                    raise CannotDisableLastOperatorError
                revoked = 0
                if not target.disabled:
                    work.accounts.set_disabled(target.id, now)
                    revoked = work.accounts.revoke_sessions(target.id)
                work.commit()
        except AdminError as error:
            self._refuse(operator_id, target_id, error, client_ip)
            raise
        self._events.log(
            BusinessEvent.success(
                catalog.ACCOUNT_DISABLED,
                resource_type=catalog.RESOURCE_ACCOUNT,
                resource_id=str(target_id),
                actor_type=catalog.ACTOR_OPERATOR,
                actor_id=str(operator_id),
                client_ip=client_ip,
                attributes={"sessions_revoked": revoked, "already_disabled": target.disabled},
            )
        )
        return AccountSummary.of(replace(target, disabled=True))

    def enable(
        self, operator_id: UUID, target_id: UUID, client_ip: str | None = None
    ) -> AccountSummary:
        try:
            with self._unit_of_work() as work:
                target = work.accounts.find_for_update(target_id)
                if target is None:
                    raise AccountNotFoundError
                if target.disabled:
                    work.accounts.set_disabled(target.id, None)
                work.commit()
        except AdminError as error:
            self._refuse(operator_id, target_id, error, client_ip)
            raise
        self._events.log(
            BusinessEvent.success(
                catalog.ACCOUNT_ENABLED,
                resource_type=catalog.RESOURCE_ACCOUNT,
                resource_id=str(target_id),
                actor_type=catalog.ACTOR_OPERATOR,
                actor_id=str(operator_id),
                client_ip=client_ip,
                attributes={"already_enabled": not target.disabled},
            )
        )
        return AccountSummary.of(replace(target, disabled=False))

    def _refuse(
        self, operator_id: UUID, target_id: UUID, error: AdminError, client_ip: str | None
    ) -> None:
        self._events.log(
            BusinessEvent.denied(
                catalog.ADMIN_ACTION_REFUSED,
                error.code,
                resource_type=catalog.RESOURCE_ACCOUNT,
                resource_id=str(target_id),
                actor_type=catalog.ACTOR_OPERATOR,
                actor_id=str(operator_id),
                client_ip=client_ip,
            )
        )
