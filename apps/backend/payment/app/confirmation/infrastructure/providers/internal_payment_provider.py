from collections.abc import Callable

from app.confirmation.domain.enums.payment_method import PaymentMethod
from app.confirmation.domain.enums.provider_outcome import ProviderOutcome
from app.confirmation.domain.interfaces.payment_provider import PaymentProvider
from app.intent.domain.value_objects.amount import Amount


class InternalPaymentProvider(PaymentProvider):
    """Fournisseur interne simulé : le résultat dépend uniquement de la méthode de test."""

    def __init__(self, wait: Callable[[float], None], timeout_seconds: float) -> None:
        self._wait = wait
        self._timeout_seconds = timeout_seconds

    def authorize(self, method: PaymentMethod, amount: Amount) -> ProviderOutcome:
        if method is PaymentMethod.SUCCESS:
            return ProviderOutcome.APPROVED
        if method is PaymentMethod.DECLINED:
            return ProviderOutcome.DECLINED
        self._wait(self._timeout_seconds)  # délai simulé, toujours borné
        return ProviderOutcome.TIMED_OUT
