from datetime import datetime
from decimal import Decimal, InvalidOperation

from flask import Blueprint, current_app, flash, jsonify, redirect, render_template, request, url_for
from sqlalchemy import func, or_

from config import Config
from decorators import login_required
from extensions import db
from models import (
    Customer,
    DefectiveInventory,
    InventoryMovement,
    Order,
    OrderItem,
    OrderSource,
    Product,
    ProductVariant,
    Return,
    ReturnItem,
    utc_now,
)
from pagination import get_page_args


orders_bp = Blueprint("orders", __name__, url_prefix="/orders")
SAVE_FAILED_ERROR = "系統儲存失敗，請檢查資料是否完整。"

ORDER_STATUSES = ["待付款", "已付款", "預購中", "待出貨", "已完成", "部分退貨", "已退貨", "已取消"]
MANUAL_ORDER_STATUSES = {"待付款", "已付款"}
RETURN_ORDER_STATUSES = {"部分退貨", "已退貨"}
RETURN_TYPES = ["正常退貨", "瑕疵退貨"]
FULFILLMENT_STATUSES = {"預購中", "待出貨"}


def clean(value):
    return (value or "").strip()


def parse_date(value, default=None):
    value = clean(value)
    if not value:
        return default
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return default


def parse_money(name):
    try:
        value = Decimal(clean(request.form.get(name)) or "0")
    except InvalidOperation:
        return Decimal("0")
    return value if value >= 0 else Decimal("0")


def parse_optional_int(value):
    try:
        return int(value or 0) or None
    except (TypeError, ValueError):
        return None


def generate_order_no(order_date):
    prefix = order_date.strftime("%Y%m%d")
    latest = (
        Order.query.with_entities(Order.order_no)
        .filter(Order.order_no.like(f"{prefix}%"))
        .order_by(Order.order_no.desc())
        .first()
    )
    sequence = 0
    if latest and latest.order_no and latest.order_no[len(prefix):].isdigit():
        sequence = int(latest.order_no[len(prefix):])
    return f"{prefix}{sequence + 1:04d}"


def generate_return_no():
    today = utc_now().date()
    prefix = f"R{today.strftime('%Y%m%d')}"
    latest = (
        Return.query.with_entities(Return.return_no)
        .filter(Return.return_no.like(f"{prefix}%"))
        .order_by(Return.return_no.desc())
        .first()
    )
    sequence = 0
    if latest and latest.return_no and latest.return_no[len(prefix):].isdigit():
        sequence = int(latest.return_no[len(prefix):])
    return f"{prefix}{sequence + 1:04d}"


def returned_quantity(order_item_id):
    return (
        db.session.query(func.coalesce(func.sum(ReturnItem.quantity), 0))
        .filter(ReturnItem.order_item_id == order_item_id)
        .scalar()
        or 0
    )


def order_return_summary(order):
    summary = {
        item.id: {
            "normal": 0,
            "defective": 0,
            "returned": 0,
            "remaining": item.quantity,
            "actual": item.quantity,
            "normal_amount": Decimal("0"),
            "defective_amount": Decimal("0"),
            "returned_amount": Decimal("0"),
            "actual_amount": Decimal(item.quantity) * Decimal(item.unit_price or 0),
        }
        for item in order.items
    }
    def return_created_sort_key(record):
        if not record.created_at:
            return datetime.min
        return record.created_at.replace(tzinfo=None)

    for return_record in sorted(order.returns, key=return_created_sort_key):
        for return_item in return_record.items:
            item_summary = summary.get(return_item.order_item_id)
            if not item_summary:
                continue
            if return_record.return_type == "正常退貨":
                item_summary["normal"] += return_item.quantity
                item_summary["normal_amount"] += Decimal(return_item.quantity) * Decimal(return_item.order_item.unit_price or 0)
            elif return_record.return_type == "瑕疵退貨":
                item_summary["defective"] += return_item.quantity
                item_summary["defective_amount"] += Decimal(return_item.quantity) * Decimal(return_item.order_item.unit_price or 0)
            item_summary["returned"] += return_item.quantity

    for item in order.items:
        item_summary = summary[item.id]
        item_summary["remaining"] = max(0, item.quantity - item_summary["returned"])
        item_summary["actual"] = max(0, item.quantity - item_summary["returned"])
        item_summary["returned_amount"] = item_summary["normal_amount"] + item_summary["defective_amount"]
        item_summary["actual_amount"] = Decimal(item_summary["actual"]) * Decimal(item.unit_price or 0)
    return summary


