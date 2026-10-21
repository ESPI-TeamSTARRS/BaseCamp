"""Le traitement déclenchable `python -m app.order_expiration` écrit des logs conformes au schéma."""

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from sqlalchemy import Engine, create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.order.infrastructure.models.order_base import OrderBase
from app.order.infrastructure.models.order_model import OrderModel
from app.order.infrastructure.models.order_product_model import OrderProductModel
from app.order.infrastructure.models.stock_reservation_model import StockReservationModel
from app.order_expiration import __main__ as cli

SCHEMA_PATH = Path(__file__).resolve().parents[7] / "docs/development/log-event.schema.json"


def _engine_with_an_old_unpaid_order() -> Engine:
    engine = create_engine(
        "sqlite+pysqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False}
    )
    OrderBase.metadata.create_all(engine)
    with Session(engine) as session:
        session.add(OrderProductModel(id="popote", name="Popote", price_cents=3900, stock=8))
        session.add(
            OrderModel(
                id="0b6b1f2e-6c52-4d3b-8a52-1d6f7a9b2c10",
                number="BC-ABCDEFGHJK",
                status="pending_payment",
                email="camille.martin@example.org",
                ship_full_name="Camille Martin",
                ship_line1="12 rue des Alpes",
                ship_postal_code="38000",
                ship_city="Grenoble",
                ship_country="FR",
                subtotal_cents=7800,
                shipping_cents=0,
                total_cents=7800,
                idempotency_key="cle-cli-0001",
                request_fingerprint="f" * 64,
                created_at=datetime.now(UTC) - timedelta(hours=2),
            )
        )
        session.add(
            StockReservationModel(
                order_id="0b6b1f2e-6c52-4d3b-8a52-1d6f7a9b2c10",
                product_id="popote",
                quantity=2,
                status="reserved",
            )
        )
        session.commit()
    return engine


class TestExpirationCli:
    def test_once_expires_due_orders_and_logs_schema_valid_lines(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        engine = _engine_with_an_old_unpaid_order()
        monkeypatch.setattr(cli, "create_engine", lambda *_, **__: engine)

        exit_code = cli.main(["--once"])

        assert exit_code == 0
        lines = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
        assert [line["event"] for line in lines] == ["order.expired", "order.expiration_completed"]
        validator = Draft202012Validator(json.loads(SCHEMA_PATH.read_text(encoding="utf-8")))
        for line in lines:
            validator.validate(line)
        with Session(engine) as session:
            assert session.scalars(select(OrderModel.status)).one() == "expired"
            assert session.scalars(select(OrderProductModel.stock)).one() == 10

    def test_a_pass_without_anything_due_exits_cleanly_and_silently(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        engine = _engine_with_an_old_unpaid_order()
        monkeypatch.setattr(cli, "create_engine", lambda *_, **__: engine)
        cli.main(["--once"])
        capsys.readouterr()

        assert cli.main(["--once"]) == 0
        assert capsys.readouterr().out == ""

    def test_a_database_failure_exits_with_an_error_and_logs_it(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        broken = create_engine("sqlite+pysqlite://", poolclass=StaticPool)  # sans tables
        monkeypatch.setattr(cli, "create_engine", lambda *_, **__: broken)

        assert cli.main(["--once"]) == 1

        (line,) = [json.loads(row) for row in capsys.readouterr().out.splitlines()]
        assert (line["event"], line["outcome"], line["reason"]) == (
            "order.expiration_failed",
            "error",
            "expiration_error",
        )

    def test_the_loop_option_repeats_until_stopped(self, monkeypatch: pytest.MonkeyPatch) -> None:
        engine = _engine_with_an_old_unpaid_order()
        monkeypatch.setattr(cli, "create_engine", lambda *_, **__: engine)
        seen: dict[str, float] = {}
        monkeypatch.setattr(
            cli, "run_forever", lambda use_case, events, interval: seen.update(interval=interval)
        )

        assert cli.main(["--every", "30"]) == 0
        assert seen == {"interval": 30.0}
