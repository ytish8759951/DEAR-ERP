from flask import Blueprint, render_template, request
from sqlalchemy import func, or_

from config import Config
from decorators import login_required
from extensions import db
from models import (
    Color,
    Customer,
    DefectiveInventory,
    Employee,
    InventoryMovement,
    Location,
    Order,
    Product,
    ProductVariant,
    Return,
    ReturnItem,
    Size,
    Supplier,
)
from pagination import get_page_args


operations_bp = Blueprint("operations", __name__)


def clean(value):
    return (value or "").strip()


def inventory_filters():
    return {
        "sku": clean(request.args.get("sku")),
        "name": clean(request.args.get("name")),
        "color_id": clean(request.args.get("color_id")),
        "size_id": clean(request.args.get("size_id")),
        "location_id": clean(request.args.get("location_id")),
        "supplier_id": clean(request.args.get("supplier_id")),
        "stock_status": clean(request.args.get("stock_status")),
    }


def filter_int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def defective_quantity_subquery():
    return (
        db.session.query(
            DefectiveInventory.product_variant_id.label("variant_id"),
            func.coalesce(func.sum(DefectiveInventory.quantity), 0).label("defective_quantity"),
        )
        .group_by(DefectiveInventory.product_variant_id)
        .subquery()
    )


def inventory_query(filters):
    defective_sq = defective_quantity_subquery()
    query = (
        db.session.query(
            ProductVariant,
            func.coalesce(defective_sq.c.defective_quantity, 0).label("defective_quantity"),
        )
        .join(ProductVariant.product)
        .outerjoin(defective_sq, defective_sq.c.variant_id == ProductVariant.id)
    )
    if filters["sku"]:
        query = query.filter(Product.sku.like(f"%{filters['sku']}%"))
    if filters["name"]:
        query = query.filter(Product.name.like(f"%{filters['name']}%"))
    color_id = filter_int(filters["color_id"])
    if color_id:
        query = query.filter(ProductVariant.color_id == color_id)
    size_id = filter_int(filters["size_id"])
    if size_id:
        query = query.filter(ProductVariant.size_id == size_id)
    location_id = filter_int(filters["location_id"])
    if location_id:
        query = query.filter(Product.location_id == location_id)
    supplier_id = filter_int(filters["supplier_id"])
    if supplier_id:
        query = query.filter(Product.supplier_id == supplier_id)

    status = filters["stock_status"]
    if status == "in_stock":
        query = query.filter(ProductVariant.stock > 0)
    elif status == "out_of_stock":
        query = query.filter(ProductVariant.stock <= 0)
    elif status == "low_stock":
        query = query.filter(ProductVariant.stock <= Config.LOW_STOCK_THRESHOLD)
    elif status == "has_defective":
        query = query.filter(func.coalesce(defective_sq.c.defective_quantity, 0) > 0)
    return query.order_by(Product.sku, ProductVariant.id)


def load_inventory_options():
    return {
        "colors": Color.query.order_by(Color.name).all(),
        "sizes": Size.query.order_by(Size.name).all(),
        "locations": Location.query.order_by(Location.name).all(),
        "suppliers": Supplier.query.order_by(Supplier.name).all(),
        "stock_status_options": [
            ("", "全部"),
            ("in_stock", "有庫存"),
            ("out_of_stock", "缺貨"),
            ("low_stock", "低庫存"),
            ("has_defective", "有瑕疵庫存"),
        ],
    }


def page_url(endpoint, pagination, page, filters=None):
    params = dict(filters or {})
    params["page"] = page
    params["per_page"] = pagination.per_page
    return endpoint, params


@operations_bp.route("/customers/")
@login_required
def customers():
    page, per_page = get_page_args(request, Config.DEFAULT_PAGE_SIZE, Config.PAGE_SIZE_OPTIONS)
    pagination = Customer.query.order_by(Customer.created_at.desc()).paginate(
        page=page,
        per_page=per_page,
        error_out=False,
    )
    return render_template(
        "operations/customers.html",
        customers=pagination.items,
        pagination=pagination,
        page_size_options=Config.PAGE_SIZE_OPTIONS,
    )


@operations_bp.route("/employees/")
@login_required
def employees():
    page, per_page = get_page_args(request, Config.DEFAULT_PAGE_SIZE, Config.PAGE_SIZE_OPTIONS)
    pagination = Employee.query.order_by(Employee.created_at.desc()).paginate(
        page=page,
        per_page=per_page,
        error_out=False,
    )
    return render_template(
        "operations/employees.html",
        employees=pagination.items,
        pagination=pagination,
        page_size_options=Config.PAGE_SIZE_OPTIONS,
    )


@operations_bp.route("/inventory/")
@login_required
def inventory():
    filters = inventory_filters()
    page, per_page = get_page_args(request, Config.DEFAULT_PAGE_SIZE, Config.PAGE_SIZE_OPTIONS)
    pagination = inventory_query(filters).paginate(page=page, per_page=per_page, error_out=False)
    return render_template(
        "operations/inventory.html",
        rows=pagination.items,
        pagination=pagination,
        filters=filters,
        page_size_options=Config.PAGE_SIZE_OPTIONS,
        low_stock_threshold=Config.LOW_STOCK_THRESHOLD,
        **load_inventory_options(),
    )


@operations_bp.route("/inventory/defective")
@login_required
def defective_inventory():
    page, per_page = get_page_args(request, Config.DEFAULT_PAGE_SIZE, Config.PAGE_SIZE_OPTIONS)
    query = (
        ReturnItem.query.join(ReturnItem.return_record)
        .join(ReturnItem.product)
        .join(ReturnItem.product_variant)
        .filter(Return.return_type == "瑕疵退貨")
        .order_by(Return.created_at.desc(), ReturnItem.id.desc())
    )
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)
    return render_template(
        "operations/defective_inventory.html",
        return_items=pagination.items,
        pagination=pagination,
        page_size_options=Config.PAGE_SIZE_OPTIONS,
    )


@operations_bp.route("/inventory/logs")
@login_required
def inventory_logs():
    page, per_page = get_page_args(request, Config.DEFAULT_PAGE_SIZE, Config.PAGE_SIZE_OPTIONS)
    query = InventoryMovement.query.order_by(InventoryMovement.created_at.desc(), InventoryMovement.id.desc())
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)
    return render_template(
        "operations/inventory_logs.html",
        logs=pagination.items,
        pagination=pagination,
        page_size_options=Config.PAGE_SIZE_OPTIONS,
    )


@operations_bp.route("/orders/")
@login_required
def orders():
    page, per_page = get_page_args(request, Config.DEFAULT_PAGE_SIZE, Config.PAGE_SIZE_OPTIONS)
    pagination = Order.query.order_by(Order.created_at.desc()).paginate(
        page=page,
        per_page=per_page,
        error_out=False,
    )
    return render_template(
        "operations/orders.html",
        orders=pagination.items,
        pagination=pagination,
        page_size_options=Config.PAGE_SIZE_OPTIONS,
    )