def order_return_totals(order):
    summary = order_return_summary(order)
    purchased = sum(item.quantity for item in order.items)
    returned = sum(item_summary["returned"] for item_summary in summary.values())
    remaining = max(0, purchased - returned)
    return purchased, returned, remaining


def order_actual_subtotal(item, return_summary):
    item_summary = return_summary.get(item.id, {})
    return item_summary.get("actual_amount", Decimal(item.quantity) * Decimal(item.unit_price or 0))


def order_original_total(order):
    return sum(Decimal(item.quantity) * Decimal(item.unit_price or 0) for item in order.items)


def order_return_amount(order):
    summary = order_return_summary(order)
    return sum(item_summary["returned_amount"] for item_summary in summary.values())


def order_amount_breakdown(order):
    original_total = order_original_total(order)
    return_amount = abs(order_return_amount(order))
    merchandise_total = max(Decimal("0"), original_total - return_amount)
    if merchandise_total <= 0 and order.items:
        order_total = Decimal("0")
    else:
        order_total = merchandise_total - Decimal(order.discount_amount or 0) + Decimal(order.shipping_fee or 0)
    return {
        "original_total": original_total,
        "return_amount": return_amount,
        "merchandise_total": merchandise_total,
        "discount_amount": Decimal(order.discount_amount or 0),
        "shipping_fee": Decimal(order.shipping_fee or 0),
        "order_total": order_total,
    }


def recalculate_order_amounts(order):
    breakdown = order_amount_breakdown(order)
    order.total_amount = breakdown["merchandise_total"]
    order.receivable_amount = breakdown["order_total"]


def recalculate_return_status(order):
    if order.status == "已取消":
        return
    purchased, returned, _remaining = order_return_totals(order)
    if purchased <= 0 or returned <= 0:
        return
    order.status = "已退貨" if returned >= purchased else "部分退貨"


def recalculate_fulfillment_status(order):
    if order.status in {"已取消", "部分退貨", "已退貨", "已完成"}:
        return
    total_ordered = sum(item.quantity or 0 for item in order.items)
    total_allocated = sum(item.allocated_quantity or 0 for item in order.items)
    total_backorder = sum(item.backorder_quantity or 0 for item in order.items)
    if total_ordered <= 0:
        return
    if total_backorder > 0 and total_allocated <= 0:
        order.status = "預購中"
    elif total_backorder > 0:
        order.status = "預購中"
    elif total_backorder <= 0 and order.status in {"已付款", "預購中", "部分到貨", "已出貨"}:
        order.status = "待出貨"
    elif total_backorder <= 0 and order.status in FULFILLMENT_STATUSES:
        order.status = "待出貨"


def can_edit_order(order):
    return order.status not in {"已取消", "部分退貨", "已退貨", "已完成"}


def has_backorder_items(order):
    return any((item.backorder_quantity or 0) > 0 for item in order.items)


def can_complete_order(order):
    return order.status == "待出貨" and not has_backorder_items(order)


def order_filters():
    return {
        "order_no": clean(request.args.get("order_no")),
        "customer_code": clean(request.args.get("customer_code")),
        "customer_name": clean(request.args.get("customer_name")),
        "order_source_id": clean(request.args.get("order_source_id")),
        "status": clean(request.args.get("status")),
        "date_start": clean(request.args.get("date_start")),
        "date_end": clean(request.args.get("date_end")),
    }


