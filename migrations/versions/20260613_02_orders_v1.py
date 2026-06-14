"""orders v1

Revision ID: 20260613_02
Revises: 20260613_01
Create Date: 2026-06-13
"""

from alembic import op
import sqlalchemy as sa


revision = "20260613_02"
down_revision = "20260613_01"
branch_labels = None
depends_on = None


def table_exists(table_name):
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return table_name in inspector.get_table_names()


def column_exists(table_name, column_name):
    if not table_exists(table_name):
        return False
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return column_name in {column["name"] for column in inspector.get_columns(table_name)}


def add_column_once(table_name, column_name, column):
    if table_exists(table_name) and not column_exists(table_name, column_name):
        op.add_column(table_name, column)


def create_index_once(name, table_name, columns, unique=False):
    if not table_exists(table_name):
        return
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing = {index["name"] for index in inspector.get_indexes(table_name)}
    if name not in existing:
        op.create_index(name, table_name, columns, unique=unique)


def upgrade():
    add_column_once("customers", "customer_code", sa.Column("customer_code", sa.String(length=20), nullable=True))
    add_column_once("customers", "wholesale_paid", sa.Column("wholesale_paid", sa.Boolean(), nullable=False, server_default=sa.false()))
    add_column_once("customers", "wholesale_paid_date", sa.Column("wholesale_paid_date", sa.Date(), nullable=True))
    create_index_once("ix_customers_customer_code", "customers", ["customer_code"], unique=True)
    create_index_once("ix_customers_wholesale_paid", "customers", ["wholesale_paid"])

    add_column_once("orders", "order_source_id", sa.Column("order_source_id", sa.Integer(), nullable=True))
    add_column_once("orders", "order_date", sa.Column("order_date", sa.Date(), nullable=True))
    add_column_once("orders", "discount_amount", sa.Column("discount_amount", sa.Numeric(12, 2), nullable=False, server_default="0"))
    add_column_once("orders", "shipping_fee", sa.Column("shipping_fee", sa.Numeric(12, 2), nullable=False, server_default="0"))
    add_column_once("orders", "receivable_amount", sa.Column("receivable_amount", sa.Numeric(12, 2), nullable=False, server_default="0"))
    add_column_once("orders", "note", sa.Column("note", sa.Text(), nullable=True))
    add_column_once("orders", "canceled_at", sa.Column("canceled_at", sa.DateTime(timezone=True), nullable=True))
    add_column_once("orders", "updated_at", sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True))
    create_index_once("ix_orders_order_date", "orders", ["order_date"])
    create_index_once("ix_orders_order_source_id", "orders", ["order_source_id"])
    create_index_once("ix_orders_status", "orders", ["status"])

    add_column_once("order_items", "subtotal", sa.Column("subtotal", sa.Numeric(12, 2), nullable=False, server_default="0"))


def downgrade():
    pass
