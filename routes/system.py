from datetime import datetime

from flask import Blueprint, current_app, flash, redirect, render_template, request, session, url_for
from sqlalchemy.exc import IntegrityError

from config import Config
from decorators import login_required
from extensions import db
from models import Customer, CustomerCategory, Employee, EmployeeRole, OrderSource, Product, Supplier
from pagination import get_page_args
from services.gemini_service import get_ai_settings, masked_api_key, test_gemini_connection, update_ai_api_key, MODEL_NAME


system_bp = Blueprint("system", __name__, url_prefix="/system")


def clean(value):
    return (value or "").strip()


def int_value(value):
    if not value:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def date_value(value):
    value = clean(value)
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None


TAB_ALIASES = {
    "vendors": "suppliers",
    "settings": "basic",
}


def normalize_tab(active_tab):
    return TAB_ALIASES.get(active_tab, active_tab)


def redirect_system(active_tab):
    output_tab = {"suppliers": "vendors", "basic": "settings", "ai": "ai"}.get(active_tab, active_tab)
    return redirect(url_for("system.index", active_tab=output_tab))


def admin_required():
    return session.get("username") == "admin"


def next_customer_code():
    latest = Customer.query.with_entities(Customer.customer_code).filter(
        Customer.customer_code.like("D%")
    ).order_by(Customer.customer_code.desc()).first()
    sequence = 0
    if latest and latest.customer_code and latest.customer_code[1:].isdigit():
        sequence = int(latest.customer_code[1:])
    return f"D{sequence + 1:07d}"


def next_employee_code():
    latest = Employee.query.with_entities(Employee.employee_code).filter(
        Employee.employee_code.like("E%")
    ).order_by(Employee.employee_code.desc()).first()
    sequence = 0
    if latest and latest.employee_code and latest.employee_code[1:].isdigit():
        sequence = int(latest.employee_code[1:])
    return f"E{sequence + 1:06d}"


def active_customer_categories():
    return CustomerCategory.query.filter_by(is_active=True).order_by(CustomerCategory.name).all()


def active_employee_roles():
    return EmployeeRole.query.filter_by(is_active=True).order_by(EmployeeRole.name).all()


def active_order_sources():
    return OrderSource.query.filter_by(is_active=True).order_by(OrderSource.name).all()


def require_name(name, label):
    name = clean(name)
    if not name:
        flash(f"{label}名稱不可空白。", "danger")
        return None
    return name


def commit_or_flash(success_message, error_message):
    try:
        db.session.commit()
        flash(success_message, "success")
        return True
    except IntegrityError:
        db.session.rollback()
        flash(error_message, "danger")
        return False
    except Exception:
        db.session.rollback()
        current_app.logger.exception("System save failed")
        flash("系統儲存失敗，請檢查資料是否完整。", "danger")
        return False


def system_filters():
    return {
        "customer_code": clean(request.args.get("customer_code")),
        "customer_name": clean(request.args.get("customer_name")),
        "customer_category_id": clean(request.args.get("customer_category_id")),
        "customer_wholesale_paid": clean(request.args.get("customer_wholesale_paid")),
        "employee_name": clean(request.args.get("employee_name")),
        "employee_role_id": clean(request.args.get("employee_role_id")),
        "employee_status": clean(request.args.get("employee_status")),
        "supplier_name": clean(request.args.get("supplier_name")),
        "supplier_contact_person": clean(request.args.get("supplier_contact_person")),
        "supplier_phone": clean(request.args.get("supplier_phone")),
    }


def customer_query(filters):
    query = Customer.query
    if filters["customer_code"]:
        query = query.filter(Customer.customer_code.like(f"%{filters['customer_code']}%"))
    if filters["customer_name"]:
        query = query.filter(Customer.name.like(f"%{filters['customer_name']}%"))
    category_id = int_value(filters["customer_category_id"])
    if category_id:
        query = query.filter(Customer.category_id == category_id)
    if filters["customer_wholesale_paid"] == "yes":
        query = query.filter(Customer.wholesale_paid.is_(True))
    elif filters["customer_wholesale_paid"] == "no":
        query = query.filter(Customer.wholesale_paid.is_(False))
    return query.order_by(Customer.created_at.desc())


