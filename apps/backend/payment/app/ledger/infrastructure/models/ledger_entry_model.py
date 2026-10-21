from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    DDL,
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    String,
    Uuid,
    event,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.intent.infrastructure.models.base import Base


class LedgerEntryModel(Base):
    """Ligne du grand livre. Ajout seul : les déclencheurs refusent UPDATE et DELETE.

    Sur Postgres les déclencheurs (et l'équilibre débits = crédits par transaction) sont posés par
    la migration 0004. Pour SQLite (tests), ils sont posés à la création de la table ci-dessous.
    """

    __tablename__ = "ledger_entries"
    __table_args__ = (
        CheckConstraint("amount > 0", name="ck_ledger_entries_amount_positive"),
        CheckConstraint("direction IN ('debit', 'credit')", name="ck_ledger_entries_direction"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    transaction_id: Mapped[UUID] = mapped_column(Uuid, index=True)
    intent_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("payment_intents.id"), index=True)
    account: Mapped[str] = mapped_column(String(32))
    direction: Mapped[str] = mapped_column(String(6))
    amount: Mapped[int] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


for _operation in ("UPDATE", "DELETE"):
    event.listen(
        LedgerEntryModel.__table__,
        "after_create",
        DDL(  # type: ignore[no-untyped-call]
            f"CREATE TRIGGER ledger_entries_no_{_operation.lower()} "
            f"BEFORE {_operation} ON ledger_entries "
            "BEGIN SELECT RAISE(ABORT, 'ledger_entries est en ajout seul'); END"
        ).execute_if(dialect="sqlite"),
    )
