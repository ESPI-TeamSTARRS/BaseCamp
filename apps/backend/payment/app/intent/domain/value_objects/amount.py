from dataclasses import dataclass


@dataclass(frozen=True)
class Amount:
    """Montant en centimes : toujours un entier strictement positif (jamais de flottant)."""

    cents: int

    def __post_init__(self) -> None:
        if type(self.cents) is not int:
            raise TypeError("Le montant doit être un entier de centimes.")
        if self.cents <= 0:
            raise ValueError("Le montant doit être strictement positif.")
