import re
from collections.abc import Mapping
from dataclasses import dataclass, field

from app.core.events.outcome import Outcome

Scalar = str | int | float | bool | None

_EVENT_NAME = re.compile(r"^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$")
_CODE = re.compile(r"^[a-z][a-z0-9_]*$")


@dataclass(frozen=True)
class BusinessEvent:
    """Evenement metier : nom stable, resultat, motif en code, ressource, valeurs non sensibles."""

    event: str
    outcome: Outcome
    reason: str | None = None
    resource_type: str | None = None
    resource_id: str | None = None
    actor_type: str | None = None
    actor_id: str | None = None
    duration_ms: int | None = None
    client_ip: str | None = None
    attributes: Mapping[str, Scalar] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not _EVENT_NAME.match(self.event):
            raise ValueError("event must look like '<domain>.<action>' in lowercase snake_case")
        if (self.outcome is Outcome.SUCCESS) != (self.reason is None):
            raise ValueError("reason is required unless the outcome is success, and only then")
        if self.reason is not None and not _CODE.match(self.reason):
            raise ValueError("reason must be a snake_case code, not a sentence")
        if self.resource_id is not None and self.resource_type is None:
            raise ValueError("resource_id requires a resource_type")
        if not all(_CODE.match(key) for key in self.attributes):
            raise ValueError("attributes keys must be snake_case")
        if not all(
            isinstance(value, str | int | float | bool | None) for value in self.attributes.values()
        ):
            raise ValueError("attributes values must be scalars")

    @classmethod
    def success(cls, event: str, **fields: object) -> "BusinessEvent":
        return cls(event=event, outcome=Outcome.SUCCESS, **fields)  # type: ignore[arg-type]

    @classmethod
    def denied(cls, event: str, reason: str, **fields: object) -> "BusinessEvent":
        return cls(event=event, outcome=Outcome.DENIED, reason=reason, **fields)  # type: ignore[arg-type]

    @classmethod
    def error(cls, event: str, reason: str, **fields: object) -> "BusinessEvent":
        return cls(event=event, outcome=Outcome.ERROR, reason=reason, **fields)  # type: ignore[arg-type]