def apply_order_filters(query, filters):
    if filters["order_no"]:
        query = query.filter(Order.order_no.like(f"%{filters['order_no']}%"))
    if filters["customer_code"] or filters["customer_name"]:
        query = query.join(Order.customer)
    if filters["customer_code"]:
        query = query.filter(Customer.customer_code.like(f"%{filters['customer_code']}%"))
    if filters["customer_name"]:
        query = query.filter(Customer.name.like(f"%{filters['customer_name']}%"))
    if filters["order_source_id"]:
        query = query.filter(Order.order_source_id == int(filters["order_source_id"]))
    if filters["status"]:
        query = query.filter(Order.status == filters["status"])
    date_start = parse_date(filters["date_start"])
    date_end = parse_date(filters["date_end"])
    if date_start:
        query = query.filter(Order.order_date >= date_start)
    if date_end:
        query = query.filter(Order.order_date <= date_end)
    return query


def customer_options():
    customer_code = clean(request.args.get("customer_code"))
    customer_name = clean(request.args.get("customer_name"))
    query = Customer.query.filter(Customer.is_active.is_(True))
    if customer_code:
        query = query.filter(Customer.customer_code.like(f"%{customer_code}%"))
    if customer_name:
        query = query.filter(Customer.name.like(f"%{customer_name}%"))
    return query.order_by(Customer.customer_code).limit(100).all()


def product_variant_options():
    product_sku = clean(request.args.get("product_sku"))
    product_name = clean(request.args.get("product_name"))
    query = ProductVariant.query.join(ProductVariant.product)
    if product_sku:
        query = query.filter(Product.sku.like(f"%{product_sku}%"))
    if product_name:
        query = query.filter(Product.name.like(f"%{product_name}%"))
    return query.order_by(Product.sku, ProductVariant.id).limit(100).all()


@orders_bp.route("/customers/search")
@login_required
def search_customers():
    keyword = clean(request.args.get("q"))
    query = Customer.query.filter(Customer.is_active.is_(True))
    if keyword:
        like = f"%{keyword}%"
        query = query.filter(
            or_(
                Customer.customer_code.like(like),
                Customer.name.like(like),
                Customer.phone.like(like),
            )
        )
    results = query.order_by(Customer.customer_code).limit(20).all()
    return jsonify(
        [
            {
                "id": customer.id,
                "customer_code": customer.customer_code or "",
                "name": customer.name,
                "phone": customer.phone or "",
                "wholesale_paid": bool(customer.wholesale_paid),
                "label": f"{customer.customer_code or '-'} {customer.name}",
            }
            for customer in results
        ]
    )


@orders_bp.route("/products/search")
@login_required
def search_products():
    keyword = clean(request.args.get("q"))
    query = ProductVariant.query.join(ProductVariant.product)
    if keyword:
        like = f"%{keyword}%"
        query = query.filter(or_(Product.sku.like(like), Product.name.like(like)))
    variants = query.order_by(Product.sku, ProductVariant.id).limit(20).all()
    return jsonify(
        [
            {
                "variant_id": variant.id,
                "product_id": variant.product_id,
                "sku": variant.product.sku,
                "name": variant.product.name,
                "color": variant.color.name if variant.color else "",
                "size": variant.size.name if variant.size else "",
                "stock": variant.stock,
                "price": float(variant.product.price or 0),
                "supply_mode": variant.product.supply_mode or "一般商品",
                "image_url": url_for("static", filename=variant.product.image_path) if variant.product.image_path else "",
                "label": f"{variant.product.sku} {variant.product.name} {variant.spec_name}",
            }
            for variant in variants
        ]
    )


def active_order_sources():
    return OrderSource.query.filter_by(is_active=True).order_by(OrderSource.name).all()


def wholesale_order_source():
    return OrderSource.query.filter_by(name="批發客", is_active=True).first()


