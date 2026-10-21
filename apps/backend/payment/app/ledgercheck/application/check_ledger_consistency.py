from collections.abc import Callable

from app.core.events.business_event import BusinessEvent
from app.core.events.business_event_logger import BusinessEventLogger
from app.ledgercheck.application import ledger_check_event_names as names
from app.ledgercheck.application.audit_ledger import AuditLedgerUseCase
from app.ledgercheck.application.dtos.ledger_check_report import LedgerCheckReport
from app.ledgercheck.application.exceptions.ledger_check_unavailable_error import (
    LedgerCheckUnavailableError,
)
from app.ledgercheck.domain.entities.ledger_discrepancy import LedgerDiscrepancy
from app.ledgercheck.domain.enums.discrepancy_kind import DiscrepancyKind
from app.ledgercheck.domain.exceptions.ledger_read_error import LedgerReadError

DEFAULT_MAX_LOGGED = 100

# genre d'écart -> (motif de l'événement, type de la ressource concernée)
_LOGGED_AS = {
    DiscrepancyKind.INTENT_BALANCE: ("intent_balance_mismatch", "payment_intent"),
    DiscrepancyKind.TRANSACTION_UNBALANCED: ("transaction_unbalanced", "ledger_transaction"),
}


class CheckLedgerConsistencyUseCase:
    """Contrôle la cohérence du grand livre et journalise le résultat.

    Un événement d'erreur par écart (au plus `max_logged`, pour ne pas inonder le journal si tout
    est corrompu), puis un événement de synthèse qui porte toujours le total. Aucune correction :
    le contrôle ne fait que lire et rapporter. Les événements ne portent que des identifiants et
    des montants en centimes.
    """

    def __init__(
        self,
        audit: AuditLedgerUseCase,
        events: BusinessEventLogger,
        timer: Callable[[], float],
        max_logged: int = DEFAULT_MAX_LOGGED,
    ) -> None:
        self._audit = audit
        self._events = events
        self._timer = timer
        self._max_logged = max_logged

    def execute(self) -> LedgerCheckReport:
        started = self._timer()
        try:
            result = self._audit.execute()
        except LedgerReadError:
            self._events.log(BusinessEvent.error(names.LEDGER_CHECK_FAILED, "database_error"))
            raise LedgerCheckUnavailableError from None
        report = LedgerCheckReport.from_result(result)
        for gap in result.discrepancies[: self._max_logged]:
            self._log_gap(gap)
        self._log_summary(report, round((self._timer() - started) * 1000))
        return report

    def _log_gap(self, gap: LedgerDiscrepancy) -> None:
        reason, resource_type = _LOGGED_AS[gap.kind]
        self._events.log(
            BusinessEvent.error(
                names.LEDGER_INCONSISTENCY_DETECTED,
                reason,
                resource_type=resource_type,
                resource_id=str(gap.resource_id),
                attributes={
                    "expected_cents": gap.expected_cents,
                    "observed_cents": gap.observed_cents,
                },
            )
        )

    def _log_summary(self, report: LedgerCheckReport, duration_ms: int) -> None:
        attributes = {
            "intents_checked": report.intents_checked,
            "transactions_checked": report.transactions_checked,
            "entry_count": report.entry_count,
            "debit_cents": report.debit_cents,
            "credit_cents": report.credit_cents,
        }
        if report.is_consistent:
            self._events.log(
                BusinessEvent.success(
                    names.LEDGER_CHECK_COMPLETED, duration_ms=duration_ms, attributes=attributes
                )
            )
            return
        self._events.log(
            BusinessEvent.error(
                names.LEDGER_CHECK_COMPLETED,
                "ledger_inconsistent",
                duration_ms=duration_ms,
                attributes={**attributes, "discrepancy_count": report.discrepancy_count},
            )
        )
