from abc import ABC, abstractmethod

from app.confirmation.domain.enums.payment_method import PaymentMethod
from app.confirmation.domain.enums.provider_outcome import ProviderOutcome
from app.intent.domain.value_objects.amount import Amount


class PaymentProvider(ABC):
    """Fournisseur de paiement : l'adaptateur interne est celui par défaut, un externe reste branchable."""

    @abstractmethod
    def authorize(self, method: PaymentMethod, amount: Amount) -> ProviderOutcome: ...