def validate_customer_order_source(order):
    source = OrderSource.query.get(order.order_source_id) if order.order_source_id else None
    customer = Customer.query.get(order.customer_id) if order.customer_id else None
    if source and source.name == "批發客" and customer and not customer.wholesale_paid:
        flash("此客戶尚未繳交批發資格費 2000 元，不能選擇批發客。", "danger")
        return False
    return True


def selected_items_from_form():
    items = []
    item_errors = []
    for variant_id in request.form.getlist("variant_id"):
        try:
            variant_id_int = int(variant_id)
            quantity = int(request.form.get(f"quantity_{variant_id}") or 0)
            unit_price = Decimal(clean(request.form.get(f"unit_price_{variant_id}")) or "0")
        except (ValueError, InvalidOperation):
            item_errors.append("商品數量或單價格式錯誤。")
            continue
        if quantity > 0 and unit_price >= 0:
            items.append((variant_id_int, quantity, unit_price))
        else:
            item_errors.append("商品數量必須大於 0，商品單價必須大於等於 0。")
    return items, item_errors


def existing_order_quantities(order):
    quantities = {}
    if not order or order.status == "已取消":
        return quantities
    for item in order.items:
        quantities[item.product_variant_id] = quantities.get(item.product_variant_id, 0) + item.quantity
    return quantities


def validate_stock(selected_items, old_quantities=None):
    old_quantities = old_quantities or {}
    errors = []
    variants = {
        variant.id: variant
        for variant in ProductVariant.query.filter(ProductVariant.id.in_([item[0] for item in selected_items])).all()
    }
    for variant_id, quantity, _unit_price in selected_items:
        variant = variants.get(variant_id)
        if not variant:
            errors.append("商品資料不存在。")
            continue
        available_quantity = (variant.stock or 0) + old_quantities.get(variant_id, 0)
        if variant.product and variant.product.supply_mode == "出清商品" and quantity > available_quantity:
            errors.append("此商品為出清商品，庫存不足，請修改數量或取消商品後再儲存。")
    return errors, variants


def apply_items(order, selected_items, variants, restore_existing=False):
    if restore_existing:
        for item in order.items:
            if item.product_variant:
                item.product_variant.stock += item.allocated_quantity or 0
        order.items = []

    total = Decimal("0")
    for variant_id, quantity, unit_price in selected_items:
        variant = variants[variant_id]
        allocated_quantity = min(quantity, max(variant.stock, 0))
        backorder_quantity = max(quantity - allocated_quantity, 0)
        subtotal = unit_price * quantity
        variant.stock -= allocated_quantity
        order.items.append(
            OrderItem(
                product_id=variant.product_id,
                product_variant_id=variant.id,
                quantity=quantity,
                allocated_quantity=allocated_quantity,
                backorder_quantity=backorder_quantity,
                unit_price=unit_price,
                subtotal=subtotal,
            )
        )
        total += subtotal
    order.total_amount = total
    order.receivable_amount = total - (order.discount_amount or 0) + (order.shipping_fee or 0)
    recalculate_fulfillment_status(order)


def sync_order_header(order, is_create=False):
    order_date = parse_date(request.form.get("order_date"), default=utc_now().date())
    if is_create:
        order.order_no = generate_order_no(order_date)
    order.order_date = order_date
    order.customer_id = parse_optional_int(request.form.get("customer_id"))
    order.order_source_id = parse_optional_int(request.form.get("order_source_id"))
    status = clean(request.form.get("status"))
    if status in MANUAL_ORDER_STATUSES and order.status not in {"部分退貨", "已退貨", "已取消", "已完成"}:
        order.status = status
    elif is_create and not order.status:
        order.status = "待付款"
    order.discount_amount = parse_money("discount_amount")
    order.shipping_fee = parse_money("shipping_fee")
    order.note = clean(request.form.get("note"))


