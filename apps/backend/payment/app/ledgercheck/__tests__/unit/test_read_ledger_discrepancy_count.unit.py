from app.core.__tests__.in_memory_business_event_logger import InMemoryBusinessEventLogger
from app.ledgercheck.__tests__.support import StubLedgerReader, balanced, position
from app.ledgercheck.application import ledger_check_metrics as metrics
from app.ledgercheck.application.audit_ledger import AuditLedgerUseCase
from app.ledgercheck.application.read_ledger_discrepancy_count import ReadLedgerDiscrepancyCount
from app.ledgercheck.domain.entities.ledger_snapshot import LedgerSnapshot


class TestReadLedgerDiscrepancyCount:
    def test_a_healthy_ledger_reads_zero(self) -> None:
        reader = StubLedgerReader(LedgerSnapshot((position(),), (balanced(),)))

        assert ReadLedgerDiscrepancyCount(AuditLedgerUseCase(reader))() == 0

    def test_it_reads_the_current_number_of_discrepancies_on_each_call(self) -> None:
        reader = StubLedgerReader(LedgerSnapshot((position(balance=1), position(balance=2)), ()))
        read = ReadLedgerDiscrepancyCount(AuditLedgerUseCase(reader))

        assert (read(), read()) == (2, 2)
        assert reader.reads == 2

    def test_the_metric_name_is_published_in_one_place(self) -> None:
        assert metrics.LEDGER_DISCREPANCIES == "payment_ledger_discrepancies"

    def test_reading_the_metric_emits_no_business_event(self) -> None:
        # Le lecteur ne reçoit aucun journal : un scrape fréquent ne doit jamais inonder les logs.
        events = InMemoryBusinessEventLogger()
        reader = StubLedgerReader(LedgerSnapshot((position(balance=1),), ()))

        ReadLedgerDiscrepancyCount(AuditLedgerUseCase(reader))()

        assert events.events == []
