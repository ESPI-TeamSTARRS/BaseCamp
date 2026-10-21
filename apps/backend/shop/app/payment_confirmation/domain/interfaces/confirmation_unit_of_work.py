from abc import ABC, abstractmethod
from types import TracebackType
from typing import Self

from app.payment_confirmation.domain.interfaces.settlement_targets import SettlementTargets
from app.payment_confirmation.domain.interfaces.webhook_events import WebhookEvents


class ConfirmationUnitOfWork(ABC):
    """Une transaction : état de la commande, stock et mémoire de l'événement, tout ou rien."""

    events: WebhookEvents
    targets: SettlementTargets

    @abstractmethod
    def __enter__(self) -> Self: ...

    @abstractmethod
    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None: ...

    @abstractmethod
    def commit(self) -> None:
        """Valide; lève DuplicateWebhookEventError si l'événement vient d'être enregistré ailleurs."""