def wholesale_warning(customer, order_source):
    if order_source and order_source.name == "批發客" and customer and not customer.wholesale_paid:
        return "此客戶尚未繳交批發資格費 2000 元"
    return None


def order_wholesale_warning(order):
    source = OrderSource.query.get(order.order_source_id) if order.order_source_id else None
    customer = Customer.query.get(order.customer_id) if order.customer_id else None
    return wholesale_warning(customer, source)


def render_order_form(order, action, is_create=False, status_code=200, errors=None, field_errors=None):
    selected_customer = order.customer if order.customer_id else None
    selected_source = OrderSource.query.get(order.order_source_id) if order.order_source_id else None
    return (
        render_template(
            "orders/form.html",
            order=order,
            action=action,
            is_create=is_create,
            statuses=ORDER_STATUSES,
            order_sources=active_order_sources(),
            selected_customer=selected_customer,
            wholesale_source=wholesale_order_source(),
            wholesale_warning=wholesale_warning(selected_customer, selected_source),
            errors=errors or [],
            field_errors=field_errors or {},
        ),
        status_code,
    )


def validate_order_required(order, selected_items, item_errors):
    errors = []
    field_errors = {}
    if not order.customer_id:
        field_errors["customer_id"] = "請選擇客戶"
    if not order.order_source_id:
        field_errors["order_source_id"] = "請選擇客源"
    if not clean(request.form.get("status")):
        field_errors["status"] = "請選擇訂單狀態"
    if item_errors:
        field_errors["order_items"] = item_errors[0]
    elif not selected_items:
        field_errors["order_items"] = "請至少加入一個商品"
    if field_errors:
        errors.append("請確認必填欄位是否已完整填寫。")
    return errors, field_errors


@orders_bp.route("/")
@login_required
def index():
    filters = order_filters()
    page, per_page = get_page_args(request, Config.DEFAULT_PAGE_SIZE, Config.PAGE_SIZE_OPTIONS)
    query = apply_order_filters(Order.query, filters).order_by(Order.order_date.desc(), Order.order_no.desc())
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)
    return render_template(
        "orders/index.html",
        orders=pagination.items,
        return_summaries={order.id: order_return_summary(order) for order in pagination.items},
        amount_breakdowns={order.id: order_amount_breakdown(order) for order in pagination.items},
        can_complete_order=can_complete_order,
        pagination=pagination,
        filters=filters,
        order_sources=active_order_sources(),
        statuses=ORDER_STATUSES,
        page_size_options=Config.PAGE_SIZE_OPTIONS,
    )


@orders_bp.route("/new", methods=["GET", "POST"])
@login_required
def create():
    order = Order(order_date=utc_now().date(), status="待付款")
    if request.method == "POST":
        try:
            sync_order_header(order, is_create=True)
            selected_items, item_errors = selected_items_from_form()
            errors, field_errors = validate_order_required(order, selected_items, item_errors)
            if errors:
                db.session.rollback()
                return render_order_form(order, url_for("orders.create"), True, 200, errors, field_errors)
            customer = Customer.query.get(order.customer_id)
            if not customer or not customer.is_active:
                db.session.rollback()
                return render_order_form(
                    order,
                    url_for("orders.create"),
                    True,
                    200,
                    ["請確認必填欄位是否已完整填寫。"],
                    {"customer_id": "此客戶已停用，無法新增訂單。"},
                )
            if not validate_customer_order_source(order):
                db.session.rollback()
                return render_order_form(order, url_for("orders.create"), True, 200)

            errors, variants = validate_stock(selected_items)
            if errors:
                db.session.rollback()
                for error in errors:
                    flash(error, "danger")
                return render_order_form(order, url_for("orders.create"), True, 200)

            db.session.add(order)
            apply_items(order, selected_items, variants)
            warning = order_wholesale_warning(order)
            if warning:
                flash(warning, "warning")
            db.session.commit()
            flash("訂單已新增。", "success")
            return redirect(url_for("orders.detail", order_id=order.id))
        except Exception:
            db.session.rollback()
            current_app.logger.exception("Order create failed")
            return render_order_form(
                order,
                url_for("orders.create"),
                True,
                200,
                [SAVE_FAILED_ERROR],
                {"form": SAVE_FAILED_ERROR},
            )

    return render_order_form(order, url_for("orders.create"), True)


