from app.ledgercheck.domain.entities.ledger_check_result import LedgerCheckResult
from app.ledgercheck.domain.interfaces.ledger_reader import LedgerReader
from app.ledgercheck.domain.services.ledger_auditor import LedgerAuditor


class AuditLedgerUseCase:
    """Lit le grand livre et le compare à l'état des paiements. Lecture seule, aucun journal.

    Socle commun de la commande `ledger-check` (qui journalise) et de la métrique (qui ne doit
    jamais inonder les logs à chaque lecture).
    """

    def __init__(self, reader: LedgerReader, auditor: LedgerAuditor | None = None) -> None:
        self._reader = reader
        self._auditor = auditor or LedgerAuditor()

    def execute(self) -> LedgerCheckResult:
        return self._auditor.audit(self._reader.read_snapshot())
