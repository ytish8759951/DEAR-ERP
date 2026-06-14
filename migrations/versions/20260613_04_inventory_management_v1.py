"""inventory management v1

Revision ID: 20260613_04
Revises: 20260613_03
Create Date: 2026-06-13
"""

from alembic import op
import sqlalchemy as sa


revision = "20260613_04"
down_revision = "20260613_03"
branch_labels = None
depends_on = None


def table_exists(table_name):
    inspector = sa.inspect(op.get_bind())
    return table_name in inspector.get_table_names()


def column_exists(table_name, column_name):
    if not table_exists(table_name):
        return False
    inspector = sa.inspect(op.get_bind())
    return column_name in {column["name"] for column in inspector.get_columns(table_name)}


def add_column_once(table_name, column_name, column):
    if table_exists(table_name) and not column_exists(table_name, column_name):
        op.add_column(table_name, column)


def upgrade():
    add_column_once(
        "return_items",
        "process_status",
        sa.Column("process_status", sa.String(length=40), nullable=False, server_default="待處理"),
    )
    add_column_once("inventory_movements", "before_quantity", sa.Column("before_quantity", sa.Integer(), nullable=True))
    add_column_once("inventory_movements", "after_quantity", sa.Column("after_quantity", sa.Integer(), nullable=True))
    add_column_once("inventory_movements", "source_no", sa.Column("source_no", sa.String(length=80), nullable=True))
    add_column_once("inventory_movements", "operator", sa.Column("operator", sa.String(length=80), nullable=True))


def downgrade():
    pass
