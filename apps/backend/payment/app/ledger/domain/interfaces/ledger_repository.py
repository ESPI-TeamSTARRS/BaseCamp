from abc import ABC, abstractmethod

from app.ledger.domain.entities.ledger_transaction import LedgerTransaction


class LedgerRepository(ABC):
    @abstractmethod
    def add(self, transaction: LedgerTransaction) -> None:
        """Ajoute les lignes d'une transaction. Le grand livre est en ajout seul : rien d'autre."""