def employee_query(filters):
    query = Employee.query
    if filters["employee_name"]:
        query = query.filter(Employee.name.like(f"%{filters['employee_name']}%"))
    role_id = int_value(filters["employee_role_id"])
    if role_id:
        query = query.filter(Employee.role_id == role_id)
    if filters["employee_status"] == "active":
        query = query.filter(Employee.is_active.is_(True))
    elif filters["employee_status"] == "inactive":
        query = query.filter(Employee.is_active.is_(False))
    return query.order_by(Employee.created_at.desc())


def supplier_query(filters):
    query = Supplier.query
    if filters["supplier_name"]:
        query = query.filter(Supplier.name.like(f"%{filters['supplier_name']}%"))
    if filters["supplier_contact_person"]:
        query = query.filter(Supplier.contact_person.like(f"%{filters['supplier_contact_person']}%"))
    if filters["supplier_phone"]:
        query = query.filter(Supplier.phone.like(f"%{filters['supplier_phone']}%"))
    return query.order_by(Supplier.id.desc())


def set_customer_from_form(customer):
    customer.name = require_name(request.form.get("name"), "客戶")
    customer.phone = clean(request.form.get("phone"))
    customer.line = clean(request.form.get("line"))
    wholesale_paid = request.form.get("wholesale_paid") == "1"
    old_category_name = customer.category.name if customer.category else None
    category_id = int_value(request.form.get("category_id"))
    category = CustomerCategory.query.get(category_id) if category_id else None
    general_category = CustomerCategory.query.filter_by(name="一般客").first()

    if old_category_name == "批發客" and not wholesale_paid:
        category = general_category
    elif category and category.name == "批發客" and not wholesale_paid:
        flash("請先勾選已繳批發金，才能設定為批發客", "danger")
        return False

    customer.wholesale_paid = wholesale_paid
    customer.wholesale_paid_date = date_value(request.form.get("wholesale_paid_date")) if wholesale_paid else None
    customer.category_id = category.id if category else None
    customer.address = clean(request.form.get("address"))
    customer.note = clean(request.form.get("note"))
    return bool(customer.name)


def set_employee_from_form(employee):
    employee.name = require_name(request.form.get("name"), "員工")
    employee.login_username = clean(request.form.get("login_username")) or None
    password = request.form.get("login_password")
    if password:
        employee.set_login_password(password)
    employee.phone = clean(request.form.get("phone"))
    employee.email = clean(request.form.get("email")) or None
    employee.role_id = int_value(request.form.get("role_id"))
    role = EmployeeRole.query.get(employee.role_id) if employee.role_id else None
    employee.role = role.name if role else ""
    employee.is_active = request.form.get("is_active", "1") == "1"
    employee.status = "在職" if employee.is_active else "停用"
    employee.hire_date = date_value(request.form.get("hire_date"))
    employee.resign_date = date_value(request.form.get("resign_date"))
    employee.note = clean(request.form.get("note"))
    return bool(employee.name)


def set_supplier_from_form(supplier):
    supplier.name = require_name(request.form.get("name"), "廠商")
    supplier.contact_person = clean(request.form.get("contact_person"))
    supplier.phone = clean(request.form.get("phone"))
    supplier.line = clean(request.form.get("line"))
    supplier.address = clean(request.form.get("address"))
    supplier.note = clean(request.form.get("note"))
    return bool(supplier.name)


@system_bp.route("/", strict_slashes=False)
@login_required
def index():
    return render_system_page(request.args.get("active_tab", "customers"))


