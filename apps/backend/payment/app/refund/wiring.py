from datetime import UTC, datetime

from sqlalchemy import Engine

from app.core.events.business_event_logger import BusinessEventLogger
from app.refund.application.record_rejected_refund import RecordRejectedRefundUseCase
from app.refund.application.refund_payment import RefundPaymentUseCase
from app.refund.application.refund_services import RefundServices
from app.refund.infrastructure.repositories.sqlalchemy_refund_unit_of_work import (
    SqlAlchemyRefundUnitOfWork,
)


def build_refund_services(engine: Engine, events: BusinessEventLogger) -> RefundServices:
    """Assemble les cas d'usage du remboursement avec leurs adaptateurs d'infrastructure."""
    return RefundServices(
        refund=RefundPaymentUseCase(
            SqlAlchemyRefundUnitOfWork(engine), lambda: datetime.now(UTC), events
        ),
        record_rejection=RecordRejectedRefundUseCase(events),
    )
