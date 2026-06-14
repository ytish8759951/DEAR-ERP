import os
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from uuid import uuid4

from flask import Blueprint, current_app, flash, jsonify, redirect, render_template, request, url_for
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from werkzeug.utils import secure_filename

from config import Config
from decorators import login_required
from extensions import db
from models import Color, Location, OtherSpec, Product, ProductVariant, Size, Supplier
from pagination import get_page_args
from services.gemini_service import GeminiServiceError, analyze_product_image


products_bp = Blueprint("products", __name__, url_prefix="/products")
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "webp"}
TAIPEI_TZ = timezone(timedelta(hours=8))
SKU_RETRY_LIMIT = 10
SAVE_FAILED_ERROR = "系統儲存失敗，請檢查資料是否完整。"


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def save_image(file_storage):
    if not file_storage or not file_storage.filename:
        return None
    if not allowed_file(file_storage.filename):
        flash("商品圖片格式僅支援 png、jpg、jpeg、gif、webp。", "danger")
        return None

    filename = secure_filename(file_storage.filename)
    ext = filename.rsplit(".", 1)[1].lower()
    stored_name = f"{uuid4().hex}.{ext}"
    upload_dir = current_app.config["PRODUCT_UPLOAD_FOLDER"]
    upload_dir.mkdir(parents=True, exist_ok=True)
    file_storage.save(upload_dir / stored_name)
    return f"uploads/products/{stored_name}"


def today_sku_prefix():
    return datetime.now(TAIPEI_TZ).strftime("%Y%m%d")


def generate_next_product_sku():
    prefix = today_sku_prefix()
    latest_product = (
        Product.query.with_entities(Product.sku)
        .filter(Product.sku.like(f"{prefix}%"))
        .order_by(Product.sku.desc())
        .first()
    )
    latest_sequence = 0

    if latest_product:
        suffix = (latest_product.sku or "")[len(prefix) :]
        if suffix.isdigit():
            latest_sequence = int(suffix)

    return f"{prefix}{latest_sequence + 1:02d}"


def parse_money(field_name):
    raw_value = (request.form.get(field_name) or "0").strip()
    try:
        value = Decimal(raw_value)
    except InvalidOperation:
        return Decimal("0")
    return value if value >= 0 else Decimal("0")


def validate_money_field(field_name, label):
    raw_value = (request.form.get(field_name) or "").strip()
    if raw_value == "":
        return f"請輸入{label}"
    try:
        value = Decimal(raw_value)
    except InvalidOperation:
        return f"{label}格式錯誤"
    if value < 0:
        return f"{label}不可小於 0"
    return None


def parse_int_list(field_name):
    values = []
    for item in request.form.getlist(field_name):
        try:
            values.append(int(item))
        except (TypeError, ValueError):
            continue
    return values


def load_form_options():
    return {
        "locations": Location.query.order_by(Location.id).all(),
        "colors": Color.query.order_by(Color.id).all(),
        "sizes": Size.query.order_by(Size.id).all(),
        "other_specs": OtherSpec.query.order_by(OtherSpec.id).all(),
        "suppliers": Supplier.query.order_by(Supplier.name).all(),
    }


def get_product_search_filters():
    return {
        "sku": (request.args.get("sku") or "").strip(),
        "name": (request.args.get("name") or "").strip(),
        "supplier": (request.args.get("supplier") or "").strip(),
        "location_id": (request.args.get("location_id") or "").strip(),
    }


def apply_product_search(query, filters):
    if filters["sku"]:
        query = query.filter(Product.sku.like(f"%{filters['sku']}%"))
    if filters["name"]:
        query = query.filter(Product.name.like(f"%{filters['name']}%"))
    if filters["supplier"]:
        query = query.join(Product.supplier).filter(Supplier.name.like(f"%{filters['supplier']}%"))
    if filters["location_id"]:
        try:
            location_id = int(filters["location_id"])
        except ValueError:
            location_id = None
        if location_id:
            query = query.filter(Product.location_id == location_id)
    return query


def cleanup_orphan_product_rows():
    db.session.execute(
        text(
            """
            DELETE FROM product_other_specs
            WHERE product_id NOT IN (SELECT id FROM products)
            """
        )
    )
    db.session.execute(
        text(
            """
            DELETE FROM product_variants
            WHERE product_id NOT IN (SELECT id FROM products)
            """
        )
    )


def is_sku_integrity_error(error):
    detail = str(getattr(error, "orig", error))
    return "products.sku" in detail


def integrity_error_message(error):
    if is_sku_integrity_error(error):
        return "商品編號已存在，請使用其他編號。"
    return "商品資料寫入失敗，請檢查欄位後再試一次。"


