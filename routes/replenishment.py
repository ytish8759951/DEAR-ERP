from datetime import datetime, timedelta, timezone
from math import ceil

from flask import Blueprint, current_app, flash, redirect, render_template, request, url_for
from sqlalchemy import func

from config import Config
from decorators import login_required
from extensions import db
from models import (
    InventoryMovement,
    Order,
    OrderItem,
    Product,
    ProductVariant,
    ReplenishmentItem,
    ReplenishmentOrder,
    ReplenishmentReceipt,
    Supplier,
    utc_now,
)
from pagination import get_page_args
from routes.orders import recalculate_fulfillment_status


replenishment_bp = Blueprint("replenishment", __name__, url_prefix="/replenishment")
FINISHED_STATUSES = {"已完成", "已到貨"}
CLOSED_STATUSES = {"已完成", "已到貨", "已取消"}


class SimplePagination:
    def __init__(self, items, page, per_page, total):
        self.items = items
        self.page = page
        self.per_page = per_page
        self.total = total
        self.pages = ceil(total / per_page) if total else 0
        self.has_prev = page > 1
        self.has_next = page < self.pages
        self.prev_num = page - 1
        self.next_num = page + 1


def clean(value):
    return (value or "").strip()


def parse_int(value, default=0):
    try:
        return int(value or default)
    except (TypeError, ValueError):
        return default


def parse_date(value):
    value = clean(value)
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None


def generate_replenishment_no(sequence_offset=0):
    today = datetime.now(timezone(timedelta(hours=8))).date()
    prefix = f"P{today.strftime('%Y%m%d')}"
    latest = (
        ReplenishmentOrder.query.with_entities(ReplenishmentOrder.order_no)
        .filter(ReplenishmentOrder.order_no.like(f"{prefix}%"))
        .order_by(ReplenishmentOrder.order_no.desc())
        .first()
    )
    sequence = 0
    if latest and latest.order_no and latest.order_no[len(prefix) :].isdigit():
        sequence = int(latest.order_no[len(prefix) :])
    return f"{prefix}{sequence + 1 + sequence_offset:04d}"


def status_options():
    return [
        ("", "全部"),
        ("追貨中", "追貨中"),
        ("部分到貨", "部分到貨"),
        ("已完成", "已完成"),
        ("已取消", "已取消"),
    ]


def demand_query(filters):
    query = (
        db.session.query(
            ProductVariant,
            func.coalesce(func.sum(OrderItem.backorder_quantity), 0).label("required_quantity"),
        )
        .join(OrderItem, OrderItem.product_variant_id == ProductVariant.id)
        .join(Order, Order.id == OrderItem.order_id)
        .join(Product, Product.id == ProductVariant.product_id)
        .outerjoin(Supplier, Supplier.id == Product.supplier_id)
        .filter(OrderItem.backorder_quantity > 0)
        .filter(Product.supply_mode != "出清商品")
        .filter(~Order.status.in_(["已取消", "已退貨", "全部退貨"]))
        .group_by(ProductVariant.id)
    )
    if filters["sku"]:
        query = query.filter(Product.sku.like(f"%{filters['sku']}%"))
    if filters["name"]:
        query = query.filter(Product.name.like(f"%{filters['name']}%"))
    if filters["supplier_id"]:
        supplier_id = parse_int(filters["supplier_id"])
        if supplier_id:
            query = query.filter(Product.supplier_id == supplier_id)
    return query.order_by(Product.sku, ProductVariant.id)


def replenishment_filters():
    return {
        "sku": clean(request.args.get("sku")),
        "name": clean(request.args.get("name")),
        "supplier_id": clean(request.args.get("supplier_id")),
        "status": clean(request.args.get("status")),
    }


def open_replenishment_quantity_by_variant():
    rows = (
        db.session.query(
            ReplenishmentItem.product_variant_id,
            func.coalesce(func.sum(ReplenishmentItem.remaining_quantity), 0),
        )
        .join(ReplenishmentItem.replenishment_order)
        .filter(~ReplenishmentOrder.status.in_(CLOSED_STATUSES))
        .filter(ReplenishmentItem.remaining_quantity > 0)
        .group_by(ReplenishmentItem.product_variant_id)
        .all()
    )
    return {variant_id: int(quantity or 0) for variant_id, quantity in rows}


