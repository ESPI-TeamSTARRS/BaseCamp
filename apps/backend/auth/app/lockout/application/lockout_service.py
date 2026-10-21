from datetime import datetime

from app.core.events.business_event import BusinessEvent
from app.core.events.business_event_logger import BusinessEventLogger
from app.lockout.application import lockout_events as catalog
from app.lockout.application.unit_of_work_factory import UnitOfWorkFactory
from app.lockout.domain.entities.lock_status import LockStatus
from app.lockout.domain.entities.lockout_policy import LockoutPolicy


class LockoutService:
    """Verrouillage progressif, independant de l'etape qui l'appelle.

    Une etape (`scope` : mot de passe, identifiant, visage, ...) interroge `check` avant de
    verifier, signale l'echec par `record_failure` ou le succes par `record_success`. L'etat est en
    base : il survit a un redemarrage et se partage entre instances. Le service ne connait ni
    l'email ni le mot de passe, seulement une empreinte opaque (`subject`).
    """

    def __init__(
        self,
        unit_of_work: UnitOfWorkFactory,
        policy: LockoutPolicy,
        events: BusinessEventLogger,
    ) -> None:
        self._unit_of_work = unit_of_work
        self._policy = policy
        self._events = events

    def check(self, scope: str, subject: str, now: datetime) -> LockStatus:
        with self._unit_of_work() as work:
            state = work.lockouts.find(scope, subject)
        if state is None or not state.locked(now):
            return LockStatus.free()
        return LockStatus(locked=True, retry_after_seconds=state.retry_after_seconds(now))

    def record_failure(self, scope: str, subject: str, now: datetime) -> LockStatus:
        with self._unit_of_work() as work:
            before = work.lockouts.lock_for_update(scope, subject, now)
            after = before.after_failure(now, self._policy)
            work.lockouts.save(after)
            work.lockouts.purge_idle_before(now - self._policy.memory)
            work.commit()
        just_locked = after.locked(now) and not before.locked(now)
        if just_locked:
            self._events.log(
                BusinessEvent.denied(
                    catalog.LOCKOUT_TRIGGERED,
                    catalog.REASON_TOO_MANY_FAILURES,
                    resource_type=catalog.RESOURCE_SUBJECT,
                    attributes={
                        "step": scope,
                        "subject_hash": subject,
                        "level": after.level,
                        "locked_seconds": after.retry_after_seconds(now),
                    },
                )
            )
        if not after.locked(now):
            return LockStatus.free()
        return LockStatus(
            locked=True,
            retry_after_seconds=after.retry_after_seconds(now),
            just_locked=just_locked,
        )

    def record_success(self, scope: str, subject: str) -> None:
        """Un succes remet le compteur a zero (et l'echelle des recidives)."""
        with self._unit_of_work() as work:
            work.lockouts.delete(scope, subject)
            work.commit()
