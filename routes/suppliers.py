from flask import Blueprint, current_app, flash, redirect, render_template, request, url_for
from sqlalchemy.exc import IntegrityError

from decorators import login_required
from config import Config
from extensions import db
from models import Product, Supplier
from pagination import get_page_args


suppliers_bp = Blueprint("suppliers", __name__, url_prefix="/suppliers")


def supplier_filters():
    return {
        "name": (request.args.get("name") or "").strip(),
        "contact_person": (request.args.get("contact_person") or "").strip(),
        "phone": (request.args.get("phone") or "").strip(),
    }


def apply_supplier_search(query, filters):
    if filters["name"]:
        query = query.filter(Supplier.name.like(f"%{filters['name']}%"))
    if filters["contact_person"]:
        query = query.filter(Supplier.contact_person.like(f"%{filters['contact_person']}%"))
    if filters["phone"]:
        query = query.filter(Supplier.phone.like(f"%{filters['phone']}%"))
    return query


def fill_supplier_from_form(supplier):
    supplier.name = (request.form.get("name") or "").strip()
    supplier.contact_person = (request.form.get("contact_person") or "").strip()
    supplier.phone = (request.form.get("phone") or "").strip()
    supplier.line = (request.form.get("line") or "").strip()
    supplier.address = (request.form.get("address") or "").strip()
    supplier.note = (request.form.get("note") or "").strip()


def supplier_name_exists(name, supplier_id=None):
    with db.session.no_autoflush:
        query = Supplier.query.filter_by(name=name)
        if supplier_id:
            query = query.filter(Supplier.id != supplier_id)
        return db.session.query(query.exists()).scalar()


def render_supplier_form(supplier, action, status_code=200, field_errors=None):
    field_errors = field_errors or {}
    return (
        render_template(
            "suppliers/form.html",
            supplier=supplier,
            action=action,
            errors=["請確認必填欄位是否已完整填寫。"] if field_errors else [],
            field_errors=field_errors,
        ),
        status_code,
    )


@suppliers_bp.route("/")
@login_required
def index():
    filters = supplier_filters()
    page, per_page = get_page_args(request, Config.DEFAULT_PAGE_SIZE, Config.PAGE_SIZE_OPTIONS)
    pagination = apply_supplier_search(Supplier.query, filters).order_by(Supplier.id.desc()).paginate(
        page=page,
        per_page=per_page,
        error_out=False,
    )
    return render_template(
        "suppliers/list.html",
        suppliers=pagination.items,
        pagination=pagination,
        page_size_options=Config.PAGE_SIZE_OPTIONS,
        filters=filters,
    )


@suppliers_bp.route("/new", methods=["GET", "POST"])
@login_required
def create():
    supplier = Supplier()
    if request.method == "POST":
        try:
            fill_supplier_from_form(supplier)
            if not supplier.name:
                db.session.rollback()
                return render_supplier_form(supplier, "新增廠商", 200, {"name": "請輸入廠商名稱"})
            if supplier_name_exists(supplier.name):
                db.session.rollback()
                return render_supplier_form(supplier, "新增廠商", 200, {"name": "廠商名稱已存在，請重新輸入。"})

            db.session.add(supplier)
            try:
                db.session.commit()
            except IntegrityError:
                db.session.rollback()
                return render_supplier_form(supplier, "新增廠商", 200, {"name": "廠商名稱已存在，請重新輸入。"})
        except Exception:
            db.session.rollback()
            current_app.logger.exception("Supplier create failed")
            return render_supplier_form(supplier, "新增廠商", 200, {"form": "系統儲存失敗，請檢查資料是否完整。"})

        flash("廠商已新增。", "success")
        return redirect(url_for("suppliers.index"))

    return render_supplier_form(supplier, "新增廠商")


@suppliers_bp.route("/<int:supplier_id>/edit", methods=["GET", "POST"])
@login_required
def edit(supplier_id):
    supplier = Supplier.query.get_or_404(supplier_id)
    if request.method == "POST":
        try:
            fill_supplier_from_form(supplier)
            if not supplier.name:
                db.session.rollback()
                return render_supplier_form(supplier, "編輯廠商", 200, {"name": "請輸入廠商名稱"})
            if supplier_name_exists(supplier.name, supplier.id):
                db.session.rollback()
                return render_supplier_form(supplier, "編輯廠商", 200, {"name": "廠商名稱已存在，請重新輸入。"})

            try:
                db.session.commit()
            except IntegrityError:
                db.session.rollback()
                return render_supplier_form(supplier, "編輯廠商", 200, {"name": "廠商名稱已存在，請重新輸入。"})
        except Exception:
            db.session.rollback()
            current_app.logger.exception("Supplier update failed")
            return render_supplier_form(supplier, "編輯廠商", 200, {"form": "系統儲存失敗，請檢查資料是否完整。"})

        flash("廠商已更新。", "success")
        return redirect(url_for("suppliers.index"))

    return render_supplier_form(supplier, "編輯廠商")


@suppliers_bp.route("/<int:supplier_id>/delete", methods=["POST"])
@login_required
def delete(supplier_id):
    supplier = Supplier.query.get_or_404(supplier_id)
    if Product.query.filter_by(supplier_id=supplier.id).first():
        flash("此廠商已有商品使用，無法刪除。", "danger")
        return redirect(url_for("suppliers.index"))

    try:
        db.session.delete(supplier)
        db.session.commit()
        flash("廠商已刪除。", "success")
    except Exception:
        db.session.rollback()
        current_app.logger.exception("Supplier delete failed")
        flash("系統儲存失敗，請檢查資料是否完整。", "danger")
    return redirect(url_for("suppliers.index"))
