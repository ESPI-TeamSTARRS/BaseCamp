"""Contrôle du grand livre sur Postgres : écarts réels, lecture seule et volumétrie (10 000 intentions).

Exécutés si PAYMENT_TEST_DATABASE_URL pointe vers une base Postgres JETABLE (schéma créé par
`alembic upgrade head`, puis supprimé).

Astuce de test, à ne jamais reproduire ailleurs : le grand livre est en ajout seul (déclencheurs
`UPDATE`/`DELETE` refusés) et équilibré (déclencheur de contrainte différé sur `INSERT`). Pour
fabriquer une ligne altérée ou orpheline, les tests désactivent les déclencheurs de CETTE table de
test, dans une transaction qui les réactive avant de valider (`ALTER TABLE ... DISABLE TRIGGER
USER`, transactionnel sous Postgres). La base de production n'est jamais concernée.
"""

import time
from collections.abc import Iterator
from typing import Any
from uuid import UUID

import pytest
from sqlalchemy import Engine, event, text

from app.confirmation.application.commands.confirm_payment_command import ConfirmPaymentCommand
from app.core.__tests__.in_memory_business_event_logger import InMemoryBusinessEventLogger
from app.core.__tests__.postgres_support import add_intent, migrated_engine, requires_postgres
from app.core.config import Settings
from app.confirmation.wiring import build_confirmation_services
from app.intent.domain.entities.payment_intent import PaymentIntent
from app.ledgercheck.application.audit_ledger import AuditLedgerUseCase
from app.ledgercheck.application.check_ledger_consistency import CheckLedgerConsistencyUseCase
from app.ledgercheck.application.dtos.ledger_check_report import LedgerCheckReport
from app.ledgercheck.domain.enums.discrepancy_kind import DiscrepancyKind
from app.ledgercheck.infrastructure.readers.sqlalchemy_ledger_reader import SqlAlchemyLedgerReader
from app.refund.application.commands.refund_payment_command import RefundPaymentCommand
from app.refund.wiring import build_refund_services

pytestmark = requires_postgres

CAPTURED = 2500
VOLUME = 10_000


@pytest.fixture
def engine(monkeypatch: pytest.MonkeyPatch) -> Iterator[Engine]:
    yield from migrated_engine(monkeypatch)


def _paid(engine: Engine, refunded: int = 0) -> PaymentIntent:
    events = InMemoryBusinessEventLogger()
    intent = add_intent(engine)
    build_confirmation_services(engine, Settings(), events).confirm.execute(
        ConfirmPaymentCommand("shop", f"confirm-{intent.id}", str(intent.id), "pm_test_success")
    )
    if refunded:
        build_refund_services(engine, events).refund.execute(
            RefundPaymentCommand("shop", f"refund-{intent.id}", str(intent.id), refunded)
        )
    return intent


def _check(engine: Engine) -> LedgerCheckReport:
    reader = SqlAlchemyLedgerReader(engine)
    use_case = CheckLedgerConsistencyUseCase(
        AuditLedgerUseCase(reader), InMemoryBusinessEventLogger(), time.perf_counter
    )
    return use_case.execute()


def _tamper(engine: Engine, sql: str, **params: Any) -> None:
    """Exécute `sql` avec les déclencheurs de la table désactivés le temps de la transaction."""
    with engine.begin() as connection:
        connection.execute(text("ALTER TABLE ledger_entries DISABLE TRIGGER USER"))
        connection.execute(text(sql), params)
        connection.execute(text("ALTER TABLE ledger_entries ENABLE TRIGGER USER"))


def _insert_line(account: str, direction: str, amount: int) -> str:
    return (
        "INSERT INTO ledger_entries (id, transaction_id, intent_id, account, direction, amount,"
        f" created_at) VALUES (gen_random_uuid(), :tx, :intent, '{account}', '{direction}',"
        f" {amount}, now())"
    )


