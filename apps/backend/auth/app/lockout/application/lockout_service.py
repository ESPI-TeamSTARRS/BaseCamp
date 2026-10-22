from collections.abc import Iterable
from datetime import datetime

from app.core.events.business_event import BusinessEvent
from app.core.events.business_event_logger import BusinessEventLogger
from app.lockout.application import lockout_events as catalog
from app.lockout.application.unit_of_work_factory import UnitOfWorkFactory
from app.lockout.domain.entities.lock_status import LockStatus
from app.lockout.domain.entities.lockout_policies import LockoutPolicies
from app.lockout.domain.entities.lockout_policy import LockoutPolicy
from app.lockout.domain.entities.lockout_scope import lockout_scope
from app.lockout.domain.entities.lockout_subject import LockoutSubject
from app.lockout.domain.entities.truncated_address import truncate_address
from app.lockout.domain.enums.subject_type import SubjectType


class LockoutService:
    """Verrouillage, independant de l'etape qui l'appelle, avec une politique par etape.

    Une etape (`step` : mot de passe, visage, ...) interroge `check` avant de verifier, signale
    l'echec par `record_failure` ou le succes par `record_success`. Chaque (etape, type de sujet) a
    son compteur et sa regle (`LockoutPolicies`) : un visage refuse ne compte jamais comme un mot de
    passe faux. Le sujet est un compte ou une adresse source (`SubjectType`). L'etat est en base : il
    survit a un redemarrage et se partage entre instances. Le service ne connait ni l'email ni le mot
    de passe, seulement une empreinte opaque (`subject`).
    """

    def __init__(
        self,
        unit_of_work: UnitOfWorkFactory,
        policy: LockoutPolicy | LockoutPolicies,
        events: BusinessEventLogger,
    ) -> None:
        self._unit_of_work = unit_of_work
        self._policies = (
            policy if isinstance(policy, LockoutPolicies) else LockoutPolicies(default=policy)
        )
        self._events = events

    def check(
        self,
        step: str,
        subject: str,
        now: datetime,
        subject_type: SubjectType = SubjectType.ACCOUNT,
    ) -> LockStatus:
        with self._unit_of_work() as work:
            state = work.lockouts.find(lockout_scope(step, subject_type), subject)
        if state is None or not state.locked(now):
            return LockStatus.free()
        return LockStatus(locked=True, retry_after_seconds=state.retry_after_seconds(now))

    def record_failure(
        self,
        step: str,
        subject: str,
        now: datetime,
        subject_type: SubjectType = SubjectType.ACCOUNT,
        client_ip: str | None = None,
    ) -> LockStatus:
        policy = self._policies.for_step(step, subject_type)
        scope = lockout_scope(step, subject_type)
        with self._unit_of_work() as work:
            before = work.lockouts.lock_for_update(scope, subject, now)
            after = before.after_failure(now, policy)
            work.lockouts.save(after)
            work.lockouts.purge_idle_before(now - self._policies.max_memory)
            work.commit()
        just_locked = after.locked(now) and not before.locked(now)
        if just_locked:
            self._events.log(
                BusinessEvent.denied(
                    catalog.LOCKOUT_TRIGGERED,
                    catalog.REASON_TOO_MANY_FAILURES,
                    resource_type=catalog.RESOURCE_SUBJECT,
                    client_ip=truncate_address(client_ip),
                    attributes={
                        "step": step,
                        "subject_type": subject_type.value,
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

    def record_success(
        self, step: str, subject: str, subject_type: SubjectType = SubjectType.ACCOUNT
    ) -> None:
        """Un succes remet le compteur a zero (et l'echelle des recidives)."""
        self.clear([LockoutSubject(step, subject, subject_type)])

    def clear(self, subjects: Iterable[LockoutSubject]) -> None:
        """Remet a zero plusieurs compteurs en une transaction (connexion reussie de bout en bout)."""
        with self._unit_of_work() as work:
            for target in subjects:
                scope = lockout_scope(target.step, target.subject_type)
                work.lockouts.delete(scope, target.subject)
            work.commit()
