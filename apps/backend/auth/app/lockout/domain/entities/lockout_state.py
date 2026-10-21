import math
from dataclasses import dataclass, replace
from datetime import datetime

from app.lockout.domain.entities.lockout_policy import LockoutPolicy


@dataclass(frozen=True)
class LockoutState:
    """Etat de verrouillage d'un sujet (`subject`) pour une etape (`scope`).

    `subject` est une empreinte opaque (jamais une adresse) : un email inconnu est verrouille
    comme un email connu, donc le verrou ne revele rien sur l'existence d'un compte.
    """

    scope: str
    subject: str
    failures: int = 0
    window_started_at: datetime | None = None
    level: int = 0
    locked_until: datetime | None = None
    updated_at: datetime | None = None

    def locked(self, now: datetime) -> bool:
        return self.locked_until is not None and self.locked_until > now

    def retry_after_seconds(self, now: datetime) -> int:
        """Secondes restantes de verrou, arrondies au-dessus; 0 si le sujet n'est pas verrouille."""
        if self.locked_until is None or not self.locked(now):
            return 0
        return math.ceil((self.locked_until - now).total_seconds())

    def after_failure(self, now: datetime, policy: LockoutPolicy) -> "LockoutState":
        """Etat apres un echec. Un echec pendant un verrou ne compte pas et ne le prolonge pas."""
        if self.locked(now):
            return self
        level = self.level
        if self.locked_until is not None and now - self.locked_until > policy.memory:
            level = 0
        fresh_window = (
            self.window_started_at is None or now - self.window_started_at > policy.window
        )
        failures = 1 if fresh_window else self.failures + 1
        started = now if fresh_window else self.window_started_at
        if failures >= policy.max_failures:
            level += 1
            return replace(
                self,
                failures=0,
                window_started_at=None,
                level=level,
                locked_until=now + policy.duration_for(level),
                updated_at=now,
            )
        return replace(
            self,
            failures=failures,
            window_started_at=started,
            level=level,
            updated_at=now,
        )