def sync_product_from_form(product, image_filename=None, keep_sku=True):
    if not keep_sku:
        product.sku = (request.form.get("sku") or "").strip()

    product.name = (request.form.get("name") or "").strip()
    product.price = parse_money("price")
    product.cost = parse_money("cost")
    product.supply_mode = (request.form.get("supply_mode") or "一般商品").strip()
    if product.supply_mode not in {"一般商品", "出清商品"}:
        product.supply_mode = "一般商品"
    try:
        product.location_id = int(request.form.get("location_id") or 0) or None
    except (TypeError, ValueError):
        product.location_id = None
    try:
        product.supplier_id = int(request.form.get("supplier_id") or 0) or None
    except (TypeError, ValueError):
        product.supplier_id = None
    product.size_chart = (request.form.get("size_chart") or "").strip()
    product.ai_description = (request.form.get("ai_description") or "").strip()
    product.line_group_text = (request.form.get("line_group_text") or "").strip()
    product.live_script = (request.form.get("live_script") or "").strip()

    if image_filename:
        product.image_path = image_filename

    selected_other_spec_ids = parse_int_list("other_spec_ids")
    if selected_other_spec_ids:
        product.other_specs = OtherSpec.query.filter(OtherSpec.id.in_(selected_other_spec_ids)).all()
    else:
        product.other_specs = []


def sync_variants(product):
    color_ids = parse_int_list("color_ids")
    size_ids = parse_int_list("size_ids")
    existing = {(variant.color_id, variant.size_id): variant for variant in product.variants}
    next_variants = []

    for color_id in color_ids:
        for size_id in size_ids:
            key = (color_id, size_id)
            variant = existing.get(key)
            if not variant:
                variant = ProductVariant(color_id=color_id, size_id=size_id)

            try:
                stock = int(request.form.get(f"stock_{color_id}_{size_id}") or 0)
            except (TypeError, ValueError):
                stock = 0
            variant.stock = max(stock, 0)
            next_variants.append(variant)

    product.variants = next_variants


def render_product_form(product, action, status_code=200, is_create=False, field_errors=None):
    field_errors = field_errors or {}
    next_sku = product.sku
    if is_create and not next_sku:
        next_sku = generate_next_product_sku()

    return (
        render_template(
            "products/form.html",
            product=product,
            action=action,
            is_create=is_create,
            next_sku=next_sku,
            errors=["請確認必填欄位是否已完整填寫。"] if field_errors else [],
            field_errors=field_errors,
            **load_form_options(),
        ),
        status_code,
    )


def validate_product_form(product, require_sku=True):
    field_errors = {}
    if require_sku and not (product.sku or "").strip():
        field_errors["sku"] = "請輸入商品編號"
    if not (product.name or "").strip():
        field_errors["name"] = "請輸入商品名稱"
    if not product.supplier_id:
        field_errors["supplier_id"] = "請選擇廠商"
    if not product.location_id:
        field_errors["location_id"] = "請選擇放置位置"
    price_error = validate_money_field("price", "售價")
    if price_error:
        field_errors["price"] = price_error
    cost_error = validate_money_field("cost", "成本")
    if cost_error:
        field_errors["cost"] = cost_error
    color_ids = parse_int_list("color_ids")
    size_ids = parse_int_list("size_ids")
    if not color_ids or not size_ids:
        field_errors["variants"] = "請至少加入一個規格庫存"
    else:
        for color_id in color_ids:
            for size_id in size_ids:
                raw_stock = (request.form.get(f"stock_{color_id}_{size_id}") or "").strip()
                if raw_stock == "":
                    field_errors["variants"] = "規格數量不可為空"
                    return field_errors
                try:
                    stock = int(raw_stock)
                except (TypeError, ValueError):
                    field_errors["variants"] = "規格數量格式錯誤"
                    return field_errors
                if stock < 0:
                    field_errors["variants"] = "規格數量不可小於 0"
                    return field_errors
    return field_errors


@products_bp.route("/")
@login_required
def index():
    filters = get_product_search_filters()
    query = apply_product_search(Product.query, filters)
    page, per_page = get_page_args(request, Config.DEFAULT_PAGE_SIZE, Config.PAGE_SIZE_OPTIONS)
    pagination = query.order_by(Product.created_at.desc()).paginate(page=page, per_page=per_page, error_out=False)
    locations = Location.query.order_by(Location.id).all()
    return render_template(
        "products/list.html",
        products=pagination.items,
        pagination=pagination,
        page_size_options=Config.PAGE_SIZE_OPTIONS,
        locations=locations,
        filters=filters,
    )


