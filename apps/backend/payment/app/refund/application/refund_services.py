from dataclasses import dataclass

from app.refund.application.record_rejected_refund import RecordRejectedRefundUseCase
from app.refund.application.refund_payment import RefundPaymentUseCase


@dataclass(frozen=True)
class RefundServices:
    """Cas d'usage de la tranche, câblés dans wiring.py et lus par la présentation."""

    refund: RefundPaymentUseCase
    record_rejection: RecordRejectedRefundUseCase
