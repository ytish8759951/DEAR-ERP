from datetime import datetime

from flask import Blueprint, current_app, flash, redirect, render_template, request, url_for

from config import Config
from decorators import login_required
from extensions import db
from models import Customer, CustomerCategory, Order, Return, ReturnItem
from pagination import get_page_args
from routes.orders import order_amount_breakdown


customers_bp = Blueprint("customers", __name__, url_prefix="/customers")


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


def next_customer_code():
    latest = (
        Customer.query.with_entities(Customer.customer_code)
        .filter(Customer.customer_code.like("D%"))
        .order_by(Customer.customer_code.desc())
        .first()
    )
    sequence = 0
    if latest and latest.customer_code and latest.customer_code[1:].isdigit():
        sequence = int(latest.customer_code[1:])
    return f"D{sequence + 1:07d}"


def backfill_customer_codes():
    changed = False
    for customer in Customer.query.filter((Customer.customer_code.is_(None)) | (Customer.customer_code == "")).order_by(Customer.id):
        customer.customer_code = next_customer_code()
        changed = True
    if changed:
        db.session.commit()


def active_categories():
    return CustomerCategory.query.filter_by(is_active=True).order_by(CustomerCategory.name).all()


def category_by_name(name):
    return CustomerCategory.query.filter_by(name=name).first()


def customer_filters():
    return {
        "customer_code": clean(request.args.get("customer_code")),
        "name": clean(request.args.get("name")),
        "phone": clean(request.args.get("phone")),
        "line": clean(request.args.get("line")),
        "category_id": clean(request.args.get("category_id")),
        "wholesale_paid": clean(request.args.get("wholesale_paid")),
        "status": clean(request.args.get("status")),
    }


def apply_customer_filters(query, filters):
    if filters["customer_code"]:
        query = query.filter(Customer.customer_code.like(f"%{filters['customer_code']}%"))
    if filters["name"]:
        query = query.filter(Customer.name.like(f"%{filters['name']}%"))
    if filters["phone"]:
        query = query.filter(Customer.phone.like(f"%{filters['phone']}%"))
    if filters["line"]:
        query = query.filter(Customer.line.like(f"%{filters['line']}%"))
    if filters["category_id"]:
        try:
            query = query.filter(Customer.category_id == int(filters["category_id"]))
        except ValueError:
            pass
    if filters["wholesale_paid"] in {"1", "0"}:
        query = query.filter(Customer.wholesale_paid.is_(filters["wholesale_paid"] == "1"))
    if filters["status"] == "active":
        query = query.filter(Customer.is_active.is_(True))
    elif filters["status"] == "inactive":
        query = query.filter(Customer.is_active.is_(False))
    return query


def sync_customer(customer):
    customer.name = clean(request.form.get("name"))
    customer.phone = clean(request.form.get("phone"))
    customer.line = clean(request.form.get("line"))
    customer.address = clean(request.form.get("address"))
    customer.note = clean(request.form.get("note"))
    customer.wholesale_paid = request.form.get("wholesale_paid") == "1"
    customer.wholesale_paid_date = parse_date(request.form.get("wholesale_paid_date"))
    customer.is_active = request.form.get("is_active", "1") == "1"

    category_id = request.form.get("category_id")
    customer.category_id = int(category_id) if category_id and category_id.isdigit() else None
    wholesale_category = category_by_name("批發客")
    normal_category = category_by_name("一般客")
    field_errors = {}
    if not customer.name:
        field_errors["name"] = "請輸入客戶名稱"
    if not customer.category_id:
        field_errors["category_id"] = "請選擇客戶分類"
    if wholesale_category and customer.category_id == wholesale_category.id and not customer.wholesale_paid:
        customer.category_id = normal_category.id if normal_category else None
        field_errors["category_id"] = "請先勾選已繳批發金，才能設定為批發客"
    if not customer.wholesale_paid and wholesale_category and customer.category_id == wholesale_category.id:
        customer.category_id = normal_category.id if normal_category else None
    return not field_errors, field_errors


def render_form(customer, action, title, status_code=200, form_error=None, field_errors=None):
    field_errors = field_errors or {}
    return render_template(
        "customers/form.html",
        customer=customer,
        action=action,
        title=title,
        categories=active_categories(),
        wholesale_category=category_by_name("批發客"),
        normal_category=category_by_name("一般客"),
        form_error=form_error,
        errors=["請確認必填欄位是否已完整填寫。"] if field_errors else [],
        field_errors=field_errors,
    ), status_code


def has_unfinished_orders(customer):
    return (
        Order.query.filter(
            Order.customer_id == customer.id,
            ~Order.status.in_(["已取消", "已退貨", "全部退貨"]),
        ).first()
        is not None
    )


