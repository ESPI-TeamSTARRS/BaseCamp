from dataclasses import dataclass


@dataclass(frozen=True)
class DeliveryResult:
    """Issue d'une tentative d'envoi : livré, ou échec décrit par un code (jamais un message)."""

    delivered: bool
    reason: str | None = None
    status_code: int | None = None
    rejected: bool = (
        False  # refus définitif de la boutique (409 « commande expirée »), pas une panne
    )

    @classmethod
    def ok(cls, status_code: int) -> "DeliveryResult":
        return cls(delivered=True, status_code=status_code)

    @classmethod
    def rejection(cls, reason: str, status_code: int) -> "DeliveryResult":
        return cls(delivered=False, reason=reason, status_code=status_code, rejected=True)

    @classmethod
    def failed(cls, reason: str, status_code: int | None = None) -> "DeliveryResult":
        return cls(delivered=False, reason=reason, status_code=status_code)
