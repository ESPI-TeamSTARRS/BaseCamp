from uuid import UUID

from app.intent.domain.enums.intent_status import IntentStatus
from app.ledgercheck.__tests__.support import balanced, position
from app.ledgercheck.application.dtos.ledger_check_report import LedgerCheckReport
from app.ledgercheck.domain.entities.ledger_snapshot import LedgerSnapshot
from app.ledgercheck.domain.entities.transaction_balance import TransactionBalance
from app.ledgercheck.domain.services.ledger_auditor import LedgerAuditor
from app.ledgercheck.presentation.ledger_check_report_renderer import LedgerCheckReportRenderer


def _render(snapshot: LedgerSnapshot) -> str:
    report = LedgerCheckReport.from_result(LedgerAuditor().audit(snapshot))
    return LedgerCheckReportRenderer().render(report)


class TestLedgerCheckReportRenderer:
    def test_a_healthy_ledger_says_coherent_with_the_totals(self) -> None:
        text = _render(LedgerSnapshot((position(10000, 4000),), (balanced(10000), balanced(4000))))

        assert text.splitlines()[0] == "grand livre cohérent"
        assert "débits : 14000 centimes" in text
        assert "crédits : 14000 centimes" in text
        assert "intentions contrôlées : 1" in text
        assert "transactions : 2" in text
        assert "écarts : 0" in text

    def test_each_discrepancy_names_the_intent_with_expected_and_observed(self) -> None:
        altered = position(10000, balance=9000, intent_id=UUID(int=1))
        orphan = position(status=IntentStatus.EXPIRED, balance=2500, intent_id=UUID(int=2))
        broken = TransactionBalance(UUID(int=3), 1, 5000, 0)

        text = _render(LedgerSnapshot((altered, orphan), (broken,)))

        lines = text.splitlines()
        assert lines[0] == "grand livre INCOHÉRENT"
        assert "écarts : 3" in text
        assert (
            f"intention {UUID(int=1)} : solde marchand attendu 10000, constaté 9000 (écart -1000)"
            in lines
        )
        assert (
            f"intention {UUID(int=2)} : solde marchand attendu 0, constaté 2500 (écart +2500)"
            in lines
        )
        assert f"transaction {UUID(int=3)} : débits 5000, crédits 0 (écart -5000)" in lines

    def test_the_metric_is_printed_for_the_scheduler(self) -> None:
        text = _render(LedgerSnapshot((position(balance=1),), ()))

        assert "métrique payment_ledger_discrepancies 1" in text.splitlines()