class TestHealthyLedger:
    def test_real_confirmations_and_refunds_are_coherent_with_exact_totals(
        self, engine: Engine
    ) -> None:
        _paid(engine)
        _paid(engine, refunded=1000)
        _paid(engine, refunded=CAPTURED)

        report = _check(engine)

        assert report.is_consistent
        assert report.discrepancies == ()
        assert report.intents_checked == 3
        assert (report.transactions_checked, report.entry_count) == (5, 10)
        assert report.debit_cents == report.credit_cents == 3 * CAPTURED + 1000 + CAPTURED

    def test_an_empty_database_is_coherent(self, engine: Engine) -> None:
        assert _check(engine).is_consistent


class TestAlteredLedger:
    def test_an_altered_amount_is_reported_with_expected_and_observed(self, engine: Engine) -> None:
        intent = _paid(engine)
        _tamper(
            engine,
            "UPDATE ledger_entries SET amount = 2000 WHERE intent_id = :intent"
            " AND account = 'marchand'",
            intent=intent.id,
        )

        report = _check(engine)

        by_kind = {d.kind: d for d in report.discrepancies}
        balance = by_kind[DiscrepancyKind.INTENT_BALANCE.value]
        assert (balance.resource_id, balance.expected_cents, balance.observed_cents) == (
            str(intent.id),
            CAPTURED,
            2000,
        )
        assert by_kind[DiscrepancyKind.TRANSACTION_UNBALANCED.value].observed_cents == 2000
        assert not report.is_consistent

    def test_the_database_refuses_the_alteration_without_the_trick(self, engine: Engine) -> None:
        intent = _paid(engine)

        with pytest.raises(Exception, match="ajout seul"), engine.begin() as connection:
            connection.execute(
                text("UPDATE ledger_entries SET amount = 1 WHERE intent_id = :i"), {"i": intent.id}
            )

        assert _check(engine).is_consistent

    def test_a_line_added_to_an_unpaid_intent_is_an_orphan(self, engine: Engine) -> None:
        unpaid = add_intent(engine)
        transaction = "00000000-0000-0000-0000-0000000000aa"
        with engine.begin() as connection:  # paire équilibrée : la base l'accepte, le contrôle non
            connection.execute(
                text(_insert_line("client_attente", "debit", 700)),
                {"tx": transaction, "intent": unpaid.id},
            )
            connection.execute(
                text(_insert_line("marchand", "credit", 700)),
                {"tx": transaction, "intent": unpaid.id},
            )

        report = _check(engine)

        (found,) = report.discrepancies
        assert (found.resource_id, found.expected_cents, found.observed_cents) == (
            str(unpaid.id),
            0,
            700,
        )

    def test_a_lone_line_without_counterpart_is_an_unbalanced_transaction(
        self, engine: Engine
    ) -> None:
        intent = _paid(engine)
        transaction = UUID(int=42)
        with engine.begin() as connection:
            connection.execute(text("ALTER TABLE ledger_entries DISABLE TRIGGER USER"))
            connection.execute(
                text(_insert_line("marchand", "credit", 300)),
                {"tx": str(transaction), "intent": intent.id},
            )
            connection.execute(text("ALTER TABLE ledger_entries ENABLE TRIGGER USER"))

        report = _check(engine)

        kinds = {d.kind: d for d in report.discrepancies}
        lone = kinds[DiscrepancyKind.TRANSACTION_UNBALANCED.value]
        assert (lone.resource_id, lone.expected_cents, lone.observed_cents) == (
            str(transaction),
            0,
            300,
        )
        assert kinds[DiscrepancyKind.INTENT_BALANCE.value].observed_cents == CAPTURED + 300

    def test_a_deleted_counterpart_leaves_an_unbalanced_transaction(self, engine: Engine) -> None:
        intent = _paid(engine, refunded=1000)
        _tamper(
            engine,
            "DELETE FROM ledger_entries WHERE intent_id = :intent AND account = 'remboursements'",
            intent=intent.id,
        )

        report = _check(engine)

        assert sorted(d.kind for d in report.discrepancies) == [
            DiscrepancyKind.TRANSACTION_UNBALANCED.value
        ]


