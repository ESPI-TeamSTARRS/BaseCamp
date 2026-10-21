"""Commande ledger-check de bout en bout sur SQLite : état sain, écarts, lecture seule, panne.

L'état est produit par l'API réelle (création, confirmation, remboursement). Pour altérer le grand
livre, le déclencheur d'ajout seul de SQLite est retiré dans la base de test (la garantie
équivalente de Postgres est contournée de la même façon dans test_ledger_check_postgres).
"""

import io
import json
import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator
from sqlalchemy import Engine, StaticPool, create_engine, event, text

from app.core.config import Settings
from app.core.logging.structlog_business_event_logger import StructlogBusinessEventLogger
from app.intent.infrastructure.models.base import Base
from app.ledgercheck.presentation.cli import main
from app.main import create_app
from app.ratelimit.infrastructure.models.base import Base as RateLimitBase

TOKEN = "tok-shop-test-0001"
SCHEMA_PATH = Path(__file__).resolve().parents[7] / "docs/development/log-event.schema.json"
VALIDATOR = Draft202012Validator(json.loads(SCHEMA_PATH.read_text(encoding="utf-8")))
AMOUNT = 4990


@dataclass
class Env:
    client: TestClient
    engine: Engine
    settings: Settings


@dataclass
class Run:
    code: int
    report: list[str]
    logs: list[dict[str, Any]]
    raw: str


@pytest.fixture
def env() -> Iterator[Env]:
    engine = create_engine(
        "sqlite+pysqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False}
    )
    event.listen(
        engine, "connect", lambda connection, _: connection.execute("PRAGMA foreign_keys=ON")
    )
    Base.metadata.create_all(engine)
    RateLimitBase.metadata.create_all(engine)
    settings = Settings(service_tokens={"shop": TOKEN})
    with TestClient(
        create_app(settings, engine, StructlogBusinessEventLogger("payment", io.StringIO()))
    ) as client:
        yield Env(client, engine, settings)


