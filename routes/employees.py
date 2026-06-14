from datetime import datetime

from flask import Blueprint, current_app, flash, redirect, render_template, request, url_for
from sqlalchemy.exc import IntegrityError

from config import Config
from decorators import login_required
from extensions import db
from models import Employee, EmployeeRole
from pagination import get_page_args


employees_bp = Blueprint("employees", __name__, url_prefix="/employees")

EMPLOYEE_STATUSES = ["在職", "離職", "停用"]


def clean(value):
    return (value or "").strip()


def parse_date(value):
    value = clean(value)
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None


def next_employee_code():
    latest = (
        Employee.query.with_entities(Employee.employee_code)
        .filter(Employee.employee_code.like("E%"))
        .order_by(Employee.employee_code.desc())
        .first()
    )
    sequence = 0
    if latest and latest.employee_code and latest.employee_code[1:].isdigit():
        sequence = int(latest.employee_code[1:])
    return f"E{sequence + 1:06d}"


def backfill_employee_codes():
    changed = False
    for employee in Employee.query.filter(
        (Employee.employee_code.is_(None)) | (Employee.employee_code == "")
    ).order_by(Employee.id):
        employee.employee_code = next_employee_code()
        changed = True
    if changed:
        db.session.commit()


def role_options(selected_role_id=None):
    roles = EmployeeRole.query.filter(EmployeeRole.is_active.is_(True)).order_by(EmployeeRole.name).all()
    if selected_role_id:
        selected_role = EmployeeRole.query.get(selected_role_id)
        if selected_role and selected_role not in roles:
            roles.append(selected_role)
    return roles


def employee_filters():
    return {
        "name": clean(request.args.get("name")),
        "login_username": clean(request.args.get("login_username")),
        "role_id": clean(request.args.get("role_id")),
        "status": clean(request.args.get("status")),
    }


def apply_employee_filters(query, filters):
    if filters["name"]:
        query = query.filter(Employee.name.like(f"%{filters['name']}%"))
    if filters["login_username"]:
        query = query.filter(Employee.login_username.like(f"%{filters['login_username']}%"))
    if filters["role_id"]:
        try:
            query = query.filter(Employee.role_id == int(filters["role_id"]))
        except ValueError:
            pass
    if filters["status"] in EMPLOYEE_STATUSES:
        query = query.filter(Employee.status == filters["status"])
    return query


def sync_employee(employee, is_create=False):
    field_errors = {}
    employee.name = clean(request.form.get("name"))
    employee.login_username = clean(request.form.get("login_username")) or None
    password = request.form.get("login_password") or ""
    if is_create and not password:
        field_errors["login_password"] = "請輸入登入密碼"
    if password:
        employee.set_login_password(password)
    employee.phone = clean(request.form.get("phone"))
    try:
        employee.role_id = int(request.form.get("role_id") or 0) or None
    except (TypeError, ValueError):
        employee.role_id = None
    role = EmployeeRole.query.get(employee.role_id) if employee.role_id else None
    employee.role = role.name if role else ""
    employee.hire_date = parse_date(request.form.get("hire_date"))
    employee.resign_date = parse_date(request.form.get("resign_date"))
    employee.note = clean(request.form.get("note"))
    status = clean(request.form.get("status")) or "在職"
    employee.status = status if status in EMPLOYEE_STATUSES else "在職"
    employee.is_active = employee.status == "在職"
    if employee.status == "離職" and not employee.resign_date:
        employee.resign_date = datetime.now().date()
    if employee.status == "在職":
        employee.resign_date = None
    if not employee.name:
        field_errors["name"] = "請輸入員工姓名"
    if not employee.login_username:
        field_errors["login_username"] = "請輸入登入帳號"
    if not employee.role_id:
        field_errors["role_id"] = "請選擇角色"
    return not field_errors, field_errors


