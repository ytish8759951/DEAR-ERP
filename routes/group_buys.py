from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation

from flask import Blueprint, current_app, flash, redirect, render_template, request, session, url_for
from sqlalchemy import func, or_

from config import Config
from decorators import login_required
from extensions import db
from models import (
    Color,
    Customer,
    CustomerCategory,
    GroupBuy,
    GroupBuyItem,
    GroupBuyOrder,
    GroupBuyOrderItem,
    Location,
    Order,
    OrderItem,
    OrderSource,
    Product,
    ProductVariant,
    Size,
    Supplier,
    utc_now,
)
from pagination import get_page_args
from routes.orders import generate_order_no, recalculate_fulfillment_status


group_buys_bp = Blueprint("group_buys", __name__, url_prefix="/line-group-buys")
public_groupbuy_bp = Blueprint("public_groupbuy", __name__, url_prefix="/groupbuy")
TAIPEI_TZ = timezone(timedelta(hours=8))
GB_SAVE_FAILED = "系統儲存失敗，請檢查資料是否完整。"


def clean(value):
    return (value or "").strip()


def parse_date(value):
    value = clean(value)
    if not value:
        return None
    for fmt in ("%Y-%m-%dT%H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            pass
    return None


def parse_datetime(value):
    value = clean(value)
    if not value:
        return None
    for fmt in ("%Y-%m-%dT%H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            pass
    return None


def parse_int(value, default=0):
    try:
        return int(value or default)
    except (TypeError, ValueError):
        return default


def parse_money(value, default=0):
    try:
        result = Decimal(clean(value) or str(default))
    except (InvalidOperation, TypeError):
        return Decimal(str(default))
    return result if result >= 0 else Decimal(str(default))


def today_code_prefix():
    return datetime.now(TAIPEI_TZ).strftime("%Y%m%d")


def generate_group_buy_no():
    prefix = f"G{today_code_prefix()}"
    latest = (
        GroupBuy.query.with_entities(GroupBuy.group_buy_no)
        .filter(GroupBuy.group_buy_no.like(f"{prefix}%"))
        .order_by(GroupBuy.group_buy_no.desc())
        .first()
    )
    sequence = 0
    if latest and latest.group_buy_no and latest.group_buy_no[len(prefix) :].isdigit():
        sequence = int(latest.group_buy_no[len(prefix) :])
    return f"{prefix}{sequence + 1:04d}"


def generate_group_buy_order_no():
    prefix = f"GB{today_code_prefix()}"
    latest = (
        GroupBuyOrder.query.with_entities(GroupBuyOrder.order_no)
        .filter(GroupBuyOrder.order_no.like(f"{prefix}%"))
        .order_by(GroupBuyOrder.order_no.desc())
        .first()
    )
    sequence = 0
    if latest and latest.order_no and latest.order_no[len(prefix) :].isdigit():
        sequence = int(latest.order_no[len(prefix) :])
    return f"{prefix}{sequence + 1:04d}"


def group_buy_statuses():
    return ["草稿", "進行中", "已結單", "已停用"]


def transfer_statuses():
    return ["未轉訂單", "已轉訂單", "已取消"]


def group_buy_filters():
    return {
        "group_buy_no": clean(request.args.get("group_buy_no")),
        "name": clean(request.args.get("name")),
        "status": clean(request.args.get("status")),
        "date_start": clean(request.args.get("date_start")),
        "date_end": clean(request.args.get("date_end")),
    }


def apply_group_buy_filters(query, filters):
    if filters["group_buy_no"]:
        query = query.filter(GroupBuy.group_buy_no.like(f"%{filters['group_buy_no']}%"))
    if filters["name"]:
        query = query.filter(GroupBuy.name.like(f"%{filters['name']}%"))
    if filters["status"]:
        query = query.filter(GroupBuy.status == filters["status"])
    date_start = parse_date(filters["date_start"])
    date_end = parse_date(filters["date_end"])
    if date_start:
        query = query.filter(GroupBuy.start_date >= date_start)
    if date_end:
        query = query.filter(GroupBuy.end_date <= date_end)
    return query


def order_filters():
    return {
        "order_no": clean(request.args.get("order_no")),
        "group_buy_no": clean(request.args.get("group_buy_no")),
        "group_buy_name": clean(request.args.get("group_buy_name")),
        "customer_name": clean(request.args.get("customer_name")),
        "customer_code": clean(request.args.get("customer_code")),
        "phone": clean(request.args.get("phone")),
        "product_code": clean(request.args.get("product_code")),
        "product_name": clean(request.args.get("product_name")),
        "group_status": clean(request.args.get("group_status")),
        "status": clean(request.args.get("status")),
        "date_start": clean(request.args.get("date_start")),
        "date_end": clean(request.args.get("date_end")),
    }


def apply_order_filters(query, filters):
    joined_group_buy = False
    joined_items = False
    if filters["order_no"]:
        query = query.filter(GroupBuyOrder.order_no.like(f"%{filters['order_no']}%"))
    if filters["group_buy_no"] or filters["group_buy_name"] or filters["group_status"]:
        query = query.join(GroupBuyOrder.group_buy)
        joined_group_buy = True
    if filters["group_buy_no"]:
        query = query.filter(GroupBuy.group_buy_no.like(f"%{filters['group_buy_no']}%"))
    if filters["group_buy_name"]:
        query = query.filter(GroupBuy.name.like(f"%{filters['group_buy_name']}%"))
    if filters["group_status"]:
        query = query.filter(GroupBuy.status == filters["group_status"])
    if filters["customer_name"]:
        query = query.filter(GroupBuyOrder.customer_name.like(f"%{filters['customer_name']}%"))
    if filters["customer_code"]:
        query = query.filter(GroupBuyOrder.customer_code.like(f"%{filters['customer_code']}%"))
    if filters["phone"]:
        query = query.filter(GroupBuyOrder.phone.like(f"%{filters['phone']}%"))
    if filters["product_code"] or filters["product_name"]:
        query = query.join(GroupBuyOrder.items)
        joined_items = True
    if filters["product_code"]:
        query = query.filter(GroupBuyOrderItem.product_code.like(f"%{filters['product_code']}%"))
    if filters["product_name"]:
        query = query.filter(GroupBuyOrderItem.product_name.like(f"%{filters['product_name']}%"))
    if filters["status"]:
        query = query.filter(GroupBuyOrder.order_status == filters["status"])
    date_start = parse_date(filters["date_start"])
    date_end = parse_date(filters["date_end"])
    if date_start:
        query = query.filter(func.date(GroupBuyOrder.created_at) >= date_start)
    if date_end:
        query = query.filter(func.date(GroupBuyOrder.created_at) <= date_end)
    if joined_items or joined_group_buy:
        query = query.distinct()
    return query


def sales_filters():
    return {
        "product_code": clean(request.args.get("product_code")),
        "product_name": clean(request.args.get("product_name")),
        "group_buy_name": clean(request.args.get("group_buy_name")),
        "date_start": clean(request.args.get("date_start")),
        "date_end": clean(request.args.get("date_end")),
        "supply_mode": clean(request.args.get("supply_mode")),
    }


def apply_sales_filters(query, filters):
    if filters["product_code"]:
        query = query.filter(GroupBuyOrderItem.product_code.like(f"%{filters['product_code']}%"))
    if filters["product_name"]:
        query = query.filter(GroupBuyOrderItem.product_name.like(f"%{filters['product_name']}%"))
    if filters["group_buy_name"]:
        query = query.filter(GroupBuy.name.like(f"%{filters['group_buy_name']}%"))
    if filters["supply_mode"]:
        query = query.filter(GroupBuyOrderItem.supply_mode == filters["supply_mode"])
    date_start = parse_date(filters["date_start"])
    date_end = parse_date(filters["date_end"])
    if date_start:
        query = query.filter(func.date(GroupBuyOrder.created_at) >= date_start)
    if date_end:
        query = query.filter(func.date(GroupBuyOrder.created_at) <= date_end)
    return query


def product_search_filters():
    return {
        "sku": clean(request.args.get("sku")),
        "name": clean(request.args.get("product_name")),
        "supplier_id": clean(request.args.get("supplier_id")),
        "color_id": clean(request.args.get("color_id")),
        "size_id": clean(request.args.get("size_id")),
        "location_id": clean(request.args.get("location_id")),
    }


def apply_product_search(query, filters):
    query = query.join(ProductVariant).join(ProductVariant.color).join(ProductVariant.size)
    if filters["sku"]:
        query = query.filter(Product.sku.like(f"%{filters['sku']}%"))
    if filters["name"]:
        query = query.filter(Product.name.like(f"%{filters['name']}%"))
    if filters["supplier_id"]:
        query = query.filter(Product.supplier_id == parse_int(filters["supplier_id"]))
    if filters["color_id"]:
        query = query.filter(ProductVariant.color_id == parse_int(filters["color_id"]))
    if filters["size_id"]:
        query = query.filter(ProductVariant.size_id == parse_int(filters["size_id"]))
    if filters["location_id"]:
        query = query.filter(Product.location_id == parse_int(filters["location_id"]))
    return query


def item_total(order):
    return sum(item.quantity or 0 for item in order.items)


def order_total(order):
    return sum(item.subtotal or 0 for item in order.items)


def page_url(endpoint, page, per_page, filters=None, **extra):
    params = {key: value for key, value in dict(filters or {}).items() if value not in ("", None)}
    params.update(extra)
    params["page"] = page
    params["per_page"] = per_page
    return url_for(endpoint, **params)


def public_group_buy_url(group_buy):
    return url_for("public_groupbuy.entry", public_code=group_buy.public_code or group_buy.group_buy_no)


def public_group_buy_preview_url(group_buy):
    return url_for("public_groupbuy.entry", public_code=group_buy.public_code or group_buy.group_buy_no, preview=1)


def public_group_buy_test_order_url(group_buy):
    return url_for("public_groupbuy.entry", public_code=group_buy.public_code or group_buy.group_buy_no, test_order=1)


def sync_group_buy_from_form(group_buy):
    group_buy.name = clean(request.form.get("name"))
    group_buy.start_date = parse_date(request.form.get("start_at"))
    group_buy.end_date = parse_date(request.form.get("end_at"))
    group_buy.description = clean(request.form.get("description"))
    group_buy.note = clean(request.form.get("note"))
    group_buy.status = clean(request.form.get("status")) or "草稿"
    group_buy.is_active = group_buy.status != "已停用"


def sync_group_buy_from_args(group_buy):
    if not request.args:
        return
    group_buy.group_buy_no = clean(request.args.get("group_buy_no")) or group_buy.group_buy_no
    group_buy.public_code = group_buy.group_buy_no
    group_buy.name = clean(request.args.get("name")) or group_buy.name
    group_buy.start_date = parse_date(request.args.get("start_at")) or group_buy.start_date
    group_buy.end_date = parse_date(request.args.get("end_at")) or group_buy.end_date
    group_buy.description = clean(request.args.get("description")) or group_buy.description
    group_buy.note = clean(request.args.get("note")) or group_buy.note
    group_buy.status = clean(request.args.get("status")) or group_buy.status
    group_buy.is_active = group_buy.status != "已停用"


def sync_group_buy_items_from_source(group_buy, source):
    group_buy.items = []
    for variant_id in source.getlist("variant_id"):
        variant = ProductVariant.query.get(parse_int(variant_id))
        if not variant or not variant.product:
            continue
        product = variant.product
        supply_mode = clean(source.get(f"supply_mode_{variant_id}")) or product.supply_mode or "一般商品"
        if product.supply_mode == "出清商品":
            supply_mode = "出清商品"
        group_price = parse_money(source.get(f"group_price_{variant_id}"), product.price or 0)
        order_limit = parse_int(source.get(f"order_limit_{variant_id}"), variant.stock or 0)
        group_buy.items.append(
            GroupBuyItem(
                product_id=product.id,
                product_variant_id=variant.id,
                supply_mode=supply_mode,
                original_price=product.price or 0,
                group_price=group_price,
                order_limit=order_limit,
                allow_preorder=False,
                is_active=True,
            )
        )


def sync_group_buy_items_from_form(group_buy):
    sync_group_buy_items_from_source(group_buy, request.form)


def sync_group_buy_items_from_args(group_buy):
    sync_group_buy_items_from_source(group_buy, request.args)


def validate_group_buy(group_buy):
    errors = []
    if not group_buy.name:
        errors.append("請輸入團購名稱")
    if not group_buy.status:
        errors.append("請選擇狀態")
    if not group_buy.items:
        errors.append("請至少加入一個團購商品")
    return errors


def selected_variant_ids(group_buy):
    return {item.product_variant_id for item in group_buy.items}


def render_group_buy_form(group_buy, action, status_code=200, errors=None):
    if request.method == "GET" and request.args:
        sync_group_buy_from_args(group_buy)
        sync_group_buy_items_from_args(group_buy)
    filters = product_search_filters()
    product_page = max(parse_int(request.args.get("product_page"), 1), 1)
    variant_query = ProductVariant.query.join(ProductVariant.product).join(ProductVariant.color).join(ProductVariant.size)
    if filters["sku"]:
        variant_query = variant_query.filter(Product.sku.like(f"%{filters['sku']}%"))
    if filters["name"]:
        variant_query = variant_query.filter(Product.name.like(f"%{filters['name']}%"))
    if filters["supplier_id"]:
        variant_query = variant_query.filter(Product.supplier_id == parse_int(filters["supplier_id"]))
    if filters["color_id"]:
        variant_query = variant_query.filter(ProductVariant.color_id == parse_int(filters["color_id"]))
    if filters["size_id"]:
        variant_query = variant_query.filter(ProductVariant.size_id == parse_int(filters["size_id"]))
    if filters["location_id"]:
        variant_query = variant_query.filter(Product.location_id == parse_int(filters["location_id"]))
    variant_pagination = variant_query.order_by(Product.sku, ProductVariant.id).paginate(
        page=product_page,
        per_page=20,
        error_out=False,
    )
    return (
        render_template(
            "group_buys/form.html",
            group_buy=group_buy,
            action=action,
            errors=errors or [],
            statuses=group_buy_statuses(),
            variant_rows=variant_pagination.items,
            variant_pagination=variant_pagination,
            selected_variant_ids=selected_variant_ids(group_buy),
            filters=filters,
            suppliers=Supplier.query.order_by(Supplier.name).all(),
            colors=Color.query.order_by(Color.name).all(),
            sizes=Size.query.order_by(Size.name).all(),
            locations=Location.query.order_by(Location.name).all(),
        ),
        status_code,
    )


def wholesale_customer(customer_code, phone):
    return (
        Customer.query
        .filter(Customer.customer_code == customer_code)
        .filter(Customer.phone == phone)
        .filter(Customer.is_active.is_(True))
        .filter(Customer.wholesale_paid.is_(True))
        .filter(Customer.category.has(name="批發客"))
        .first()
    )


def ensure_test_wholesale_customer():
    customer = Customer.query.filter_by(customer_code="TEST001").first()
    category = CustomerCategory.query.filter_by(name="批發客").first()
    if not category:
        category = CustomerCategory(name="批發客", is_active=True)
        db.session.add(category)
        db.session.flush()
    if not customer:
        customer = Customer(
            customer_code="TEST001",
            name="系統測試批客",
            phone="0912345678",
            category_id=category.id,
            wholesale_paid=True,
            wholesale_paid_date=utc_now().date(),
            is_active=True,
            note="系統測試下單使用",
        )
        db.session.add(customer)
        db.session.flush()
    else:
        customer.name = customer.name or "系統測試批客"
        customer.phone = customer.phone or "0912345678"
        customer.category_id = customer.category_id or category.id
        customer.wholesale_paid = True
        customer.is_active = True
    return customer


def active_group_buy(public_code):
    return (
        GroupBuy.query.filter(or_(GroupBuy.public_code == public_code, GroupBuy.group_buy_no == public_code))
        .filter(GroupBuy.is_active.is_(True))
        .filter(GroupBuy.status == "進行中")
        .first_or_404()
    )


def public_group_buy_by_code(public_code):
    return (
        GroupBuy.query.filter(or_(GroupBuy.public_code == public_code, GroupBuy.group_buy_no == public_code))
        .filter(GroupBuy.is_active.is_(True))
        .first_or_404()
    )


def verified_customer_for_group_buy(group_buy):
    key = f"groupbuy_verified_{group_buy.id}"
    verified = session.get(key) or {}
    if verified.get("groupbuy_id") != group_buy.id:
        return None
    return Customer.query.get(verified.get("customer_id"))


def line_order_source():
    source = OrderSource.query.filter_by(name="LINE團購").first()
    if not source:
        source = OrderSource(name="LINE團購", is_active=True)
        db.session.add(source)
        db.session.flush()
    return source


def convert_group_buy_order(group_order):
    if group_order.order_status == "已轉訂單" and group_order.formal_order_id:
        return group_order.formal_order
    if group_order.order_status == "已取消":
        raise ValueError("已取消的團購訂單不可轉單。")

    order_date = utc_now().date()
    formal_order = Order(
        order_no=generate_order_no(order_date),
        order_date=order_date,
        customer_id=group_order.customer_id,
        order_source_id=line_order_source().id,
        group_buy_order_id=group_order.id,
        group_buy_code=group_order.group_buy.group_buy_no if group_order.group_buy else group_order.group_buy_code,
        status="已付款",
        note=f"由團購訂單 {group_order.order_no} 轉入",
    )
    total = Decimal("0")
    for item in group_order.items:
        variant = item.product_variant
        if not variant:
            raise ValueError(f"{item.product_name} 找不到商品規格，無法轉單。")
        quantity = item.quantity or 0
        if item.supply_mode == "出清商品" and quantity > variant.stock:
            raise ValueError("此商品為出清商品，現貨賣完不補。請修改數量或取消商品後再轉訂單。")
        allocated_quantity = min(quantity, max(variant.stock, 0))
        backorder_quantity = max(quantity - allocated_quantity, 0)
        if item.supply_mode == "出清商品" and backorder_quantity > 0:
            raise ValueError("此商品為出清商品，現貨賣完不補。請修改數量或取消商品後再轉訂單。")
        variant.stock -= allocated_quantity
        formal_order.items.append(
            OrderItem(
                product_id=item.product_id,
                product_variant_id=item.product_variant_id,
                quantity=quantity,
                allocated_quantity=allocated_quantity,
                backorder_quantity=backorder_quantity,
                unit_price=item.unit_price,
                subtotal=item.subtotal,
            )
        )
        item.converted_quantity = quantity
        item.backorder_quantity = backorder_quantity
        total += Decimal(item.subtotal or 0)
    formal_order.total_amount = total
    formal_order.receivable_amount = total
    recalculate_fulfillment_status(formal_order)
    group_order.order_status = "已轉訂單"
    db.session.add(formal_order)
    db.session.flush()
    group_order.formal_order_id = formal_order.id
    return formal_order


@group_buys_bp.route("/")
@login_required
def index():
    filters = group_buy_filters()
    page, per_page = get_page_args(request, Config.DEFAULT_PAGE_SIZE, Config.PAGE_SIZE_OPTIONS)
    query = apply_group_buy_filters(GroupBuy.query, filters)
    pagination = query.order_by(GroupBuy.created_at.desc()).paginate(page=page, per_page=per_page, error_out=False)
    return render_template(
        "group_buys/index.html",
        group_buys=pagination.items,
        pagination=pagination,
        filters=filters,
        statuses=group_buy_statuses(),
        page_size_options=Config.PAGE_SIZE_OPTIONS,
        public_group_buy_url=public_group_buy_url,
        public_group_buy_preview_url=public_group_buy_preview_url,
        public_group_buy_test_order_url=public_group_buy_test_order_url,
        item_total=item_total,
        order_total=order_total,
        prev_page_url=page_url("group_buys.index", pagination.prev_num, pagination.per_page, filters),
        next_page_url=page_url("group_buys.index", pagination.next_num, pagination.per_page, filters),
    )


@group_buys_bp.route("/new", methods=["GET", "POST"])
@login_required
def create():
    group_buy = GroupBuy(group_buy_no=generate_group_buy_no(), public_code=generate_group_buy_no(), status="草稿")
    if request.method == "POST":
        try:
            group_buy.group_buy_no = generate_group_buy_no()
            group_buy.public_code = group_buy.group_buy_no
            sync_group_buy_from_form(group_buy)
            sync_group_buy_items_from_form(group_buy)
            errors = validate_group_buy(group_buy)
            if errors:
                db.session.rollback()
                return render_group_buy_form(group_buy, "新增團購", 200, errors)
            db.session.add(group_buy)
            db.session.commit()
            flash("團購已新增。", "success")
            return redirect(url_for("group_buys.detail", group_buy_id=group_buy.id))
        except Exception:
            db.session.rollback()
            current_app.logger.exception("Group buy create failed")
            return render_group_buy_form(group_buy, "新增團購", 200, [GB_SAVE_FAILED])
    return render_group_buy_form(group_buy, "新增團購")


@group_buys_bp.route("/<int:group_buy_id>")
@login_required
def detail(group_buy_id):
    group_buy = GroupBuy.query.get_or_404(group_buy_id)
    return render_template(
        "group_buys/detail.html",
        group_buy=group_buy,
        public_url=public_group_buy_url(group_buy),
        item_total=item_total,
        order_total=order_total,
    )


@group_buys_bp.route("/<int:group_buy_id>/edit", methods=["GET", "POST"])
@login_required
def edit(group_buy_id):
    group_buy = GroupBuy.query.get_or_404(group_buy_id)
    if request.method == "POST":
        try:
            sync_group_buy_from_form(group_buy)
            sync_group_buy_items_from_form(group_buy)
            errors = validate_group_buy(group_buy)
            if errors:
                db.session.rollback()
                return render_group_buy_form(group_buy, "編輯團購", 200, errors)
            db.session.commit()
            flash("團購已更新。", "success")
            return redirect(url_for("group_buys.detail", group_buy_id=group_buy.id))
        except Exception:
            db.session.rollback()
            current_app.logger.exception("Group buy update failed")
            return render_group_buy_form(group_buy, "編輯團購", 200, [GB_SAVE_FAILED])
    return render_group_buy_form(group_buy, "編輯團購")


@group_buys_bp.route("/<int:group_buy_id>/close", methods=["POST"])
@login_required
def close(group_buy_id):
    group_buy = GroupBuy.query.get_or_404(group_buy_id)
    group_buy.status = "已結單"
    try:
        db.session.commit()
        flash("團購已結單。", "success")
    except Exception:
        db.session.rollback()
        flash(GB_SAVE_FAILED, "danger")
    return redirect(url_for("group_buys.index"))


@group_buys_bp.route("/<int:group_buy_id>/deactivate", methods=["POST"])
@login_required
def deactivate(group_buy_id):
    group_buy = GroupBuy.query.get_or_404(group_buy_id)
    group_buy.status = "已停用"
    group_buy.is_active = False
    try:
        db.session.commit()
        flash("團購已停用。", "success")
    except Exception:
        db.session.rollback()
        flash(GB_SAVE_FAILED, "danger")
    return redirect(url_for("group_buys.index"))


@group_buys_bp.route("/orders")
@login_required
def orders():
    filters = order_filters()
    page, per_page = get_page_args(request, Config.DEFAULT_PAGE_SIZE, Config.PAGE_SIZE_OPTIONS)
    query = apply_order_filters(GroupBuyOrder.query, filters)
    pagination = query.order_by(GroupBuyOrder.created_at.desc(), GroupBuyOrder.id.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )
    return render_template(
        "group_buys/orders.html",
        orders=pagination.items,
        pagination=pagination,
        filters=filters,
        transfer_statuses=transfer_statuses(),
        group_statuses=group_buy_statuses(),
        page_size_options=Config.PAGE_SIZE_OPTIONS,
        item_total=item_total,
        order_total=order_total,
        prev_page_url=page_url("group_buys.orders", pagination.prev_num, pagination.per_page, filters),
        next_page_url=page_url("group_buys.orders", pagination.next_num, pagination.per_page, filters),
    )


@group_buys_bp.route("/orders/<int:order_id>")
@login_required
def order_detail(order_id):
    order = GroupBuyOrder.query.get_or_404(order_id)
    return render_template("group_buys/order_detail.html", order=order, item_total=item_total(order), order_total=order_total(order))


@group_buys_bp.route("/orders/<int:order_id>/convert", methods=["POST"])
@login_required
def convert_order(order_id):
    group_order = GroupBuyOrder.query.get_or_404(order_id)
    try:
        formal_order = convert_group_buy_order(group_order)
        db.session.commit()
        flash("團購訂單已轉正式訂單。", "success")
        return redirect(url_for("orders.detail", order_id=formal_order.id))
    except ValueError as error:
        db.session.rollback()
        flash(str(error), "danger")
    except Exception:
        db.session.rollback()
        current_app.logger.exception("Group buy order convert failed")
        flash(GB_SAVE_FAILED, "danger")
    return redirect(url_for("group_buys.order_detail", order_id=group_order.id))


@group_buys_bp.route("/orders/convert-batch", methods=["POST"])
@login_required
def convert_batch():
    order_ids = [parse_int(value) for value in request.form.getlist("order_ids")]
    converted = 0
    try:
        query = GroupBuyOrder.query.filter(GroupBuyOrder.id.in_(order_ids), GroupBuyOrder.order_status == "未轉訂單")
        for group_order in query.order_by(GroupBuyOrder.created_at):
            convert_group_buy_order(group_order)
            converted += 1
        db.session.commit()
        flash(f"已轉單 {converted} 筆。", "success")
    except ValueError as error:
        db.session.rollback()
        flash(str(error), "danger")
    except Exception:
        db.session.rollback()
        current_app.logger.exception("Group buy batch convert failed")
        flash(GB_SAVE_FAILED, "danger")
    return redirect(url_for("group_buys.orders"))


@group_buys_bp.route("/orders/<int:order_id>/cancel", methods=["POST"])
@login_required
def cancel_order(order_id):
    group_order = GroupBuyOrder.query.get_or_404(order_id)
    if group_order.order_status == "已轉訂單":
        flash("已轉正式訂單不可取消。", "danger")
        return redirect(url_for("group_buys.orders"))
    group_order.order_status = "已取消"
    try:
        db.session.commit()
        flash("團購訂單已取消。", "success")
    except Exception:
        db.session.rollback()
        flash(GB_SAVE_FAILED, "danger")
    return redirect(url_for("group_buys.orders"))


@group_buys_bp.route("/sales")
@login_required
def sales():
    filters = sales_filters()
    page, per_page = get_page_args(request, Config.DEFAULT_PAGE_SIZE, Config.PAGE_SIZE_OPTIONS)
    query = (
        GroupBuyOrderItem.query.join(GroupBuyOrderItem.group_buy_order)
        .outerjoin(GroupBuyOrderItem.group_buy)
        .with_entities(
            GroupBuyOrderItem.product_id.label("product_id"),
            GroupBuyOrderItem.product_code.label("product_code"),
            GroupBuyOrderItem.product_name.label("product_name"),
            GroupBuyOrderItem.supply_mode.label("supply_mode"),
            func.count(func.distinct(GroupBuyOrderItem.group_buy_id)).label("group_buy_count"),
            func.coalesce(func.sum(GroupBuyOrderItem.quantity), 0).label("sales_quantity"),
            func.coalesce(func.sum(GroupBuyOrderItem.backorder_quantity), 0).label("backorder_quantity"),
            func.coalesce(func.sum(GroupBuyOrderItem.converted_quantity), 0).label("converted_quantity"),
            func.coalesce(func.sum(GroupBuyOrderItem.subtotal), 0).label("sales_amount"),
            func.max(GroupBuyOrder.created_at).label("last_order_time"),
        )
        .group_by(
            GroupBuyOrderItem.product_id,
            GroupBuyOrderItem.product_code,
            GroupBuyOrderItem.product_name,
            GroupBuyOrderItem.supply_mode,
        )
    )
    query = apply_sales_filters(query, filters)
    pagination = query.order_by(func.max(GroupBuyOrder.created_at).desc()).paginate(page=page, per_page=per_page, error_out=False)
    return render_template(
        "group_buys/sales.html",
        rows=pagination.items,
        pagination=pagination,
        filters=filters,
        page_size_options=Config.PAGE_SIZE_OPTIONS,
        prev_page_url=page_url("group_buys.sales", pagination.prev_num, pagination.per_page, filters),
        next_page_url=page_url("group_buys.sales", pagination.next_num, pagination.per_page, filters),
    )


@group_buys_bp.route("/sales/<int:product_id>")
@login_required
def sales_detail(product_id):
    product = Product.query.get_or_404(product_id)
    filters = sales_filters()
    page, per_page = get_page_args(request, Config.DEFAULT_PAGE_SIZE, Config.PAGE_SIZE_OPTIONS)
    query = (
        GroupBuyOrderItem.query.join(GroupBuyOrderItem.group_buy_order)
        .outerjoin(GroupBuyOrderItem.group_buy)
        .filter(GroupBuyOrderItem.product_id == product_id)
    )
    query = apply_sales_filters(query, filters)
    pagination = query.order_by(GroupBuyOrder.created_at.desc(), GroupBuyOrderItem.id.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )
    return render_template(
        "group_buys/sales_detail.html",
        product=product,
        items=pagination.items,
        pagination=pagination,
        filters=filters,
        page_size_options=Config.PAGE_SIZE_OPTIONS,
        prev_page_url=page_url("group_buys.sales_detail", pagination.prev_num, pagination.per_page, filters, product_id=product_id),
        next_page_url=page_url("group_buys.sales_detail", pagination.next_num, pagination.per_page, filters, product_id=product_id),
    )


@public_groupbuy_bp.route("/<public_code>", methods=["GET", "POST"])
def entry(public_code):
    preview_mode = request.args.get("preview") == "1"
    test_order_mode = request.args.get("test_order") == "1"
    group_buy = public_group_buy_by_code(public_code) if (preview_mode or test_order_mode) else active_group_buy(public_code)
    customer = None if preview_mode else verified_customer_for_group_buy(group_buy)
    if test_order_mode:
        customer = ensure_test_wholesale_customer()
        db.session.commit()
    error = None
    if request.method == "POST" and request.form.get("action") == "verify":
        customer_code = clean(request.form.get("customer_code"))
        phone = clean(request.form.get("phone"))
        customer = wholesale_customer(customer_code, phone)
        if customer:
            session[f"groupbuy_verified_{group_buy.id}"] = {
                "customer_id": customer.id,
                "customer_code": customer.customer_code,
                "groupbuy_id": group_buy.id,
                "verified_at": utc_now().isoformat(),
            }
            return redirect(url_for("public_groupbuy.entry", public_code=public_code))
        error = "查無有效批發客資格，請聯繫客服。"
    return render_template(
        "group_buys/public.html",
        group_buy=group_buy,
        customer=customer,
        error=error,
        preview_mode=preview_mode,
        test_order_mode=test_order_mode,
    )


@public_groupbuy_bp.route("/<public_code>/order", methods=["POST"])
def submit_order(public_code):
    preview_mode = request.args.get("preview") == "1" or request.form.get("preview_mode") == "1"
    test_order_mode = request.args.get("test_order") == "1" or request.form.get("test_order_mode") == "1"
    group_buy = public_group_buy_by_code(public_code) if (preview_mode or test_order_mode) else active_group_buy(public_code)
    if preview_mode:
        flash("預覽模式僅供畫面檢查，不會建立團購訂單。", "warning")
        return redirect(url_for("public_groupbuy.entry", public_code=public_code, preview=1))
    customer = ensure_test_wholesale_customer() if test_order_mode else verified_customer_for_group_buy(group_buy)
    entry_url = url_for("public_groupbuy.entry", public_code=public_code, test_order=1) if test_order_mode else url_for("public_groupbuy.entry", public_code=public_code)
    if not customer:
        flash("請先完成批客驗證。", "danger")
        return redirect(entry_url)
    line_name = clean(request.form.get("line_name"))
    group_order = GroupBuyOrder(
        order_no=generate_group_buy_order_no(),
        group_buy_id=group_buy.id,
        customer_id=customer.id,
        customer_name=customer.name,
        customer_code=customer.customer_code,
        line_name=line_name,
        phone=customer.phone,
        order_status="未轉訂單",
        group_buy_code=group_buy.group_buy_no,
        is_test_order=test_order_mode,
    )
    total = Decimal("0")
    for group_item in group_buy.items:
        quantity = parse_int(request.form.get(f"quantity_{group_item.id}"))
        if quantity <= 0:
            continue
        if group_item.supply_mode == "出清商品" and quantity > (group_item.product_variant.stock or 0):
            flash(f"{group_item.product.name} 為出清商品，庫存不足。", "danger")
            return redirect(entry_url)
        if group_item.order_limit and quantity > group_item.order_limit:
            flash(f"{group_item.product.name} 超過可下單數量。", "danger")
            return redirect(entry_url)
        subtotal = Decimal(quantity) * Decimal(group_item.group_price or 0)
        backorder = max(quantity - (group_item.product_variant.stock or 0), 0)
        if group_item.supply_mode == "出清商品":
            backorder = 0
        group_order.items.append(
            GroupBuyOrderItem(
                group_buy_id=group_buy.id,
                product_id=group_item.product_id,
                product_variant_id=group_item.product_variant_id,
                product_code=group_item.product.sku,
                product_name=group_item.product.name,
                color_name=group_item.product_variant.color.name if group_item.product_variant.color else "",
                size_name=group_item.product_variant.size.name if group_item.product_variant.size else "",
                supply_mode=group_item.supply_mode,
                quantity=quantity,
                unit_price=group_item.group_price,
                subtotal=subtotal,
                backorder_quantity=backorder,
            )
        )
        total += subtotal
    if not group_order.items:
        flash("請至少選擇一個商品數量。", "danger")
        return redirect(entry_url)
    group_order.total_amount = total
    try:
        db.session.add(group_order)
        db.session.commit()
        flash("團購訂單已送出。", "success")
        return redirect(url_for("public_groupbuy.thank_you", public_code=public_code, order_no=group_order.order_no, test_order=1 if test_order_mode else None))
    except Exception:
        db.session.rollback()
        current_app.logger.exception("Public group buy order submit failed")
        flash(GB_SAVE_FAILED, "danger")
        return redirect(entry_url)


@public_groupbuy_bp.route("/<public_code>/thanks")
def thank_you(public_code):
    return render_template(
        "group_buys/public_thanks.html",
        public_code=public_code,
        order_no=clean(request.args.get("order_no")),
        test_order_mode=request.args.get("test_order") == "1",
    )
