"""customer management v1

Revision ID: 20260613_05
Revises: 20260613_04
Create Date: 2026-06-13
"""

from alembic import op
import sqlalchemy as sa


revision = "20260613_05"
down_revision = "20260613_04"
branch_labels = None
depends_on = None


def table_exists(table_name):
    return table_name in sa.inspect(op.get_bind()).get_table_names()


def column_exists(table_name, column_name):
    if not table_exists(table_name):
        return False
    return column_name in {column["name"] for column in sa.inspect(op.get_bind()).get_columns(table_name)}


def index_exists(table_name, index_name):
    if not table_exists(table_name):
        return False
    return index_name in {index["name"] for index in sa.inspect(op.get_bind()).get_indexes(table_name)}


def upgrade():
    if table_exists("customers") and not column_exists("customers", "is_active"):
        op.add_column("customers", sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()))
    if table_exists("customers") and not index_exists("customers", "ix_customers_is_active"):
        op.create_index("ix_customers_is_active", "customers", ["is_active"])


def downgrade():
    pass
