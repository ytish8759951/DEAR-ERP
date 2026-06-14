"""system management v1

Revision ID: 20260613_01
Revises:
Create Date: 2026-06-13
"""

from alembic import op
import sqlalchemy as sa


revision = "20260613_01"
down_revision = None
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


def create_index_once(name, table_name, columns, unique=False):
    if not table_exists(table_name):
        return
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing = {index["name"] for index in inspector.get_indexes(table_name)}
    if name not in existing:
        op.create_index(name, table_name, columns, unique=unique)


def add_column_once(table_name, column_name, column):
    if table_exists(table_name) and not column_exists(table_name, column_name):
        op.add_column(table_name, column)


def upgrade():
    if not table_exists("customer_categories"):
        op.create_table(
            "customer_categories",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("name", sa.String(length=80), nullable=False),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )
        create_index_once("ix_customer_categories_name", "customer_categories", ["name"], unique=True)
        create_index_once("ix_customer_categories_is_active", "customer_categories", ["is_active"])

    if not table_exists("employee_roles"):
        op.create_table(
            "employee_roles",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("name", sa.String(length=80), nullable=False),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )
        create_index_once("ix_employee_roles_name", "employee_roles", ["name"], unique=True)
        create_index_once("ix_employee_roles_is_active", "employee_roles", ["is_active"])

    if not table_exists("order_sources"):
        op.create_table(
            "order_sources",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("name", sa.String(length=80), nullable=False),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )
        create_index_once("ix_order_sources_name", "order_sources", ["name"], unique=True)
        create_index_once("ix_order_sources_is_active", "order_sources", ["is_active"])

    add_column_once("customers", "category_id", sa.Column("category_id", sa.Integer(), nullable=True))
    add_column_once("employees", "login_username", sa.Column("login_username", sa.String(length=80), nullable=True))
    add_column_once("employees", "login_password_hash", sa.Column("login_password_hash", sa.String(length=255), nullable=True))
    add_column_once("employees", "role_id", sa.Column("role_id", sa.Integer(), nullable=True))
    add_column_once("employees", "hire_date", sa.Column("hire_date", sa.Date(), nullable=True))
    add_column_once("employees", "resign_date", sa.Column("resign_date", sa.Date(), nullable=True))
    add_column_once("employees", "note", sa.Column("note", sa.Text(), nullable=True))

    if table_exists("employees"):
        create_index_once("ix_employees_login_username", "employees", ["login_username"], unique=True)

    if not table_exists("attendance_records"):
        op.create_table(
            "attendance_records",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("employee_id", sa.Integer(), sa.ForeignKey("employees.id"), nullable=False),
            sa.Column("record_date", sa.Date(), nullable=False),
            sa.Column("clock_in_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("clock_out_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("work_hours", sa.Numeric(6, 2), nullable=False, server_default="0"),
            sa.Column("note", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )
        create_index_once("ix_attendance_records_record_date", "attendance_records", ["record_date"])
        create_index_once("ix_attendance_records_employee_date", "attendance_records", ["employee_id", "record_date"])

    if not table_exists("leave_requests"):
        op.create_table(
            "leave_requests",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("employee_id", sa.Integer(), sa.ForeignKey("employees.id"), nullable=False),
            sa.Column("leave_type", sa.String(length=80), nullable=False, server_default="請假"),
            sa.Column("start_date", sa.Date(), nullable=False),
            sa.Column("end_date", sa.Date(), nullable=False),
            sa.Column("status", sa.String(length=40), nullable=False, server_default="pending"),
            sa.Column("reason", sa.Text(), nullable=True),
            sa.Column("reviewer_id", sa.Integer(), sa.ForeignKey("employees.id"), nullable=True),
            sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )
        create_index_once("ix_leave_requests_employee_dates", "leave_requests", ["employee_id", "start_date", "end_date"])

    if not table_exists("work_schedules"):
        op.create_table(
            "work_schedules",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("employee_id", sa.Integer(), sa.ForeignKey("employees.id"), nullable=False),
            sa.Column("work_date", sa.Date(), nullable=False),
            sa.Column("shift_name", sa.String(length=80), nullable=True),
            sa.Column("start_time", sa.Time(), nullable=True),
            sa.Column("end_time", sa.Time(), nullable=True),
            sa.Column("is_day_off", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("note", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )
        create_index_once("ix_work_schedules_work_date", "work_schedules", ["work_date"])
        create_index_once("ix_work_schedules_is_day_off", "work_schedules", ["is_day_off"])
        create_index_once("ix_work_schedules_employee_date", "work_schedules", ["employee_id", "work_date"])

    if not table_exists("shift_change_requests"):
        op.create_table(
            "shift_change_requests",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("requester_employee_id", sa.Integer(), sa.ForeignKey("employees.id"), nullable=False),
            sa.Column("target_employee_id", sa.Integer(), sa.ForeignKey("employees.id"), nullable=True),
            sa.Column("original_work_date", sa.Date(), nullable=False),
            sa.Column("requested_work_date", sa.Date(), nullable=True),
            sa.Column("request_type", sa.String(length=40), nullable=False, server_default="shift_change"),
            sa.Column("status", sa.String(length=40), nullable=False, server_default="pending"),
            sa.Column("reason", sa.Text(), nullable=True),
            sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )


def downgrade():
    for table_name in [
        "shift_change_requests",
        "work_schedules",
        "leave_requests",
        "attendance_records",
        "order_sources",
    ]:
        if table_exists(table_name):
            op.drop_table(table_name)
