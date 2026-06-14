"""returns v1

Revision ID: 20260613_03
Revises: 20260613_02
Create Date: 2026-06-13
"""

from alembic import op
import sqlalchemy as sa


revision = "20260613_03"
down_revision = "20260613_02"
branch_labels = None
depends_on = None


def table_exists(table_name):
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return table_name in inspector.get_table_names()


def create_index_once(name, table_name, columns, unique=False):
    if not table_exists(table_name):
        return
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing = {index["name"] for index in inspector.get_indexes(table_name)}
    if name not in existing:
        op.create_index(name, table_name, columns, unique=unique)


def upgrade():
    if not table_exists("returns"):
        op.create_table(
            "returns",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("return_no", sa.String(length=80), nullable=False),
            sa.Column("order_id", sa.Integer(), sa.ForeignKey("orders.id"), nullable=False),
            sa.Column("return_type", sa.String(length=40), nullable=False),
            sa.Column("reason", sa.String(length=255), nullable=True),
            sa.Column("note", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("return_no", name="uq_returns_return_no"),
        )
    create_index_once("ix_returns_order_id", "returns", ["order_id"])
    create_index_once("ix_returns_return_no", "returns", ["return_no"])
    create_index_once("ix_returns_created_at", "returns", ["created_at"])

    if not table_exists("return_items"):
        op.create_table(
            "return_items",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("return_id", sa.Integer(), sa.ForeignKey("returns.id"), nullable=False),
            sa.Column("order_item_id", sa.Integer(), sa.ForeignKey("order_items.id"), nullable=False),
            sa.Column("product_id", sa.Integer(), sa.ForeignKey("products.id"), nullable=False),
            sa.Column("product_variant_id", sa.Integer(), sa.ForeignKey("product_variants.id"), nullable=False),
            sa.Column("quantity", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("reason", sa.String(length=255), nullable=True),
            sa.Column("note", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )
    create_index_once("ix_return_items_return_id", "return_items", ["return_id"])
    create_index_once("ix_return_items_order_item_id", "return_items", ["order_item_id"])
    create_index_once("ix_return_items_product_variant_id", "return_items", ["product_variant_id"])

    if not table_exists("defective_inventory"):
        op.create_table(
            "defective_inventory",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("product_id", sa.Integer(), sa.ForeignKey("products.id"), nullable=False),
            sa.Column("product_variant_id", sa.Integer(), sa.ForeignKey("product_variants.id"), nullable=False),
            sa.Column("quantity", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.UniqueConstraint("product_variant_id", name="uq_defective_inventory_variant"),
        )
    create_index_once("ix_defective_inventory_product_id", "defective_inventory", ["product_id"])
    create_index_once("ix_defective_inventory_product_variant_id", "defective_inventory", ["product_variant_id"])

    if not table_exists("inventory_movements"):
        op.create_table(
            "inventory_movements",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("product_id", sa.Integer(), sa.ForeignKey("products.id"), nullable=False),
            sa.Column("product_variant_id", sa.Integer(), sa.ForeignKey("product_variants.id"), nullable=False),
            sa.Column("movement_type", sa.String(length=80), nullable=False),
            sa.Column("quantity", sa.Integer(), nullable=False),
            sa.Column("reference_type", sa.String(length=80), nullable=True),
            sa.Column("reference_id", sa.Integer(), nullable=True),
            sa.Column("note", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )
    create_index_once("ix_inventory_movements_product_id", "inventory_movements", ["product_id"])
    create_index_once("ix_inventory_movements_product_variant_id", "inventory_movements", ["product_variant_id"])
    create_index_once("ix_inventory_movements_reference", "inventory_movements", ["reference_type", "reference_id"])
    create_index_once("ix_inventory_movements_created_at", "inventory_movements", ["created_at"])


def downgrade():
    pass