@products_bp.route("/new", methods=["GET", "POST"])
@login_required
def create():
    product = Product()

    if request.method == "POST":
        try:
            image_filename = save_image(request.files.get("image"))

            for _attempt in range(SKU_RETRY_LIMIT):
                product = Product(sku=generate_next_product_sku())
                sync_product_from_form(product, image_filename=image_filename, keep_sku=True)
                field_errors = validate_product_form(product)
                if field_errors:
                    db.session.rollback()
                    return render_product_form(product, "新增商品", 200, is_create=True, field_errors=field_errors)

                cleanup_orphan_product_rows()
                sync_variants(product)
                db.session.add(product)

                try:
                    db.session.commit()
                    flash("商品已新增。", "success")
                    return redirect(url_for("products.index"))
                except IntegrityError as error:
                    db.session.rollback()
                    if is_sku_integrity_error(error):
                        continue
                    field_errors = {"sku": integrity_error_message(error)}
                    product.sku = generate_next_product_sku()
                    return render_product_form(product, "新增商品", 200, is_create=True, field_errors=field_errors)

            product = Product(sku=generate_next_product_sku())
            return render_product_form(product, "新增商品", 200, is_create=True, field_errors={"sku": "商品編號產生失敗，請重新儲存。"})
        except Exception:
            db.session.rollback()
            current_app.logger.exception("Product create failed")
            return render_product_form(product, "新增商品", 200, is_create=True, field_errors={"form": SAVE_FAILED_ERROR})

    product.sku = generate_next_product_sku()
    return render_product_form(product, "新增商品", is_create=True)


@products_bp.route("/<int:product_id>/edit", methods=["GET", "POST"])
@login_required
def edit(product_id):
    product = Product.query.get_or_404(product_id)
    if request.method == "POST":
        try:
            image_filename = save_image(request.files.get("image"))
            sync_product_from_form(product, image_filename=image_filename, keep_sku=True)

            field_errors = validate_product_form(product)
            if field_errors:
                db.session.rollback()
                return render_product_form(product, "編輯商品", 200, field_errors=field_errors)

            sync_variants(product)
            db.session.commit()
        except IntegrityError as error:
            db.session.rollback()
            return render_product_form(product, "編輯商品", 200, field_errors={"sku": integrity_error_message(error)})
        except Exception:
            db.session.rollback()
            current_app.logger.exception("Product update failed")
            return render_product_form(product, "編輯商品", 200, field_errors={"form": SAVE_FAILED_ERROR})

        flash("商品已更新。", "success")
        return redirect(url_for("products.index"))

    return render_product_form(product, "編輯商品")


@products_bp.route("/<int:product_id>/delete", methods=["POST"])
@login_required
def delete(product_id):
    product = Product.query.get_or_404(product_id)
    try:
        db.session.delete(product)
        db.session.commit()
        flash("商品已刪除。", "success")
    except Exception:
        db.session.rollback()
        current_app.logger.exception("Product delete failed")
        flash(SAVE_FAILED_ERROR, "danger")
    return redirect(url_for("products.index"))


@products_bp.route("/<int:product_id>/supply-mode", methods=["POST"])
@login_required
def update_supply_mode(product_id):
    product = Product.query.get_or_404(product_id)
    mode = (request.form.get("supply_mode") or "").strip()
    if mode not in {"一般商品", "出清商品"}:
        flash("供貨模式不正確。", "danger")
        return redirect(url_for("products.index"))
    try:
        product.supply_mode = mode
        db.session.commit()
        flash(f"商品已更新為{mode}。", "success")
    except Exception:
        db.session.rollback()
        current_app.logger.exception("Product supply mode update failed")
        flash(SAVE_FAILED_ERROR, "danger")
    return redirect(url_for("products.index"))


@products_bp.route("/ai/analyze", methods=["POST"])
@login_required
def ai_analyze():
    try:
        image = request.files.get("image")
        image_path = None
        temp_filename = None

        if not image or not image.filename:
            return jsonify({"ok": False, "message": "請先上傳商品圖片"}), 400
        if not allowed_file(image.filename):
            return jsonify({"ok": False, "message": "商品圖片格式僅支援 png、jpg、jpeg、gif、webp。"}), 400
        ext = secure_filename(image.filename).rsplit(".", 1)[1].lower()
        temp_filename = f"ai_tmp_{uuid4().hex}.{ext}"
        current_app.config["PRODUCT_UPLOAD_FOLDER"].mkdir(parents=True, exist_ok=True)
        image_path = os.path.join(current_app.config["PRODUCT_UPLOAD_FOLDER"], temp_filename)
        image.save(image_path)

        result = analyze_product_image(image_path)

        if image_path and os.path.exists(image_path):
            os.remove(image_path)

        return jsonify({"ok": True, "message": "AI辨識成功", "data": result})
    except GeminiServiceError as error:
        if image_path and os.path.exists(image_path):
            os.remove(image_path)
        current_app.logger.exception("AI product analysis failed: %s", getattr(error, "detail", str(error)))
        return jsonify({"ok": False, "message": str(error) or "AI服務暫時無法使用"}), 200
    except Exception:
        current_app.logger.exception("AI product analysis failed")
        return jsonify({"ok": False, "message": "AI辨識失敗，請稍後再試。"}), 500


@products_bp.route("/ai-assistant")
@login_required
def ai_assistant():
    return render_template("products/ai_assistant.html")
