from datetime import UTC, datetime, timedelta

from sqlalchemy import Connection, Engine, case, distinct, exists, func, select
from sqlalchemy.exc import SQLAlchemyError

from app.intent.domain.enums.intent_status import IntentStatus
from app.intent.infrastructure.models.payment_intent_model import PaymentIntentModel as Intent
from app.ledger.infrastructure.models.ledger_entry_model import LedgerEntryModel as Entry
from app.observability.domain.entities.service_state import ServiceState
from app.observability.domain.interfaces.service_state_reader import ServiceStateReader
from app.webhook.domain.enums.outbox_status import OutboxStatus
from app.webhook.infrastructure.models.outbox_event_model import OutboxEventModel as Outbox

SUCCEEDED = IntentStatus.SUCCEEDED.value


class SqlAlchemyServiceStateReader(ServiceStateReader):
    """Lit l'état en base, en lecture seule, avec un coût borné.

    Une seule connexion et des agrégats (`GROUP BY`, `COUNT`) : jamais de ligne ramenée en
    mémoire. Les contrôles du grand livre ne portent que sur les intentions créées dans la
    fenêtre `lookback` (une intention ne se règle que dans l'heure suivant sa création), et le
    `statement_timeout` du moteur borne chaque requête. Base indisponible : retourne None.
    """

    def __init__(self, engine: Engine, lookback: timedelta) -> None:
        self._engine = engine
        self._lookback = lookback

    def read(self, now: datetime) -> ServiceState | None:
        try:
            with self._engine.connect() as connection:
                return self._read(connection, now)
        except SQLAlchemyError:
            return None

    def _read(self, connection: Connection, now: datetime) -> ServiceState:
        since = now - self._lookback
        captured, refunded, refunded_intents = self._payments(connection)
        return ServiceState(
            intents_by_status=self._counts(
                connection, Intent.status, [status.value for status in IntentStatus]
            ),
            webhook_events_by_status=self._counts(
                connection, Outbox.status, [status.value for status in OutboxStatus]
            ),
            webhook_oldest_pending_age_seconds=self._oldest_pending_age(connection, now),
            captured_amount_cents=captured,
            refunded_amount_cents=refunded,
            refunded_intents=refunded_intents,
            ledger_discrepancies=self._ledger_discrepancies(connection, since),
        )

    @staticmethod
    def _counts(connection: Connection, column: object, known: list[str]) -> dict[str, int]:
        rows = connection.execute(select(column, func.count()).group_by(column))  # type: ignore[call-overload]
        counts = dict.fromkeys(known, 0)
        counts.update({str(value): int(count) for value, count in rows})
        return counts

    @staticmethod
    def _payments(connection: Connection) -> tuple[int, int, int]:
        succeeded = Intent.status == SUCCEEDED
        row = connection.execute(
            select(
                func.coalesce(func.sum(case((succeeded, Intent.amount), else_=0)), 0),
                func.coalesce(func.sum(case((succeeded, Intent.refunded_amount), else_=0)), 0),
                func.count(case(((succeeded) & (Intent.refunded_amount > 0), 1))),
            )
        ).one()
        return int(row[0]), int(row[1]), int(row[2])

    @staticmethod
    def _oldest_pending_age(connection: Connection, now: datetime) -> float:
        oldest: datetime | None = connection.execute(
            select(func.min(Outbox.created_at)).where(Outbox.status == OutboxStatus.PENDING.value)
        ).scalar_one()
        if oldest is None:
            return 0.0
        if oldest.tzinfo is None:
            oldest = oldest.replace(tzinfo=UTC)
        return max(0.0, (now - oldest).total_seconds())

    def _ledger_discrepancies(self, connection: Connection, since: datetime) -> dict[str, int]:
        return {
            "unbalanced_transaction": self._unbalanced(connection, since),
            "succeeded_without_entries": self._without_entries(connection, since),
            "amount_mismatch": self._amount_mismatch(connection, since),
            "entries_without_success": self._without_success(connection, since),
        }

    @staticmethod
    def _count(connection: Connection, grouped: object) -> int:
        return int(connection.execute(select(func.count()).select_from(grouped)).scalar_one())  # type: ignore[arg-type]

    def _unbalanced(self, connection: Connection, since: datetime) -> int:
        signed = case((Entry.direction == "debit", Entry.amount), else_=-Entry.amount)
        grouped = (
            select(Entry.transaction_id)
            .join(Intent, Intent.id == Entry.intent_id)
            .where(Intent.created_at >= since)
            .group_by(Entry.transaction_id)
            .having(func.sum(signed) != 0)
            .subquery()
        )
        return self._count(connection, grouped)

    @staticmethod
    def _without_entries(connection: Connection, since: datetime) -> int:
        has_entries = exists().where(Entry.intent_id == Intent.id)
        return int(
            connection.execute(
                select(func.count())
                .select_from(Intent)
                .where(Intent.status == SUCCEEDED, Intent.created_at >= since, ~has_entries)
            ).scalar_one()
        )

    def _amount_mismatch(self, connection: Connection, since: datetime) -> int:
        debits = func.sum(case((Entry.direction == "debit", Entry.amount), else_=0))
        grouped = (
            select(Intent.id)
            .join(Entry, Entry.intent_id == Intent.id)
            .where(Intent.status == SUCCEEDED, Intent.created_at >= since)
            .group_by(Intent.id, Intent.amount)
            .having(debits != Intent.amount)
            .subquery()
        )
        return self._count(connection, grouped)

    @staticmethod
    def _without_success(connection: Connection, since: datetime) -> int:
        return int(
            connection.execute(
                select(func.count(distinct(Entry.transaction_id)))
                .select_from(Entry)
                .join(Intent, Intent.id == Entry.intent_id)
                .where(Intent.status != SUCCEEDED, Intent.created_at >= since)
            ).scalar_one()
        )
