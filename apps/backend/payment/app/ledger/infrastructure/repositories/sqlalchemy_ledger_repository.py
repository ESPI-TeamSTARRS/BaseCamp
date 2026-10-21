from sqlalchemy.orm import Session

from app.ledger.domain.entities.ledger_transaction import LedgerTransaction
from app.ledger.domain.interfaces.ledger_repository import LedgerRepository
from app.ledger.infrastructure.models.ledger_entry_model import LedgerEntryModel


class SqlAlchemyLedgerRepository(LedgerRepository):
    """Écrit dans la session de l'appelant : le grand livre partage la transaction de l'état."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, transaction: LedgerTransaction) -> None:
        self._session.add_all(
            LedgerEntryModel(
                id=entry.id,
                transaction_id=entry.transaction_id,
                intent_id=entry.intent_id,
                account=entry.account.value,
                direction=entry.direction.value,
                amount=entry.amount.cents,
                created_at=entry.created_at,
            )
            for entry in transaction.entries
        )
        self._session.flush()