def _headers(key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {TOKEN}", "Idempotency-Key": key}


def _paid(env: Env, order: str) -> str:
    created = env.client.post(
        "/payments/intents",
        json={"order_reference": order, "amount": AMOUNT, "currency": "EUR"},
        headers=_headers(f"create-{order}-key"),
    )
    intent_id = str(created.json()["id"])
    confirmed = env.client.post(
        f"/payments/intents/{intent_id}/confirm",
        json={"payment_method": "pm_test_success"},
        headers=_headers(f"confirm-{order}-key"),
    )
    assert confirmed.status_code == 200
    return intent_id


def _refund(env: Env, intent_id: str, amount: int) -> None:
    response = env.client.post(
        f"/payments/intents/{intent_id}/refunds",
        json={"amount": amount},
        headers=_headers(f"refund-{intent_id}-{amount}"),
    )
    assert response.status_code == 201


def _run(env: Env, engine: Engine | None = None) -> Run:
    logs = io.StringIO()
    out = io.StringIO()
    code = main(
        env.settings, engine or env.engine, StructlogBusinessEventLogger("payment", logs), out
    )
    records = [json.loads(line) for line in logs.getvalue().splitlines()]
    for record in records:
        assert not [error.message for error in VALIDATOR.iter_errors(record)], record
    return Run(code, out.getvalue().splitlines(), records, logs.getvalue() + out.getvalue())


def _execute(env: Env, sql: str, **params: object) -> None:
    with env.engine.begin() as connection:
        connection.execute(text(sql), params)


def _dump(env: Env) -> list[tuple[Any, ...]]:
    with env.engine.connect() as connection:
        rows: list[tuple[Any, ...]] = []
        for table in ("payment_intents", "ledger_entries", "refunds", "outbox"):
            rows += [tuple(row) for row in connection.execute(text(f"SELECT * FROM {table}"))]  # noqa: S608
        return rows


def _allow_alteration(env: Env) -> None:
    _execute(env, "DROP TRIGGER ledger_entries_no_update")
    _execute(env, "DROP TRIGGER ledger_entries_no_delete")


def _hex(intent_id: str) -> str:
    return intent_id.replace("-", "")


class TestHealthyLedger:
    def test_after_a_confirmation_and_a_refund_it_says_coherent_and_exits_zero(
        self, env: Env
    ) -> None:
        _refund(env, _paid(env, "CMD-1"), 1990)
        _paid(env, "CMD-2")

        run = _run(env)

        assert run.code == 0
        assert run.report[0] == "grand livre cohérent"
        assert "intentions contrôlées : 2" in run.report
        assert "transactions : 3" in run.report
        assert "débits : 9980 centimes" in run.report
        assert "crédits : 9980 centimes" in run.report
        assert "écarts : 0" in run.report

    def test_an_empty_database_is_coherent(self, env: Env) -> None:
        run = _run(env)

        assert (run.code, run.report[0]) == (0, "grand livre cohérent")

    def test_it_emits_a_single_success_summary_following_the_common_schema(self, env: Env) -> None:
        _paid(env, "CMD-1")

        run = _run(env)

        (summary,) = run.logs
        assert (summary["event"], summary["outcome"], summary["level"]) == (
            "ledger.check_completed",
            "success",
            "info",
        )
        assert summary["attributes"]["intents_checked"] == 1
        assert "duration_ms" in summary

    def test_it_never_writes_anything(self, env: Env) -> None:
        _refund(env, _paid(env, "CMD-1"), 1990)
        statements: list[str] = []
        event.listen(
            env.engine,
            "before_cursor_execute",
            lambda _c, _cur, statement, *_: statements.append(statement),
        )
        before = _dump(env)

        _run(env)

        assert _dump(env) == before
        assert statements
        assert all(statement.lstrip().upper().startswith("SELECT") for statement in statements)


class TestInconsistentLedger:
    def test_an_altered_line_is_listed_with_expected_and_observed_and_exits_one(
        self, env: Env
    ) -> None:
        intent_id = _paid(env, "CMD-1")
        _allow_alteration(env)
        _execute(
            env,
            "UPDATE ledger_entries SET amount = :altered WHERE intent_id = :id AND account = 'marchand'",
            altered=AMOUNT - 500,
            id=_hex(intent_id),
        )

        run = _run(env)

        assert run.code == 1
        assert run.report[0] == "grand livre INCOHÉRENT"
        assert (
            f"intention {intent_id} : solde marchand attendu {AMOUNT}, constaté {AMOUNT - 500}"
            f" (écart -500)" in run.report
        )
        assert any(
            line.startswith("transaction ") and "débits 4990, crédits 4490" in line
            for line in run.report
        )

    def test_an_orphan_line_on_an_unpaid_intent_is_listed(self, env: Env) -> None:
        created = env.client.post(
            "/payments/intents",
            json={"order_reference": "CMD-1", "amount": AMOUNT, "currency": "EUR"},
            headers=_headers("create-orphan-key"),
        )
        intent_id = str(created.json()["id"])
        transaction = uuid.uuid4().hex
        for account, direction in (("client_attente", "debit"), ("marchand", "credit")):
            _execute(
                env,
                "INSERT INTO ledger_entries (id, transaction_id, intent_id, account, direction,"
                " amount, created_at) VALUES (:id, :tx, :intent, :account, :direction, 700,"
                " '2026-01-01 00:00:00')",
                id=uuid.uuid4().hex,
                tx=transaction,
                intent=_hex(intent_id),
                account=account,
                direction=direction,
            )

        run = _run(env)

        assert run.code == 1
        assert (
            f"intention {intent_id} : solde marchand attendu 0, constaté 700 (écart +700)"
            in run.report
        )
        assert "écarts : 1" in run.report

    def test_a_deleted_line_breaks_its_transaction_and_the_intent_balance(self, env: Env) -> None:
        intent_id = _paid(env, "CMD-1")
        _allow_alteration(env)
        _execute(
            env,
            "DELETE FROM ledger_entries WHERE intent_id = :id AND account = 'marchand'",
            id=_hex(intent_id),
        )

        run = _run(env)

        assert run.code == 1
        assert (
            f"intention {intent_id} : solde marchand attendu {AMOUNT}, constaté 0 (écart -4990)"
            in run.report
        )
        assert any("débits 4990, crédits 0" in line for line in run.report)
        assert "écarts : 2" in run.report

    def test_errors_are_logged_with_the_common_schema_and_the_metric_is_reported(
        self, env: Env
    ) -> None:
        intent_id = _paid(env, "CMD-1")
        _allow_alteration(env)
        _execute(
            env,
            "DELETE FROM ledger_entries WHERE intent_id = :id AND account = 'marchand'",
            id=_hex(intent_id),
        )

        run = _run(env)

        details = [r for r in run.logs if r["event"] == "ledger.inconsistency_detected"]
        summary = run.logs[-1]
        assert {r["reason"] for r in details} == {
            "intent_balance_mismatch",
            "transaction_unbalanced",
        }
        assert all((r["outcome"], r["level"]) == ("error", "error") for r in details)
        assert (summary["event"], summary["outcome"], summary["reason"]) == (
            "ledger.check_completed",
            "error",
            "ledger_inconsistent",
        )
        assert len({r["correlation_id"] for r in run.logs}) == 1
        assert "métrique payment_ledger_discrepancies 2" in run.report

    def test_nothing_sensitive_reaches_the_output_or_the_logs(self, env: Env) -> None:
        intent_id = _paid(env, "CMD-SECRET-REF")
        _allow_alteration(env)
        _execute(
            env,
            "DELETE FROM ledger_entries WHERE intent_id = :id AND account = 'marchand'",
            id=_hex(intent_id),
        )

        run = _run(env)

        for forbidden in (
            TOKEN,
            "CMD-SECRET-REF",
            f"confirm-CMD-SECRET-REF-key",
            "pm_test_success",
        ):
            assert forbidden not in run.raw

    def test_a_run_leaves_the_altered_ledger_untouched(self, env: Env) -> None:
        intent_id = _paid(env, "CMD-1")
        _allow_alteration(env)
        _execute(
            env,
            "DELETE FROM ledger_entries WHERE intent_id = :id AND account = 'marchand'",
            id=_hex(intent_id),
        )
        before = _dump(env)

        first, second = _run(env), _run(env)

        assert _dump(env) == before
        assert first.report == second.report


class TestUnavailableDatabase:
    def test_it_exits_two_logs_a_failure_and_leaks_no_database_detail(self) -> None:
        engine = create_engine("sqlite+pysqlite://", poolclass=StaticPool)  # sans tables
        env = Env(None, engine, Settings())  # type: ignore[arg-type]

        run = _run(env)

        assert run.code == 2
        assert run.report == ["contrôle impossible : base de données indisponible"]
        (failed,) = run.logs
        assert (failed["event"], failed["outcome"], failed["reason"]) == (
            "ledger.check_failed",
            "error",
            "database_error",
        )
        assert "no such table" not in run.raw