@customers_bp.route("/")
@login_required
def index():
    backfill_customer_codes()
    filters = customer_filters()
    page, per_page = get_page_args(request, Config.DEFAULT_PAGE_SIZE, Config.PAGE_SIZE_OPTIONS)
    query = apply_customer_filters(Customer.query, filters).order_by(Customer.created_at.desc(), Customer.id.desc())
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)
    return render_template(
        "customers/index.html",
        customers=pagination.items,
        unfinished_order_map={customer.id: has_unfinished_orders(customer) for customer in pagination.items},
        pagination=pagination,
        filters=filters,
        categories=CustomerCategory.query.order_by(CustomerCategory.name).all(),
        page_size_options=Config.PAGE_SIZE_OPTIONS,
    )


@customers_bp.route("/new", methods=["GET", "POST"])
@login_required
def create():
    customer = Customer(customer_code=next_customer_code(), is_active=True)
    if request.method == "POST":
        try:
            customer.customer_code = next_customer_code()
            is_valid, field_errors = sync_customer(customer)
            if is_valid:
                db.session.add(customer)
                db.session.commit()
                flash("客戶已新增。", "success")
                return redirect(url_for("customers.detail", customer_id=customer.id))
            db.session.rollback()
            return render_form(customer, url_for("customers.create"), "新增客戶", 200, field_errors.get("category_id"), field_errors)
        except Exception:
            db.session.rollback()
            current_app.logger.exception("Customer create failed")
            return render_form(
                customer,
                url_for("customers.create"),
                "新增客戶",
                200,
                None,
                {"form": "系統儲存失敗，請檢查資料是否完整。"},
            )
    return render_form(customer, url_for("customers.create"), "新增客戶")


@customers_bp.route("/<int:customer_id>")
@login_required
def detail(customer_id):
    customer = Customer.query.get_or_404(customer_id)
    orders_page, orders_per_page = get_page_args(request, Config.DEFAULT_PAGE_SIZE, Config.PAGE_SIZE_OPTIONS)
    returns_page = request.args.get("returns_page", "1")
    try:
        returns_page = max(int(returns_page), 1)
    except ValueError:
        returns_page = 1
    orders_pagination = (
        Order.query.filter_by(customer_id=customer.id)
        .order_by(Order.order_date.desc(), Order.id.desc())
        .paginate(page=orders_page, per_page=orders_per_page, error_out=False)
    )
    returns_pagination = (
        ReturnItem.query.join(ReturnItem.return_record)
        .join(Return.order)
        .filter(Order.customer_id == customer.id)
        .order_by(Return.created_at.desc(), ReturnItem.id.desc())
        .paginate(page=returns_page, per_page=orders_per_page, error_out=False)
    )
    return render_template(
        "customers/detail.html",
        customer=customer,
        orders=orders_pagination.items,
        returns=returns_pagination.items,
        orders_pagination=orders_pagination,
        returns_pagination=returns_pagination,
        order_amounts={order.id: order_amount_breakdown(order) for order in orders_pagination.items},
        has_unfinished_orders=has_unfinished_orders(customer),
        page_size_options=Config.PAGE_SIZE_OPTIONS,
    )


@customers_bp.route("/<int:customer_id>/edit", methods=["GET", "POST"])
@login_required
def edit(customer_id):
    customer = Customer.query.get_or_404(customer_id)
    if request.method == "POST":
        try:
            is_valid, field_errors = sync_customer(customer)
            if is_valid:
                db.session.commit()
                flash("客戶已更新。", "success")
                return redirect(url_for("customers.detail", customer_id=customer.id))
            db.session.rollback()
            return render_form(customer, url_for("customers.edit", customer_id=customer.id), "編輯客戶", 200, field_errors.get("category_id"), field_errors)
        except Exception:
            db.session.rollback()
            current_app.logger.exception("Customer update failed")
            return render_form(
                customer,
                url_for("customers.edit", customer_id=customer.id),
                "編輯客戶",
                200,
                None,
                {"form": "系統儲存失敗，請檢查資料是否完整。"},
            )
    return render_form(customer, url_for("customers.edit", customer_id=customer.id), "編輯客戶")


@customers_bp.route("/<int:customer_id>/deactivate", methods=["POST"])
@login_required
def deactivate(customer_id):
    customer = Customer.query.get_or_404(customer_id)
    try:
        customer.is_active = False
        db.session.commit()
        flash("客戶已停用。", "success")
    except Exception:
        db.session.rollback()
        current_app.logger.exception("Customer deactivate failed")
        flash("系統儲存失敗，請檢查資料是否完整。", "danger")
    return redirect(url_for("customers.index"))


@customers_bp.route("/<int:customer_id>/activate", methods=["POST"])
@login_required
def activate(customer_id):
    customer = Customer.query.get_or_404(customer_id)
    try:
        customer.is_active = True
        db.session.commit()
        flash("客戶已啟用。", "success")
    except Exception:
        db.session.rollback()
        current_app.logger.exception("Customer activate failed")
        flash("系統儲存失敗，請檢查資料是否完整。", "danger")
    return redirect(url_for("customers.index"))