def render_system_page(active_tab="customers", status_code=200, system_errors=None, system_field_errors=None, open_modal=None):
    active_tab = normalize_tab(active_tab)
    _page, per_page = get_page_args(request, Config.DEFAULT_PAGE_SIZE, Config.PAGE_SIZE_OPTIONS)
    filters = system_filters()
    customer_page = max(request.args.get("customer_page", 1, type=int), 1)
    employee_page = max(request.args.get("employee_page", 1, type=int), 1)
    supplier_page = max(request.args.get("supplier_page", 1, type=int), 1)

    customers = customer_query(filters).paginate(page=customer_page, per_page=per_page, error_out=False)
    employees = employee_query(filters).paginate(page=employee_page, per_page=per_page, error_out=False)
    suppliers = supplier_query(filters).paginate(page=supplier_page, per_page=per_page, error_out=False)

    return (
        render_template(
            "system/index.html",
            active_tab=active_tab,
        filters=filters,
        customers=customers,
        employees=employees,
        suppliers=suppliers,
        categories=CustomerCategory.query.order_by(CustomerCategory.is_active.desc(), CustomerCategory.name).all(),
        roles=EmployeeRole.query.order_by(EmployeeRole.is_active.desc(), EmployeeRole.name).all(),
        order_sources=OrderSource.query.order_by(OrderSource.is_active.desc(), OrderSource.name).all(),
        active_categories=active_customer_categories(),
        active_roles=active_employee_roles(),
        active_order_sources=active_order_sources(),
        page_size_options=Config.PAGE_SIZE_OPTIONS,
            ai_settings=get_ai_settings(),
            ai_masked_key=masked_api_key(get_ai_settings().get("api_key", "")),
            ai_model=MODEL_NAME,
            is_admin=admin_required(),
            per_page=per_page,
            system_errors=system_errors or [],
            system_field_errors=system_field_errors or {},
            open_modal=open_modal,
        ),
        status_code,
    )


def required_error_response(active_tab, field_errors, open_modal=None):
    return render_system_page(
        active_tab,
        200,
        ["請確認必填欄位是否已完整填寫。"],
        field_errors,
        open_modal,
    )


@system_bp.route("/customers", methods=["POST"])
@login_required
def create_customer():
    customer = Customer()
    set_customer_from_form(customer)
    field_errors = {}
    if not customer.name:
        field_errors["name"] = "請輸入客戶名稱"
    if not customer.category_id:
        field_errors["category_id"] = "請選擇客戶分類"
    if field_errors:
        return required_error_response("customers", field_errors, "createCustomerModal")
    customer.customer_code = next_customer_code()
    db.session.add(customer)
    if not commit_or_flash("客戶已新增。", "客戶資料儲存失敗。"):
        return required_error_response("customers", {"name": "客戶資料儲存失敗。"}, "createCustomerModal")
    return redirect_system("customers")


@system_bp.route("/customers/<int:customer_id>", methods=["POST"])
@login_required
def update_customer(customer_id):
    customer = Customer.query.get_or_404(customer_id)
    set_customer_from_form(customer)
    field_errors = {}
    if not customer.name:
        field_errors["name"] = "請輸入客戶名稱"
    if not customer.category_id:
        field_errors["category_id"] = "請選擇客戶分類"
    if field_errors:
        return required_error_response("customers", field_errors, f"editCustomer{customer.id}")
    if not commit_or_flash("客戶已更新。", "客戶資料儲存失敗。"):
        return required_error_response("customers", {"name": "客戶資料儲存失敗。"}, f"editCustomer{customer.id}")
    return redirect_system("customers")


@system_bp.route("/customers/<int:customer_id>/delete", methods=["POST"])
@login_required
def delete_customer(customer_id):
    customer = Customer.query.get_or_404(customer_id)
    db.session.delete(customer)
    commit_or_flash("客戶已刪除。", "此客戶已有關聯資料，無法刪除。")
    return redirect_system("customers")


@system_bp.route("/employees", methods=["POST"])
@login_required
def create_employee():
    employee = Employee(employee_code=next_employee_code(), status="在職", is_active=True)
    set_employee_from_form(employee)
    field_errors = {}
    if not employee.name:
        field_errors["name"] = "請輸入員工姓名"
    if not employee.login_username:
        field_errors["login_username"] = "請輸入登入帳號"
    if not employee.role_id:
        field_errors["role_id"] = "請選擇角色"
    if not request.form.get("login_password"):
        field_errors["login_password"] = "請輸入登入密碼"
    if field_errors:
        return required_error_response("employees", field_errors, "createEmployeeModal")
    db.session.add(employee)
    if not commit_or_flash("員工已新增。", "員工資料儲存失敗，請確認登入帳號或 Email 是否重複。"):
        return required_error_response("employees", {"login_username": "登入帳號或 Email 已存在。"}, "createEmployeeModal")
    return redirect_system("employees")


