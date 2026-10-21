from dataclasses import dataclass


@dataclass(frozen=True)
class ExpirationResult:
    expired_count: int
