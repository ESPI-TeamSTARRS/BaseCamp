from app.ledgercheck.application.audit_ledger import AuditLedgerUseCase


class ReadLedgerDiscrepancyCount:
    """Valeur courante de la jauge `payment_ledger_discrepancies` (voir ledger_check_metrics).

    Appelable sans argument : le point d'accès `/metrics` l'enregistre comme rappel de la jauge, à
    chaque lecture. Relit le grand livre (lecture seule, moins de 2 s pour 10 000 intentions), ne
    garde rien en mémoire et n'émet aucun événement métier.
    """

    def __init__(self, audit: AuditLedgerUseCase) -> None:
        self._audit = audit

    def __call__(self) -> int:
        return self._audit.execute().discrepancy_count