def render_form(employee, action, title, is_create=False, status_code=200, form_error=None, field_errors=None):
    field_errors = field_errors or {}
    return (
        render_template(
            "employees/form.html",
            employee=employee,
            action=action,
            title=title,
            is_create=is_create,
            roles=role_options(employee.role_id),
            statuses=EMPLOYEE_STATUSES,
            form_error=form_error,
            errors=["請確認必填欄位是否已完整填寫。"] if field_errors else [],
            field_errors=field_errors,
        ),
        status_code,
    )


@employees_bp.route("")
@employees_bp.route("/")
@login_required
def index():
    backfill_employee_codes()
    filters = employee_filters()
    page, per_page = get_page_args(request, Config.DEFAULT_PAGE_SIZE, Config.PAGE_SIZE_OPTIONS)
    query = apply_employee_filters(Employee.query, filters).order_by(Employee.created_at.desc(), Employee.id.desc())
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)
    return render_template(
        "employees/index.html",
        employees=pagination.items,
        pagination=pagination,
        filters=filters,
        roles=EmployeeRole.query.order_by(EmployeeRole.is_active.desc(), EmployeeRole.name).all(),
        statuses=EMPLOYEE_STATUSES,
        page_size_options=Config.PAGE_SIZE_OPTIONS,
    )


@employees_bp.route("/new", methods=["GET", "POST"])
@login_required
def create():
    employee = Employee(employee_code=next_employee_code(), status="在職", is_active=True)
    if request.method == "POST":
        try:
            employee.employee_code = next_employee_code()
            is_valid, field_errors = sync_employee(employee, is_create=True)
            if is_valid:
                db.session.add(employee)
                try:
                    db.session.commit()
                    flash("員工已新增。", "success")
                    return redirect(url_for("employees.detail", employee_id=employee.id))
                except IntegrityError:
                    db.session.rollback()
                    field_errors["login_username"] = "登入帳號或員工編號已存在。"
            else:
                db.session.rollback()
            return render_form(employee, url_for("employees.create"), "新增員工", True, 200, None, field_errors)
        except Exception:
            db.session.rollback()
            current_app.logger.exception("Employee create failed")
            return render_form(
                employee,
                url_for("employees.create"),
                "新增員工",
                True,
                200,
                None,
                {"form": "系統儲存失敗，請檢查資料是否完整。"},
            )
    return render_form(employee, url_for("employees.create"), "新增員工", True)


@employees_bp.route("/<int:employee_id>")
@login_required
def detail(employee_id):
    employee = Employee.query.get_or_404(employee_id)
    return render_template(
        "employees/detail.html",
        employee=employee,
    )


@employees_bp.route("/<int:employee_id>/edit", methods=["GET", "POST"])
@login_required
def edit(employee_id):
    employee = Employee.query.get_or_404(employee_id)
    if request.method == "POST":
        try:
            is_valid, field_errors = sync_employee(employee)
            if is_valid:
                try:
                    db.session.commit()
                    flash("員工資料已更新。", "success")
                    return redirect(url_for("employees.detail", employee_id=employee.id))
                except IntegrityError:
                    db.session.rollback()
                    field_errors["login_username"] = "登入帳號已存在。"
            else:
                db.session.rollback()
            return render_form(employee, url_for("employees.edit", employee_id=employee.id), "編輯員工", False, 200, None, field_errors)
        except Exception:
            db.session.rollback()
            current_app.logger.exception("Employee update failed")
            return render_form(
                employee,
                url_for("employees.edit", employee_id=employee.id),
                "編輯員工",
                False,
                200,
                None,
                {"form": "系統儲存失敗，請檢查資料是否完整。"},
            )
    return render_form(employee, url_for("employees.edit", employee_id=employee.id), "編輯員工")


@employees_bp.route("/<int:employee_id>/deactivate", methods=["POST"])
@login_required
def deactivate(employee_id):
    employee = Employee.query.get_or_404(employee_id)
    try:
        employee.status = "停用"
        employee.is_active = False
        db.session.commit()
        flash("員工已停用。", "success")
    except Exception:
        db.session.rollback()
        current_app.logger.exception("Employee deactivate failed")
        flash("系統儲存失敗，請檢查資料是否完整。", "danger")
    return redirect(url_for("employees.index"))
