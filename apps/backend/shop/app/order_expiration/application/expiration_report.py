from dataclasses import dataclass


@dataclass(frozen=True)
class ExpirationReport:
    expired_orders: int
    released_units: int
