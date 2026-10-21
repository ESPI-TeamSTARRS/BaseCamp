"""Insertion directe de lignes pour les tests de lecture d'état (pas un test)."""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import Engine
from sqlalchemy.orm import Session

from app.intent.infrastructure.models.payment_intent_model import PaymentIntentModel
from app.ledger.infrastructure.models.ledger_entry_model import LedgerEntryModel
from app.webhook.infrastructure.models.outbox_event_model import OutboxEventModel


def add_intent(
    engine: Engine,
    created_at: datetime,
    status: str = "requires_confirmation",
    amount: int = 5000,
    refunded: int = 0,
) -> UUID:
    intent_id = uuid4()
    with Session(engine) as session, session.begin():
        session.add(
            PaymentIntentModel(
                id=intent_id,
                order_reference=f"CMD-{intent_id}",
                amount=amount,
                currency="EUR",
                status=status,
                refunded_amount=refunded,
                expires_at=created_at,
                created_at=created_at,
            )
        )
    return intent_id


def add_entries(
    engine: Engine,
    intent_id: UUID,
    created_at: datetime,
    debit: int,
    credit: int,
    transaction_id: UUID | None = None,
) -> UUID:
    transaction = transaction_id or uuid4()
    with Session(engine) as session, session.begin():
        for direction, account, amount in (
            ("debit", "client_attente", debit),
            ("credit", "marchand", credit),
        ):
            session.add(
                LedgerEntryModel(
                    id=uuid4(),
                    transaction_id=transaction,
                    intent_id=intent_id,
                    account=account,
                    direction=direction,
                    amount=amount,
                    created_at=created_at,
                )
            )
    return transaction


def add_outbox(
    engine: Engine,
    intent_id: UUID,
    status: str,
    created_at: datetime,
    event_type: str = "payment.succeeded",
) -> None:
    with Session(engine) as session, session.begin():
        session.add(
            OutboxEventModel(
                id=uuid4(),
                event_type=event_type,
                intent_id=intent_id,
                body="{}",
                status=status,
                attempts=0,
                next_attempt_at=created_at,
                created_at=created_at,
            )
        )