class TestReadOnly:
    def test_the_check_runs_in_a_read_only_repeatable_read_transaction_and_writes_nothing(
        self, engine: Engine
    ) -> None:
        _paid(engine, refunded=1000)
        observed: list[tuple[bool, Any, str]] = []

        def spy(_c: Any, cursor: Any, statement: str, *_: Any) -> None:
            observed.append(
                (cursor.connection.read_only, cursor.connection.isolation_level, statement)
            )

        def dump() -> list[tuple[Any, ...]]:
            with engine.connect() as connection:
                return [
                    tuple(row)
                    for table in ("payment_intents", "ledger_entries", "refunds")
                    for row in connection.execute(text(f"SELECT * FROM {table} ORDER BY 1"))  # noqa: S608
                ]

        before = dump()
        event.listen(engine, "before_cursor_execute", spy)
        _check(engine)
        event.remove(engine, "before_cursor_execute", spy)

        assert dump() == before
        assert observed
        assert all(read_only for read_only, _, _ in observed)
        assert all(level.name == "REPEATABLE_READ" for _, level, _ in observed)
        assert all(statement.lstrip().upper().startswith("SELECT") for _, _, statement in observed)


class TestVolume:
    def test_ten_thousand_intents_are_checked_in_under_two_seconds(self, engine: Engine) -> None:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO payment_intents (id, order_reference, amount, currency, status,"
                    " refunded_amount, expires_at, created_at) SELECT gen_random_uuid(),"
                    " 'VOL-' || g, 5000, 'EUR', 'succeeded', CASE WHEN g % 4 = 0 THEN 2000 ELSE 0"
                    " END, now(), now() FROM generate_series(1, :n) g"
                ),
                {"n": VOLUME},
            )
            connection.execute(
                text(
                    "WITH p AS (SELECT id, gen_random_uuid() AS tx FROM payment_intents)"
                    " INSERT INTO ledger_entries (id, transaction_id, intent_id, account,"
                    " direction, amount, created_at)"
                    " SELECT gen_random_uuid(), tx, id, 'client_attente', 'debit', 5000, now()"
                    " FROM p UNION ALL"
                    " SELECT gen_random_uuid(), tx, id, 'marchand', 'credit', 5000, now() FROM p"
                )
            )
            connection.execute(
                text(
                    "WITH p AS (SELECT id, gen_random_uuid() AS tx FROM payment_intents"
                    " WHERE refunded_amount > 0)"
                    " INSERT INTO ledger_entries (id, transaction_id, intent_id, account,"
                    " direction, amount, created_at)"
                    " SELECT gen_random_uuid(), tx, id, 'marchand', 'debit', 2000, now() FROM p"
                    " UNION ALL"
                    " SELECT gen_random_uuid(), tx, id, 'remboursements', 'credit', 2000, now()"
                    " FROM p"
                )
            )
        _check(engine)  # échauffe la connexion et les plans

        started = time.perf_counter()
        report = _check(engine)
        elapsed = time.perf_counter() - started

        assert report.is_consistent
        assert report.intents_checked == VOLUME
        assert (report.transactions_checked, report.entry_count) == (12_500, 25_000)
        assert elapsed < 2.0, f"{elapsed:.2f} s pour {VOLUME} intentions"

    def test_one_altered_line_among_ten_thousand_is_found(self, engine: Engine) -> None:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO payment_intents (id, order_reference, amount, currency, status,"
                    " refunded_amount, expires_at, created_at) SELECT gen_random_uuid(),"
                    " 'VOL-' || g, 5000, 'EUR', 'succeeded', 0, now(), now()"
                    " FROM generate_series(1, :n) g"
                ),
                {"n": VOLUME},
            )
            connection.execute(
                text(
                    "WITH p AS (SELECT id, gen_random_uuid() AS tx FROM payment_intents)"
                    " INSERT INTO ledger_entries (id, transaction_id, intent_id, account,"
                    " direction, amount, created_at)"
                    " SELECT gen_random_uuid(), tx, id, 'client_attente', 'debit', 5000, now()"
                    " FROM p UNION ALL"
                    " SELECT gen_random_uuid(), tx, id, 'marchand', 'credit', 5000, now() FROM p"
                )
            )
        _tamper(
            engine,
            "UPDATE ledger_entries SET amount = 4999 WHERE id = (SELECT id FROM ledger_entries"
            " WHERE account = 'marchand' LIMIT 1)",
        )

        started = time.perf_counter()
        report = _check(engine)

        assert report.discrepancy_count == 2
        assert time.perf_counter() - started < 2.0