@system_bp.route("/employees/<int:employee_id>", methods=["POST"])
@login_required
def update_employee(employee_id):
    employee = Employee.query.get_or_404(employee_id)
    set_employee_from_form(employee)
    field_errors = {}
    if not employee.name:
        field_errors["name"] = "請輸入員工姓名"
    if not employee.login_username:
        field_errors["login_username"] = "請輸入登入帳號"
    if not employee.role_id:
        field_errors["role_id"] = "請選擇角色"
    if field_errors:
        return required_error_response("employees", field_errors, f"editEmployee{employee.id}")
    if not commit_or_flash("員工已更新。", "員工資料儲存失敗，請確認登入帳號或 Email 是否重複。"):
        return required_error_response("employees", {"login_username": "登入帳號或 Email 已存在。"}, f"editEmployee{employee.id}")
    return redirect_system("employees")


@system_bp.route("/employees/<int:employee_id>/delete", methods=["POST"])
@login_required
def delete_employee(employee_id):
    employee = Employee.query.get_or_404(employee_id)
    employee.is_active = False
    employee.status = "停用"
    if commit_or_flash("員工已停用。", "系統儲存失敗，請檢查資料是否完整。"):
        return redirect_system("employees")
    return redirect_system("employees")


@system_bp.route("/employees/reserved/<feature>")
@login_required
def employee_reserved(feature):
    feature_titles = {
        "accounts": "帳號管理",
        "permissions": "權限管理",
        "applications": "員工申請審核",
        "attendance": "出勤打卡",
        "leave": "請假管理",
        "schedule": "排班排休",
    }
    title = feature_titles.get(feature)
    if not title:
        return redirect_system("employees")
    return render_template("system/reserved.html", title=title)


@system_bp.route("/suppliers", methods=["POST"])
@login_required
def create_supplier():
    supplier = Supplier()
    set_supplier_from_form(supplier)
    if not supplier.name:
        return required_error_response("suppliers", {"name": "請輸入廠商名稱"}, "createSupplierModal")
    db.session.add(supplier)
    if not commit_or_flash("廠商已新增。", "廠商名稱不可重複。"):
        return required_error_response("suppliers", {"name": "廠商名稱不可重複。"}, "createSupplierModal")
    return redirect_system("suppliers")


@system_bp.route("/suppliers/<int:supplier_id>", methods=["POST"])
@login_required
def update_supplier(supplier_id):
    supplier = Supplier.query.get_or_404(supplier_id)
    set_supplier_from_form(supplier)
    if not supplier.name:
        return required_error_response("suppliers", {"name": "請輸入廠商名稱"}, f"editSupplier{supplier.id}")
    if not commit_or_flash("廠商已更新。", "廠商名稱不可重複。"):
        return required_error_response("suppliers", {"name": "廠商名稱不可重複。"}, f"editSupplier{supplier.id}")
    return redirect_system("suppliers")


@system_bp.route("/suppliers/<int:supplier_id>/delete", methods=["POST"])
@login_required
def delete_supplier(supplier_id):
    supplier = Supplier.query.get_or_404(supplier_id)
    if Product.query.filter_by(supplier_id=supplier.id).first():
        flash("此廠商已有商品使用，無法刪除。", "danger")
        return redirect_system("suppliers")
    db.session.delete(supplier)
    commit_or_flash("廠商已刪除。", "廠商資料刪除失敗。")
    return redirect_system("suppliers")


def create_master(model, label):
    name = clean(request.form.get("name"))
    if not name:
        return required_error_response("basic", {"name": f"請輸入{label}名稱"})
    db.session.add(model(name=name))
    if not commit_or_flash(f"{label}已新增。", "此名稱已存在。"):
        return required_error_response("basic", {"name": "此名稱已存在。"})
    return redirect_system("basic")


