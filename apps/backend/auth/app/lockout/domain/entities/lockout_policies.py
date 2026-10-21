from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import timedelta

from app.lockout.domain.entities.lockout_policy import LockoutPolicy
from app.lockout.domain.enums.subject_type import SubjectType


@dataclass(frozen=True)
class LockoutPolicies:
    """Politique de verrouillage par etape et par type de sujet.

    Ordre de choix : une regle propre a (etape, type de sujet); sinon, pour une adresse source, la
    regle `address`; sinon la regle `default`. Une etape non configuree garde donc le comportement
    d'avant (aucune regression du login client).
    """

    default: LockoutPolicy
    address: LockoutPolicy | None = None
    steps: Mapping[tuple[str, SubjectType], LockoutPolicy] = field(default_factory=dict)

    def for_step(self, step: str, subject_type: SubjectType = SubjectType.ACCOUNT) -> LockoutPolicy:
        own = self.steps.get((step, subject_type))
        if own is not None:
            return own
        if subject_type is SubjectType.SOURCE_ADDRESS and self.address is not None:
            return self.address
        return self.default

    @property
    def max_memory(self) -> timedelta:
        """Plus longue memoire des regles : borne de purge des lignes inactives."""
        policies = [self.default, *self.steps.values()]
        if self.address is not None:
            policies.append(self.address)
        return max(policy.memory for policy in policies)
