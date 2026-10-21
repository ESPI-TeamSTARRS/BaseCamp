from abc import ABC, abstractmethod

from app.ledgercheck.domain.entities.ledger_snapshot import LedgerSnapshot


class LedgerReader(ABC):
    @abstractmethod
    def read_snapshot(self) -> LedgerSnapshot:
        """Lit intentions et transactions du grand livre au même instant, en lecture seule.

        Lève `LedgerReadError` si la base est indisponible.
        """