def outstanding_demand_rows(filters):
    open_quantities = open_replenishment_quantity_by_variant()
    rows = []
    for variant, required_quantity in demand_query(filters).all():
        available_quantity = int(required_quantity or 0) - open_quantities.get(variant.id, 0)
        if available_quantity > 0:
            rows.append((variant, available_quantity))
    return rows


def paginate_list(items, page, per_page):
    total = len(items)
    start = (page - 1) * per_page
    end = start + per_page
    return SimplePagination(items[start:end], page, per_page, total)


def replenishment_order_query(filters):
    query = ReplenishmentOrder.query
    if filters["status"]:
        if filters["status"] == "已完成":
            query = query.filter(ReplenishmentOrder.status.in_(FINISHED_STATUSES))
        else:
            query = query.filter(ReplenishmentOrder.status == filters["status"])
    supplier_id = parse_int(filters["supplier_id"])
    if supplier_id:
        query = query.filter(ReplenishmentOrder.supplier_id == supplier_id)
    if filters["sku"] or filters["name"]:
        query = query.join(ReplenishmentOrder.items).join(ReplenishmentItem.product)
        if filters["sku"]:
            query = query.filter(Product.sku.like(f"%{filters['sku']}%"))
        if filters["name"]:
            query = query.filter(Product.name.like(f"%{filters['name']}%"))
        query = query.distinct()
    return query.order_by(ReplenishmentOrder.created_at.desc(), ReplenishmentOrder.id.desc())


def ordered_pending_items(variant_id):
    return (
        OrderItem.query.join(Order)
        .filter(OrderItem.product_variant_id == variant_id)
        .filter(OrderItem.backorder_quantity > 0)
        .join(Product, Product.id == OrderItem.product_id)
        .filter(Product.supply_mode != "出清商品")
        .filter(~Order.status.in_(["已取消", "已退貨", "全部退貨"]))
        .order_by(Order.created_at.asc(), Order.id.asc(), OrderItem.id.asc())
        .all()
    )


def allocate_arrival(variant, quantity):
    remaining = quantity
    completed_orders = set()
    for order_item in ordered_pending_items(variant.id):
        if remaining <= 0:
            break
        allocated = min(order_item.backorder_quantity, remaining)
        order_item.allocated_quantity = (order_item.allocated_quantity or 0) + allocated
        order_item.backorder_quantity = max((order_item.backorder_quantity or 0) - allocated, 0)
        remaining -= allocated
        recalculate_fulfillment_status(order_item.order)
        if order_item.order.status == "待出貨":
            completed_orders.add(order_item.order.id)

    if remaining > 0:
        before_quantity = variant.stock
        variant.stock += remaining
        db.session.add(
            InventoryMovement(
                product_id=variant.product_id,
                product_variant_id=variant.id,
                movement_type="追貨超額入庫",
                before_quantity=before_quantity,
                quantity=remaining,
                after_quantity=variant.stock,
                reference_type="replenishment",
                note="追貨到貨超過待貨數量，自動進可售庫存。",
            )
        )
    return completed_orders, remaining


def refresh_replenishment_status(replenishment_order):
    if replenishment_order.status == "已取消":
        return
    any_pending = False
    any_received = False
    for item in replenishment_order.items:
        item.remaining_quantity = max((item.required_quantity or 0) - (item.received_quantity or 0), 0)
        if item.remaining_quantity <= 0:
            item.status = "已完成"
        elif item.received_quantity > 0:
            item.status = "部分到貨"
            any_pending = True
            any_received = True
        else:
            item.status = "追貨中"
            any_pending = True
    if not any_pending:
        replenishment_order.status = "已完成"
    elif any_received or any(item.received_quantity > 0 for item in replenishment_order.items):
        replenishment_order.status = "部分到貨"
    else:
        replenishment_order.status = "追貨中"


def item_supplier(item):
    return item.product.supplier if item.product and item.product.supplier else item.replenishment_order.supplier