def update_master(model, item_id, label):
    item = model.query.get_or_404(item_id)
    name = clean(request.form.get("name"))
    if not name:
        return required_error_response("basic", {"name": f"請輸入{label}名稱"})
    item.name = name
    item.is_active = request.form.get("is_active", "0") == "1"
    if model is EmployeeRole:
        for employee in item.employees:
            employee.role = item.name
    if not commit_or_flash(f"{label}已更新。", "此名稱已存在。"):
        return required_error_response("basic", {"name": "此名稱已存在。"})
    return redirect_system("basic")


def deactivate_master(model, item_id, label):
    item = model.query.get_or_404(item_id)
    item.is_active = False
    commit_or_flash(f"{label}已停用。", "系統儲存失敗，請檢查資料是否完整。")


@system_bp.route("/customer-categories", methods=["POST"])
@login_required
def create_customer_category():
    return create_master(CustomerCategory, "客戶分類")


@system_bp.route("/customer-categories/<int:category_id>", methods=["POST"])
@login_required
def update_customer_category(category_id):
    return update_master(CustomerCategory, category_id, "客戶分類")


@system_bp.route("/customer-categories/<int:category_id>/deactivate", methods=["POST"])
@login_required
def deactivate_customer_category(category_id):
    deactivate_master(CustomerCategory, category_id, "客戶分類")
    return redirect_system("basic")


@system_bp.route("/employee-roles", methods=["POST"])
@login_required
def create_employee_role():
    return create_master(EmployeeRole, "員工角色")


@system_bp.route("/employee-roles/<int:role_id>", methods=["POST"])
@login_required
def update_employee_role(role_id):
    return update_master(EmployeeRole, role_id, "員工角色")


@system_bp.route("/employee-roles/<int:role_id>/deactivate", methods=["POST"])
@login_required
def deactivate_employee_role(role_id):
    deactivate_master(EmployeeRole, role_id, "員工角色")
    return redirect_system("basic")


@system_bp.route("/order-sources", methods=["POST"])
@login_required
def create_order_source():
    return create_master(OrderSource, "訂單客源")


@system_bp.route("/order-sources/<int:source_id>", methods=["POST"])
@login_required
def update_order_source(source_id):
    return update_master(OrderSource, source_id, "訂單客源")


@system_bp.route("/order-sources/<int:source_id>/deactivate", methods=["POST"])
@login_required
def deactivate_order_source(source_id):
    deactivate_master(OrderSource, source_id, "訂單客源")
    return redirect_system("basic")


@system_bp.route("/ai-settings", methods=["POST"])
@login_required
def save_ai_settings():
    if not admin_required():
        flash("僅管理員可修改 AI 設定。", "danger")
        return redirect_system("ai")
    api_key = clean(request.form.get("gemini_api_key"))
    if not api_key:
        flash("請輸入 Google AI API Key。", "danger")
        return redirect_system("ai")
    try:
        update_ai_api_key(api_key)
        flash("AI API Key 已儲存，已立即生效。", "success")
    except Exception:
        db.session.rollback()
        current_app.logger.exception("AI settings save failed")
        flash("AI 設定儲存失敗，請查看後端 log。", "danger")
    return redirect_system("ai")


@system_bp.route("/ai-settings/test", methods=["POST"])
@login_required
def test_ai_settings():
    if not admin_required():
        flash("僅管理員可測試 AI 設定。", "danger")
        return redirect_system("ai")
    api_key = clean(request.form.get("gemini_api_key"))
    try:
        result = test_gemini_connection(api_key or None)
        if result["ok"]:
            flash("AI 連線測試成功。", "success")
        else:
            flash(f"AI 連線測試失敗：{result['message']}", "danger")
    except Exception:
        db.session.rollback()
        current_app.logger.exception("AI settings test failed")
        flash("AI 連線測試失敗，請查看後端 log。", "danger")
    return redirect_system("ai")
