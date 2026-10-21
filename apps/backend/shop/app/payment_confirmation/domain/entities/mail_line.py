from dataclasses import dataclass


@dataclass(frozen=True)
class MailLine:
    name: str
    quantity: int
    line_total_cents: int