@orders_bp.route("/<int:order_id>")
@login_required
def detail(order_id):
    order = Order.query.get_or_404(order_id)
    return render_template(
        "orders/detail.html",
        order=order,
        return_summary=order_return_summary(order),
        amount_breakdown=order_amount_breakdown(order),
        can_complete_order=can_complete_order,
    )


@orders_bp.route("/<int:order_id>/edit", methods=["GET", "POST"])
@login_required
def edit(order_id):
    order = Order.query.get_or_404(order_id)
    if request.method == "POST" and not can_edit_order(order):
        flash("已取消或已有退貨紀錄的訂單不可編輯。", "danger")
        return redirect(url_for("orders.detail", order_id=order.id))

    if request.method == "POST":
        try:
            sync_order_header(order)
            selected_items, item_errors = selected_items_from_form()
            errors, field_errors = validate_order_required(order, selected_items, item_errors)
            if errors:
                db.session.rollback()
                return render_order_form(order, url_for("orders.edit", order_id=order.id), False, 200, errors, field_errors)
            if not validate_customer_order_source(order):
                db.session.rollback()
                return render_order_form(order, url_for("orders.edit", order_id=order.id), False, 200)
            old_quantities = existing_order_quantities(order)
            errors, variants = validate_stock(selected_items, old_quantities)
            if errors:
                db.session.rollback()
                for error in errors:
                    flash(error, "danger")
                return render_order_form(order, url_for("orders.edit", order_id=order.id), False, 200)
            apply_items(order, selected_items, variants, restore_existing=True)
            warning = order_wholesale_warning(order)
            if warning:
                flash(warning, "warning")
            db.session.commit()
            flash("訂單已更新。", "success")
            return redirect(url_for("orders.detail", order_id=order.id))
        except Exception:
            db.session.rollback()
            current_app.logger.exception("Order update failed")
            return render_order_form(
                order,
                url_for("orders.edit", order_id=order.id),
                False,
                200,
                [SAVE_FAILED_ERROR],
                {"form": SAVE_FAILED_ERROR},
            )

    return render_order_form(order, url_for("orders.edit", order_id=order.id))


@orders_bp.route("/<int:order_id>/cancel", methods=["POST"])
@login_required
def cancel(order_id):
    order = Order.query.get_or_404(order_id)
    try:
        if order.status == "已完成":
            flash("已完成訂單不可取消。", "danger")
        elif order.status != "已取消":
            summary = order_return_summary(order)
            for item in order.items:
                if item.product_variant:
                    returnable_allocated = min(
                        item.allocated_quantity or 0,
                        summary.get(item.id, {}).get("remaining", item.quantity),
                    )
                    item.product_variant.stock += returnable_allocated
                    item.backorder_quantity = 0
            order.status = "已取消"
            order.canceled_at = utc_now()
            db.session.commit()
            flash("訂單已取消，庫存已回補。", "success")
    except Exception:
        db.session.rollback()
        current_app.logger.exception("Order cancel failed")
        flash(SAVE_FAILED_ERROR, "danger")
    return redirect(url_for("orders.detail", order_id=order.id))


@orders_bp.route("/<int:order_id>/complete", methods=["POST"])
@login_required
def complete(order_id):
    order = Order.query.get_or_404(order_id)
    try:
        if has_backorder_items(order):
            flash("此訂單仍有待貨商品，無法完成。", "danger")
        elif order.status != "待出貨":
            flash("只有待出貨訂單可以完成。", "danger")
        else:
            order.status = "已完成"
            order.completed_at = utc_now()
            db.session.commit()
            flash("訂單已完成。", "success")
    except Exception:
        db.session.rollback()
        current_app.logger.exception("Order complete failed")
        flash(SAVE_FAILED_ERROR, "danger")
    return redirect(url_for("orders.detail", order_id=order.id))


