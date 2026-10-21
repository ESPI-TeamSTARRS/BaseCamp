import time

from sqlalchemy import Engine

from app.core.events.business_event_logger import BusinessEventLogger
from app.ledgercheck.application.audit_ledger import AuditLedgerUseCase
from app.ledgercheck.application.check_ledger_consistency import CheckLedgerConsistencyUseCase
from app.ledgercheck.application.ledger_check_services import LedgerCheckServices
from app.ledgercheck.application.read_ledger_discrepancy_count import ReadLedgerDiscrepancyCount
from app.ledgercheck.infrastructure.readers.sqlalchemy_ledger_reader import SqlAlchemyLedgerReader


def build_ledger_check_services(engine: Engine, events: BusinessEventLogger) -> LedgerCheckServices:
    """Assemble le contrôle (qui journalise) et la lecture de la métrique (qui ne journalise pas)."""
    audit = AuditLedgerUseCase(SqlAlchemyLedgerReader(engine))
    return LedgerCheckServices(
        check=CheckLedgerConsistencyUseCase(audit, events, time.perf_counter),
        discrepancy_count=ReadLedgerDiscrepancyCount(audit),
    )
