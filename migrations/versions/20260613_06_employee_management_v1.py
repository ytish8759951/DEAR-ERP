"""employee management v1

Revision ID: 20260613_06
Revises: 20260613_05
Create Date: 2026-06-13
"""

from alembic import op
import sqlalchemy as sa


revision = "20260613_06"
down_revision = "20260613_05"
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
    if not table_exists("employees"):
        return
    with op.batch_alter_table("employees") as batch_op:
        if not column_exists("employees", "employee_code"):
            batch_op.add_column(sa.Column("employee_code", sa.String(length=20), nullable=True))
        if not column_exists("employees", "status"):
            batch_op.add_column(sa.Column("status", sa.String(length=20), nullable=False, server_default="在職"))
    if not index_exists("employees", "ix_employees_employee_code"):
        op.create_index("ix_employees_employee_code", "employees", ["employee_code"])
    if not index_exists("employees", "ix_employees_status"):
        op.create_index("ix_employees_status", "employees", ["status"])
    if not index_exists("employees", "ux_employees_employee_code"):
        op.create_index(
            "ux_employees_employee_code",
            "employees",
            ["employee_code"],
            unique=True,
            sqlite_where=sa.text("employee_code IS NOT NULL"),
        )


def downgrade():
    op.drop_index("ux_employees_employee_code", table_name="employees")
    op.drop_index("ix_employees_status", table_name="employees")
    op.drop_index("ix_employees_employee_code", table_name="employees")
    with op.batch_alter_table("employees") as batch_op:
        batch_op.drop_column("status")
        batch_op.drop_column("employee_code")