def replenishment_detail_summary(replenishment_order):
    grouped = {}
    for item in replenishment_order.items:
        supplier = item_supplier(item)
        variant = item.product_variant
        product = item.product
        color_name = variant.color.name if variant and variant.color else ""
        size_name = variant.size.name if variant and variant.size else ""
        key = (
            supplier.id if supplier else 0,
            product.sku if product else "",
            product.name if product else "",
            color_name,
            size_name,
            item.product_variant_id,
        )
        if key not in grouped:
            grouped[key] = {
                "supplier": supplier,
                "supplier_name": supplier.name if supplier else "未指定廠商",
                "product": product,
                "variant": variant,
                "color_name": color_name or "-",
                "size_name": size_name or "-",
                "required_quantity": 0,
                "received_quantity": 0,
                "remaining_quantity": 0,
            }
        row = grouped[key]
        row["required_quantity"] += item.required_quantity or 0
        row["received_quantity"] += item.received_quantity or 0
        row["remaining_quantity"] += item.remaining_quantity or 0

    rows = []
    for row in grouped.values():
        if row["remaining_quantity"] <= 0:
            row["status"] = "已完成"
        elif row["received_quantity"] > 0:
            row["status"] = "部分到貨"
        else:
            row["status"] = "追貨中"
        rows.append(row)

    rows.sort(
        key=lambda row: (
            row["supplier_name"],
            row["product"].sku if row["product"] else "",
            row["color_name"],
            row["size_name"],
        )
    )

    supplier_stats = {}
    for row in rows:
        supplier_id = row["supplier"].id if row["supplier"] else 0
        if supplier_id not in supplier_stats:
            supplier_stats[supplier_id] = {
                "supplier_name": row["supplier_name"],
                "item_count": 0,
                "required_quantity": 0,
                "received_quantity": 0,
                "remaining_quantity": 0,
            }
        stat = supplier_stats[supplier_id]
        stat["item_count"] += 1
        stat["required_quantity"] += row["required_quantity"]
        stat["received_quantity"] += row["received_quantity"]
        stat["remaining_quantity"] += row["remaining_quantity"]

    supplier_rows = []
    for stat in supplier_stats.values():
        if stat["remaining_quantity"] <= 0:
            stat["status"] = "已完成"
        elif stat["received_quantity"] > 0:
            stat["status"] = "部分到貨"
        else:
            stat["status"] = "追貨中"
        supplier_rows.append(stat)
    supplier_rows.sort(key=lambda stat: stat["supplier_name"])

    totals = {
        "supplier_count": len(supplier_rows),
        "item_count": len(rows),
        "required_quantity": sum(row["required_quantity"] for row in rows),
        "received_quantity": sum(row["received_quantity"] for row in rows),
        "remaining_quantity": sum(row["remaining_quantity"] for row in rows),
    }
    supplier_sections = []
    for stat in supplier_rows:
        supplier_sections.append(
            {
                "stat": stat,
                "rows": [row for row in rows if row["supplier_name"] == stat["supplier_name"]],
            }
        )
    return rows, supplier_rows, supplier_sections, totals


@replenishment_bp.route("/")
@login_required
def index():
    filters = replenishment_filters()
    page, per_page = get_page_args(request, Config.DEFAULT_PAGE_SIZE, Config.PAGE_SIZE_OPTIONS)
    pagination = paginate_list(outstanding_demand_rows(filters), page, per_page)
    order_page = max(request.args.get("order_page", 1, type=int), 1)
    order_pagination = replenishment_order_query(filters).paginate(
        page=order_page,
        per_page=per_page,
        error_out=False,
    )
    order_summaries = {
        order.id: replenishment_detail_summary(order)[3]
        for order in order_pagination.items
    }
    return render_template(
        "replenishment/index.html",
        rows=pagination.items,
        pagination=pagination,
        replenishment_orders=order_pagination.items,
        order_summaries=order_summaries,
        order_pagination=order_pagination,
        filters=filters,
        suppliers=Supplier.query.order_by(Supplier.name).all(),
        status_options=status_options(),
        page_size_options=Config.PAGE_SIZE_OPTIONS,
    )


