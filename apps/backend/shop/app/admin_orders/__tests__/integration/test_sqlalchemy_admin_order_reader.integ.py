"""Lecteur SQL des commandes admin : filtre, recherche, tri, pagination, détail."""

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import Engine, StaticPool, create_engine, event
from sqlalchemy.orm import Session

from app.admin_orders.domain.entities.admin_order_page import AdminOrderPage
from app.admin_orders.infrastructure.repositories.sqlalchemy_admin_order_reader import (
    SqlAlchemyAdminOrderReader,
)
from app.order.infrastructure.models.order_base import OrderBase
from app.order.infrastructure.models.order_line_model import OrderLineModel
from app.order.infrastructure.models.order_model import OrderModel
from app.order.infrastructure.models.order_product_model import OrderProductModel

START = datetime(2026, 10, 20, 9, 0, tzinfo=UTC)
FIRST_ID = "00000000-0000-4000-8000-000000000001"


def _order(index: int, status: str, email: str, number: str) -> OrderModel:
    return OrderModel(
        id=f"00000000-0000-4000-8000-{index:012d}",
        number=number,
        status=status,
        email=email,
        ship_full_name="Camille Martin",
        ship_line1="12 rue des Alpes",
        ship_line2="Bâtiment B",
        ship_postal_code="38000",
        ship_city="Grenoble",
        ship_country="FR",
        subtotal_cents=7800,
        shipping_cents=490,
        total_cents=8290,
        idempotency_key=f"cle-{index}",
        request_fingerprint="f" * 64,
        created_at=START + timedelta(hours=index),
        user_id=None,
    )


def _line(position: int, product_id: str, name: str, price: int, quantity: int) -> OrderLineModel:
    return OrderLineModel(
        order_id=FIRST_ID,
        position=position,
        product_id=product_id,
        product_name=name,
        unit_price_cents=price,
        quantity=quantity,
    )


@pytest.fixture
def engine() -> Iterator[Engine]:
    built = create_engine(
        "sqlite+pysqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False}
    )
    event.listen(built, "connect", lambda conn, _: conn.execute("PRAGMA foreign_keys=ON"))
    OrderBase.metadata.create_all(built)
    with Session(built) as session:
        session.add_all(
            [
                OrderProductModel(id="tente", name="Tente", price_cents=32900, stock=5),
                OrderProductModel(id="popote", name="Popote", price_cents=3900, stock=5),
                _order(1, "paid", "camille@example.org", "BC-1001"),
                _order(2, "pending_payment", "Autre.Personne@example.org", "BC-1002"),
                _order(3, "expired", "camille@example.org", "BC-1003"),
                _order(4, "refunded", "100%_sur@example.org", "BC-1004"),
            ]
        )
        session.flush()
        session.add_all(
            [_line(2, "tente", "Tente", 32900, 1), _line(1, "popote", "Popote", 3900, 2)]
        )
        session.commit()
    yield built
    built.dispose()


def _numbers(page: AdminOrderPage) -> list[str]:
    return [item.number for item in page.items]


def test_lists_every_order_newest_first(engine: Engine) -> None:
    page = SqlAlchemyAdminOrderReader(engine).list_orders(None, None, 20, 0)

    assert _numbers(page) == ["BC-1004", "BC-1003", "BC-1002", "BC-1001"]
    assert (page.total, page.limit, page.offset) == (4, 20, 0)


def test_paginates_and_keeps_the_total(engine: Engine) -> None:
    page = SqlAlchemyAdminOrderReader(engine).list_orders(None, None, 2, 2)

    assert _numbers(page) == ["BC-1002", "BC-1001"]
    assert page.total == 4


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        ("paid", ["BC-1001"]),
        ("pending_payment", ["BC-1002"]),
        ("expired", ["BC-1003"]),
        ("refunded", ["BC-1004"]),
    ],
)
def test_filters_by_status(engine: Engine, status: str, expected: list[str]) -> None:
    page = SqlAlchemyAdminOrderReader(engine).list_orders(status, None, 20, 0)

    assert _numbers(page) == expected
    assert page.total == 1


@pytest.mark.parametrize(
    ("search", "expected"),
    [
        ("BC-1002", ["BC-1002"]),
        ("bc-100", ["BC-1004", "BC-1003", "BC-1002", "BC-1001"]),
        ("CAMILLE@example", ["BC-1003", "BC-1001"]),
        ("autre.personne", ["BC-1002"]),
        ("introuvable", []),
        ("%", ["BC-1004"]),  # joker neutralisé : seul l'email qui contient « % » correspond
        ("_", ["BC-1004"]),
    ],
)
def test_searches_by_number_or_email_case_insensitively(
    engine: Engine, search: str, expected: list[str]
) -> None:
    page = SqlAlchemyAdminOrderReader(engine).list_orders(None, search, 20, 0)

    assert _numbers(page) == expected
    assert page.total == len(expected)


def test_status_and_search_combine(engine: Engine) -> None:
    reader = SqlAlchemyAdminOrderReader(engine)

    assert _numbers(reader.list_orders("paid", "camille", 20, 0)) == ["BC-1001"]
    assert reader.list_orders("expired", "BC-1001", 20, 0).total == 0


def test_summaries_count_the_items_and_carry_no_address(engine: Engine) -> None:
    (summary,) = SqlAlchemyAdminOrderReader(engine).list_orders("paid", None, 20, 0).items

    assert (summary.item_count, summary.total_cents, summary.email) == (
        3,
        8290,
        "camille@example.org",
    )
    assert not hasattr(summary, "shipping_address")


def test_a_summary_without_lines_counts_zero(engine: Engine) -> None:
    (summary,) = SqlAlchemyAdminOrderReader(engine).list_orders("expired", None, 20, 0).items

    assert summary.item_count == 0


def test_finds_the_order_with_ordered_lines_and_the_address(engine: Engine) -> None:
    order = SqlAlchemyAdminOrderReader(engine).find(FIRST_ID)

    assert order is not None
    assert (order.number, order.status, order.email) == ("BC-1001", "paid", "camille@example.org")
    assert [(line.name, line.quantity, line.line_total_cents) for line in order.lines] == [
        ("Popote", 2, 7800),
        ("Tente", 1, 32900),
    ]
    address = order.shipping_address
    assert (address.full_name, address.line1, address.line2) == (
        "Camille Martin",
        "12 rue des Alpes",
        "Bâtiment B",
    )
    assert (address.postal_code, address.city, address.country) == ("38000", "Grenoble", "FR")
    assert (order.subtotal_cents, order.shipping_cents, order.total_cents) == (7800, 490, 8290)


def test_an_unknown_order_is_none(engine: Engine) -> None:
    assert SqlAlchemyAdminOrderReader(engine).find("absente") is None
