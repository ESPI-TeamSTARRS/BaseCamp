"""Commandes : orders, order_lines (prix figes en centimes) et stock_reservations.

La cle d'idempotence est unique en base : un rejeu ne peut jamais creer un doublon, meme en
concurrence. Le stock reste protege par la contrainte ck_products_stock_non_negative (0002).

Revision ID: 0003
Revises: 0002
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "orders",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("number", sa.String(16), nullable=False, unique=True),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("email", sa.String(254), nullable=False),
        sa.Column("ship_full_name", sa.String(120), nullable=False),
        sa.Column("ship_line1", sa.String(200), nullable=False),
        sa.Column("ship_line2", sa.String(200), nullable=True),
        sa.Column("ship_postal_code", sa.String(20), nullable=False),
        sa.Column("ship_city", sa.String(120), nullable=False),
        sa.Column("ship_country", sa.String(2), nullable=False),
        sa.Column("subtotal_cents", sa.Integer(), nullable=False),
        sa.Column("shipping_cents", sa.Integer(), nullable=False),
        sa.Column("total_cents", sa.Integer(), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("request_fingerprint", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("idempotency_key", name="uq_orders_idempotency_key"),
        sa.CheckConstraint("status IN ('pending_payment')", name="ck_orders_status"),
        sa.CheckConstraint(
            "ship_country IN ('FR', 'BE', 'CH', 'LU', 'DE', 'ES', 'IT')", name="ck_orders_country"
        ),
        sa.CheckConstraint(
            "subtotal_cents >= 0 AND shipping_cents >= 0 AND total_cents = subtotal_cents + shipping_cents",
            name="ck_orders_amounts",
        ),
    )
    op.create_table(
        "order_lines",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("order_id", sa.String(36), sa.ForeignKey("orders.id"), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("product_id", sa.String(64), sa.ForeignKey("products.id"), nullable=False),
        sa.Column("product_name", sa.String(200), nullable=False),
        sa.Column("unit_price_cents", sa.Integer(), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.CheckConstraint("unit_price_cents > 0", name="ck_order_lines_price_positive"),
        sa.CheckConstraint("quantity > 0", name="ck_order_lines_quantity_positive"),
    )
    op.create_index("ix_order_lines_order_id", "order_lines", ["order_id"])
    op.create_table(
        "stock_reservations",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("order_id", sa.String(36), sa.ForeignKey("orders.id"), nullable=False),
        sa.Column("product_id", sa.String(64), sa.ForeignKey("products.id"), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.CheckConstraint("quantity > 0", name="ck_stock_reservations_quantity_positive"),
        sa.CheckConstraint("status IN ('reserved')", name="ck_stock_reservations_status"),
    )
    op.create_index("ix_stock_reservations_order_id", "stock_reservations", ["order_id"])


def downgrade() -> None:
    op.drop_index("ix_stock_reservations_order_id", table_name="stock_reservations")
    op.drop_table("stock_reservations")
    op.drop_index("ix_order_lines_order_id", table_name="order_lines")
    op.drop_table("order_lines")
    op.drop_table("orders")
