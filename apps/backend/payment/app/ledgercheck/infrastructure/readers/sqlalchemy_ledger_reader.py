from sqlalchemy import Connection, Engine, case, func, select
from sqlalchemy.exc import SQLAlchemyError

from app.intent.domain.enums.intent_status import IntentStatus
from app.intent.infrastructure.models.payment_intent_model import PaymentIntentModel
from app.ledger.domain.enums.entry_direction import EntryDirection
from app.ledger.domain.enums.ledger_account import LedgerAccount
from app.ledger.infrastructure.models.ledger_entry_model import LedgerEntryModel
from app.ledgercheck.domain.entities.intent_ledger_position import IntentLedgerPosition
from app.ledgercheck.domain.entities.ledger_snapshot import LedgerSnapshot
from app.ledgercheck.domain.entities.transaction_balance import TransactionBalance
from app.ledgercheck.domain.exceptions.ledger_read_error import LedgerReadError
from app.ledgercheck.domain.interfaces.ledger_reader import LedgerReader

_DEBIT = EntryDirection.DEBIT.value
_CREDIT = EntryDirection.CREDIT.value


class SqlAlchemyLedgerReader(LedgerReader):
    """Deux agrégations SQL, sans jamais écrire.

    Sur Postgres, la lecture se fait dans une transaction `READ ONLY` en `REPEATABLE READ` : la
    base refuse toute écriture et les deux requêtes voient le même instant, même si des paiements
    sont écrits pendant le contrôle. Aucune ligne n'est verrouillée. Les agrégations parcourent
    les tables une fois (index existants sur `intent_id` et `transaction_id`), sans index ajouté.
    """

    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def read_snapshot(self) -> LedgerSnapshot:
        try:
            with self._engine.connect() as connection:
                if self._engine.dialect.name == "postgresql":
                    connection.execution_options(
                        isolation_level="REPEATABLE READ", postgresql_readonly=True
                    )
                return LedgerSnapshot(self._positions(connection), self._transactions(connection))
        except SQLAlchemyError:
            raise LedgerReadError from None  # le message de la base n'est jamais relayé

    @staticmethod
    def _positions(connection: Connection) -> list[IntentLedgerPosition]:
        """Une position par intention : état annoncé et solde du compte marchand (crédits - débits)."""
        merchant = (
            select(
                LedgerEntryModel.intent_id.label("intent_id"),
                func.sum(
                    case(
                        (LedgerEntryModel.direction == _CREDIT, LedgerEntryModel.amount),
                        else_=-LedgerEntryModel.amount,
                    )
                ).label("balance"),
            )
            .where(LedgerEntryModel.account == LedgerAccount.MARCHAND.value)
            .group_by(LedgerEntryModel.intent_id)
            .subquery()
        )
        rows = connection.execute(
            select(
                PaymentIntentModel.id,
                PaymentIntentModel.status,
                PaymentIntentModel.amount,
                PaymentIntentModel.refunded_amount,
                func.coalesce(merchant.c.balance, 0),
            ).outerjoin(merchant, merchant.c.intent_id == PaymentIntentModel.id)
        )
        return [
            IntentLedgerPosition(
                intent_id=row[0],
                status=IntentStatus(row[1]),
                amount_cents=int(row[2]),
                refunded_cents=int(row[3]),
                merchant_balance_cents=int(row[4]),
            )
            for row in rows
        ]

    @staticmethod
    def _transactions(connection: Connection) -> list[TransactionBalance]:
        rows = connection.execute(
            select(
                LedgerEntryModel.transaction_id,
                func.count(),
                func.coalesce(
                    func.sum(
                        case(
                            (LedgerEntryModel.direction == _DEBIT, LedgerEntryModel.amount), else_=0
                        )
                    ),
                    0,
                ),
                func.coalesce(
                    func.sum(
                        case(
                            (LedgerEntryModel.direction == _CREDIT, LedgerEntryModel.amount),
                            else_=0,
                        )
                    ),
                    0,
                ),
            ).group_by(LedgerEntryModel.transaction_id)
        )
        return [TransactionBalance(row[0], int(row[1]), int(row[2]), int(row[3])) for row in rows]