@replenishment_bp.route("/create", methods=["POST"])
@login_required
def create():
    expected_arrival_date = parse_date(request.form.get("expected_arrival_date"))
    note = clean(request.form.get("note"))
    filters = {"sku": "", "name": "", "supplier_id": "", "status": ""}
    outstanding_rows = outstanding_demand_rows(filters)

    if not outstanding_rows:
        flash("目前沒有可建立追貨單的待貨需求。", "warning")
        return redirect(url_for("replenishment.index"))

    outstanding_rows.sort(
        key=lambda row: (
            row[0].product.supplier.name if row[0].product and row[0].product.supplier else "未指定廠商",
            row[0].product.sku if row[0].product else "",
            row[0].color.name if row[0].color else "",
            row[0].size.name if row[0].size else "",
        )
    )
    order = ReplenishmentOrder(
        order_no=generate_replenishment_no(),
        supplier_id=None,
        expected_arrival_date=expected_arrival_date,
        note=note,
    )
    for variant, required_quantity in outstanding_rows:
        order.items.append(
            ReplenishmentItem(
                product_id=variant.product_id,
                product_variant_id=variant.id,
                required_quantity=required_quantity,
                received_quantity=0,
                remaining_quantity=required_quantity,
                status="追貨中",
            )
        )
    db.session.add(order)

    try:
        db.session.commit()
        _rows, _supplier_rows, _sections, totals = replenishment_detail_summary(order)
        flash("本次建立追貨單數量：1", "success")
        flash(
            f"{order.order_no}｜綜合追貨單｜廠商數：{totals['supplier_count']}｜商品款數：{totals['item_count']}｜追貨總數量：{totals['required_quantity']}",
            "success",
        )
        return redirect(url_for("replenishment.detail", order_id=order.id))
    except Exception:
        db.session.rollback()
        current_app.logger.exception("Replenishment create failed")
        flash("系統儲存失敗，請檢查資料是否完整。", "danger")
        return redirect(url_for("replenishment.index"))


@replenishment_bp.route("/<int:order_id>")
@login_required
def detail(order_id):
    order = ReplenishmentOrder.query.get_or_404(order_id)
    item_rows, supplier_rows, supplier_sections, totals = replenishment_detail_summary(order)
    return render_template(
        "replenishment/detail.html",
        order=order,
        item_rows=item_rows,
        supplier_rows=supplier_rows,
        supplier_sections=supplier_sections,
        totals=totals,
    )


@replenishment_bp.route("/<int:order_id>/note", methods=["POST"])
@login_required
def update_note(order_id):
    order = ReplenishmentOrder.query.get_or_404(order_id)
    order.note = clean(request.form.get("note"))
    try:
        db.session.commit()
        flash("追貨單備註已更新。", "success")
    except Exception:
        db.session.rollback()
        current_app.logger.exception("Replenishment note update failed")
        flash("系統儲存失敗，請檢查資料是否完整。", "danger")
    return redirect(url_for("replenishment.index"))


@replenishment_bp.route("/<int:order_id>/cancel", methods=["POST"])
@login_required
def cancel(order_id):
    order = ReplenishmentOrder.query.get_or_404(order_id)
    if order.status in FINISHED_STATUSES:
        flash("已完成的追貨單不可取消。", "danger")
        return redirect(url_for("replenishment.index"))
    order.status = "已取消"
    for item in order.items:
        if item.status not in FINISHED_STATUSES:
            item.status = "已取消"
    try:
        db.session.commit()
        flash("追貨單已取消，未到貨數量已釋放回待建立追貨清單。", "success")
    except Exception:
        db.session.rollback()
        current_app.logger.exception("Replenishment cancel failed")
        flash("系統儲存失敗，請檢查資料是否完整。", "danger")
    return redirect(url_for("replenishment.index"))


@replenishment_bp.route("/items/<int:item_id>/receive", methods=["POST"])
@login_required
def receive(item_id):
    item = ReplenishmentItem.query.get_or_404(item_id)
    if item.replenishment_order.status in CLOSED_STATUSES:
        flash("此追貨單已關閉，無法再登錄到貨。", "danger")
        return redirect(url_for("replenishment.detail", order_id=item.replenishment_order_id))
    mode = clean(request.form.get("mode"))
    quantity = item.remaining_quantity if mode == "all" else parse_int(request.form.get("quantity"))
    if quantity <= 0:
        flash("請輸入正確到貨數量。", "danger")
        return redirect(url_for("replenishment.detail", order_id=item.replenishment_order_id))

    variant = item.product_variant
    try:
        item.received_quantity = (item.received_quantity or 0) + quantity
        item.remaining_quantity = max((item.required_quantity or 0) - item.received_quantity, 0)
        receipt = ReplenishmentReceipt(
            replenishment_order_id=item.replenishment_order_id,
            replenishment_item_id=item.id,
            product_id=item.product_id,
            product_variant_id=item.product_variant_id,
            quantity=quantity,
            operator="admin",
        )
        db.session.add(receipt)

        completed_orders, overstock_quantity = allocate_arrival(variant, quantity)
        db.session.add(
            InventoryMovement(
                product_id=item.product_id,
                product_variant_id=item.product_variant_id,
                movement_type="追貨到貨分配",
                quantity=quantity - overstock_quantity,
                reference_type="replenishment",
                reference_id=item.replenishment_order_id,
                source_no=item.replenishment_order.order_no,
                operator="admin",
                note=f"追貨到貨後依訂單建立時間 FIFO 分配。超額入庫 {overstock_quantity} 件。",
            )
        )
        refresh_replenishment_status(item.replenishment_order)
        db.session.commit()
        if completed_orders:
            flash(f"發現 {len(completed_orders)} 筆訂單已可出貨。", "success")
        else:
            flash("到貨已完成智慧分配。", "success")
    except Exception:
        db.session.rollback()
        current_app.logger.exception("Replenishment receive failed")
        flash("系統儲存失敗，請檢查資料是否完整。", "danger")
    return redirect(url_for("replenishment.detail", order_id=item.replenishment_order_id))


