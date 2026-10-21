from dataclasses import dataclass
from datetime import timedelta


@dataclass(frozen=True)
class RetryPolicy:
    """Relances d'une livraison : attente exponentielle bornée, nombre de tentatives borné."""

    max_attempts: int = 6
    base_seconds: float = 5.0
    max_delay_seconds: float = 300.0

    def __post_init__(self) -> None:
        if self.max_attempts < 1:
            raise ValueError("retry policy: max_attempts must be at least 1")
        if self.base_seconds <= 0 or self.max_delay_seconds <= 0:
            raise ValueError("retry policy: delays must be positive")
        if self.base_seconds > self.max_delay_seconds:
            raise ValueError("retry policy: base delay cannot exceed the maximum delay")

    def delay_after(self, attempts: int) -> timedelta:
        """Attente avant la tentative suivante, `attempts` tentatives ayant déjà échoué."""
        exponent = min(max(attempts - 1, 0), 32)
        return timedelta(seconds=min(self.base_seconds * 2**exponent, self.max_delay_seconds))

    def is_exhausted(self, attempts: int) -> bool:
        return attempts >= self.max_attempts