@orders_bp.route("/<int:order_id>/returns", methods=["POST"])
@login_required
def create_return(order_id):
    order = Order.query.get_or_404(order_id)
    if order.status == "已取消":
        flash("已取消訂單不可辦理退貨。", "danger")
        return redirect(request.referrer or url_for("orders.index"))

    return_type = clean(request.form.get("return_type"))
    reason = clean(request.form.get("reason"))
    note = clean(request.form.get("note"))
    try:
        order_item_id = int(request.form.get("order_item_id") or 0)
        quantity = int(request.form.get("quantity") or 0)
    except ValueError:
        order_item_id = 0
        quantity = 0

    if return_type not in RETURN_TYPES:
        flash("請選擇退貨類型。", "danger")
        return redirect(request.referrer or url_for("orders.index"))
    if quantity <= 0:
        flash("退貨數量必須大於 0。", "danger")
        return redirect(request.referrer or url_for("orders.index"))

    order_item = OrderItem.query.filter_by(id=order_item_id, order_id=order.id).first()
    if not order_item or not order_item.product_variant:
        flash("退貨商品資料不存在。", "danger")
        return redirect(request.referrer or url_for("orders.index"))

    already_returned = returned_quantity(order_item.id)
    returnable_quantity = order_item.quantity - already_returned
    if quantity > returnable_quantity:
        flash(f"退貨數量不可超過剩餘可退數量，目前剩餘可退 {returnable_quantity} 件", "danger")
        return redirect(request.referrer or url_for("orders.index"))

    variant = order_item.product_variant
    return_record = Return(
        return_no=generate_return_no(),
        order_id=order.id,
        return_type=return_type,
        reason=reason,
        note=note,
    )
    return_record.items.append(
        ReturnItem(
            order_item_id=order_item.id,
            product_id=order_item.product_id,
            product_variant_id=variant.id,
            quantity=quantity,
            reason=reason,
            note=note,
        )
    )
    db.session.add(return_record)

    if return_type == "正常退貨":
        variant.stock += quantity
        movement_note = f"訂單 {order.order_no} 正常退貨，回補可售庫存。"
    else:
        defective_inventory = DefectiveInventory.query.filter_by(product_variant_id=variant.id).first()
        if not defective_inventory:
            defective_inventory = DefectiveInventory(
                product_id=order_item.product_id,
                product_variant_id=variant.id,
                quantity=0,
            )
            db.session.add(defective_inventory)
        defective_inventory.quantity += quantity
        defective_inventory.updated_at = utc_now()
        movement_note = f"訂單 {order.order_no} 瑕疵退貨，累加瑕疵庫存。"

    movement = InventoryMovement(
        product_id=order_item.product_id,
        product_variant_id=variant.id,
        movement_type=return_type,
        quantity=quantity,
        reference_type="return",
        reference_id=None,
        note=movement_note,
    )
    db.session.add(movement)
    try:
        db.session.flush()
        movement.reference_id = return_record.id
        db.session.expire(order, ["returns"])
        recalculate_return_status(order)
        recalculate_order_amounts(order)
        db.session.commit()
        flash("退貨已建立，庫存紀錄已更新。", "success")
    except Exception:
        db.session.rollback()
        current_app.logger.exception("Order return failed")
        flash(SAVE_FAILED_ERROR, "danger")
    return redirect(request.referrer or url_for("orders.index"))


@orders_bp.route("/<int:order_id>/print")
@login_required
def print_order(order_id):
    order = Order.query.get_or_404(order_id)
    return render_template(
        "orders/print.html",
        order=order,
        return_summary=order_return_summary(order),
        amount_breakdown=order_amount_breakdown(order),
    )
