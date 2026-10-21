from app.ledgercheck.application.dtos.discrepancy_view import DiscrepancyView
from app.ledgercheck.application.dtos.ledger_check_report import LedgerCheckReport
from app.ledgercheck.application.ledger_check_metrics import LEDGER_DISCREPANCIES

_INTENT_KIND = "intent_balance"


class LedgerCheckReportRenderer:
    """Texte de la commande : totaux, puis un écart par ligne. Identifiants et montants seulement."""

    def render(self, report: LedgerCheckReport) -> str:
        lines = [
            "grand livre cohérent" if report.is_consistent else "grand livre INCOHÉRENT",
            f"intentions contrôlées : {report.intents_checked}",
            f"transactions : {report.transactions_checked}",
            f"lignes : {report.entry_count}",
            f"débits : {report.debit_cents} centimes",
            f"crédits : {report.credit_cents} centimes",
            f"écarts : {report.discrepancy_count}",
            *(self._line(gap) for gap in report.discrepancies),
            f"métrique {LEDGER_DISCREPANCIES} {report.discrepancy_count}",
        ]
        return "\n".join(lines)

    @staticmethod
    def _line(gap: DiscrepancyView) -> str:
        delta = f"{gap.observed_cents - gap.expected_cents:+d}"
        if gap.kind == _INTENT_KIND:
            return (
                f"intention {gap.resource_id} : solde marchand attendu {gap.expected_cents}, "
                f"constaté {gap.observed_cents} (écart {delta})"
            )
        return (
            f"transaction {gap.resource_id} : débits {gap.expected_cents}, "
            f"crédits {gap.observed_cents} (écart {delta})"
        )