@replenishment_bp.route("/<int:order_id>/variants/<int:variant_id>/receive", methods=["POST"])
@login_required
def receive_variant(order_id, variant_id):
    replenishment_order = ReplenishmentOrder.query.get_or_404(order_id)
    if replenishment_order.status in CLOSED_STATUSES:
        flash("此追貨單已關閉，無法再登錄到貨。", "danger")
        return redirect(url_for("replenishment.detail", order_id=order_id))

    items = (
        ReplenishmentItem.query.filter_by(
            replenishment_order_id=order_id,
            product_variant_id=variant_id,
        )
        .order_by(ReplenishmentItem.id)
        .all()
    )
    if not items:
        flash("找不到追貨商品明細。", "danger")
        return redirect(url_for("replenishment.detail", order_id=order_id))

    mode = clean(request.form.get("mode"))
    total_remaining = sum(item.remaining_quantity or 0 for item in items)
    quantity = total_remaining if mode == "all" else parse_int(request.form.get("quantity"))
    if quantity <= 0:
        flash("請輸入正確到貨數量。", "danger")
        return redirect(url_for("replenishment.detail", order_id=order_id))

    first_item = items[0]
    variant = first_item.product_variant
    try:
        remaining_to_record = quantity
        for item in items:
            if remaining_to_record <= 0:
                break
            received_for_item = min(item.remaining_quantity or 0, remaining_to_record)
            if received_for_item <= 0:
                continue
            item.received_quantity = (item.received_quantity or 0) + received_for_item
            item.remaining_quantity = max((item.required_quantity or 0) - item.received_quantity, 0)
            db.session.add(
                ReplenishmentReceipt(
                    replenishment_order_id=order_id,
                    replenishment_item_id=item.id,
                    product_id=item.product_id,
                    product_variant_id=item.product_variant_id,
                    quantity=received_for_item,
                    operator="admin",
                )
            )
            remaining_to_record -= received_for_item

        if remaining_to_record > 0:
            first_item.received_quantity = (first_item.received_quantity or 0) + remaining_to_record
            first_item.remaining_quantity = max((first_item.required_quantity or 0) - first_item.received_quantity, 0)
            db.session.add(
                ReplenishmentReceipt(
                    replenishment_order_id=order_id,
                    replenishment_item_id=first_item.id,
                    product_id=first_item.product_id,
                    product_variant_id=first_item.product_variant_id,
                    quantity=remaining_to_record,
                    operator="admin",
                )
            )

        completed_orders, overstock_quantity = allocate_arrival(variant, quantity)
        db.session.add(
            InventoryMovement(
                product_id=first_item.product_id,
                product_variant_id=first_item.product_variant_id,
                movement_type="追貨到貨分配",
                quantity=quantity - overstock_quantity,
                reference_type="replenishment",
                reference_id=order_id,
                source_no=replenishment_order.order_no,
                operator="admin",
                note=f"追貨到貨後依訂單建立時間 FIFO 分配。超額入庫 {overstock_quantity} 件。",
            )
        )
        refresh_replenishment_status(replenishment_order)
        db.session.commit()
        if completed_orders:
            flash(f"發現 {len(completed_orders)} 筆訂單已可出貨。", "success")
        else:
            flash("到貨已完成智慧分配。", "success")
    except Exception:
        db.session.rollback()
        current_app.logger.exception("Replenishment grouped receive failed")
        flash("系統儲存失敗，請檢查資料是否完整。", "danger")
    return redirect(url_for("replenishment.detail", order_id=order_id))
