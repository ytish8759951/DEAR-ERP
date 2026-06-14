from flask import Blueprint, current_app, flash, redirect, render_template, request, url_for
from sqlalchemy.exc import IntegrityError

from decorators import login_required
from extensions import db
from models import Color, Location, OtherSpec, Size


settings_bp = Blueprint("settings", __name__, url_prefix="/settings")


SPEC_MODELS = {
    "colors": (Color, "顏色"),
    "sizes": (Size, "尺寸"),
    "other_specs": (OtherSpec, "其他規格"),
}


def create_item(model, name):
    name = (name or "").strip()
    if not name:
        return False, {"name": "名稱不可空白"}
    if model.query.filter_by(name=name).first():
        return False, {"name": "此名稱已存在。"}

    db.session.add(model(name=name))
    try:
        db.session.commit()
        flash("新增成功。", "success")
        return True, {}
    except IntegrityError:
        db.session.rollback()
        return False, {"name": "此名稱已存在。"}
    except Exception:
        db.session.rollback()
        current_app.logger.exception("Setting create failed")
        return False, {"name": "系統儲存失敗，請檢查資料是否完整。"}


def update_item(model, item_id, name):
    item = model.query.get_or_404(item_id)
    item.name = (name or "").strip()
    if not item.name:
        return False, {"name": "名稱不可空白"}

    try:
        db.session.commit()
        flash("更新成功。", "success")
        return True, {}
    except IntegrityError:
        db.session.rollback()
        return False, {"name": "此名稱已存在。"}
    except Exception:
        db.session.rollback()
        current_app.logger.exception("Setting update failed")
        return False, {"name": "系統儲存失敗，請檢查資料是否完整。"}


def delete_item(model, item_id):
    item = model.query.get_or_404(item_id)
    db.session.delete(item)
    try:
        db.session.commit()
        flash("刪除成功。", "success")
    except IntegrityError:
        db.session.rollback()
        flash("此資料已被商品使用，無法刪除。", "danger")
    except Exception:
        db.session.rollback()
        current_app.logger.exception("Setting delete failed")
        flash("系統儲存失敗，請檢查資料是否完整。", "danger")


@settings_bp.route("/locations", methods=["GET", "POST"])
@login_required
def locations():
    if request.method == "POST":
        ok, field_errors = create_item(Location, request.form.get("name", ""))
        if ok:
            return redirect(url_for("settings.locations"))
        items = Location.query.order_by(Location.id).all()
        return render_template("settings/locations.html", items=items, errors=["請確認必填欄位是否已完整填寫。"], field_errors=field_errors), 200

    items = Location.query.order_by(Location.id).all()
    return render_template("settings/locations.html", items=items, errors=[], field_errors={})


@settings_bp.route("/locations/<int:item_id>/edit", methods=["POST"])
@login_required
def edit_location(item_id):
    ok, field_errors = update_item(Location, item_id, request.form.get("name", ""))
    if ok:
        return redirect(url_for("settings.locations"))
    items = Location.query.order_by(Location.id).all()
    return render_template("settings/locations.html", items=items, errors=["請確認必填欄位是否已完整填寫。"], field_errors=field_errors), 200


@settings_bp.route("/locations/<int:item_id>/delete", methods=["POST"])
@login_required
def delete_location(item_id):
    delete_item(Location, item_id)
    return redirect(url_for("settings.locations"))


@settings_bp.route("/specs/<kind>", methods=["GET", "POST"])
@login_required
def specs(kind):
    model, title = SPEC_MODELS.get(kind, SPEC_MODELS["colors"])
    if request.method == "POST":
        ok, field_errors = create_item(model, request.form.get("name", ""))
        if ok:
            return redirect(url_for("settings.specs", kind=kind))
        items = model.query.order_by(model.id).all()
        return render_template("settings/specs.html", items=items, kind=kind, title=title, errors=["請確認必填欄位是否已完整填寫。"], field_errors=field_errors), 200

    items = model.query.order_by(model.id).all()
    return render_template("settings/specs.html", items=items, kind=kind, title=title, errors=[], field_errors={})


@settings_bp.route("/specs/<kind>/<int:item_id>/edit", methods=["POST"])
@login_required
def edit_spec(kind, item_id):
    model, _title = SPEC_MODELS.get(kind, SPEC_MODELS["colors"])
    ok, field_errors = update_item(model, item_id, request.form.get("name", ""))
    if ok:
        return redirect(url_for("settings.specs", kind=kind))
    items = model.query.order_by(model.id).all()
    _model, title = SPEC_MODELS.get(kind, SPEC_MODELS["colors"])
    return render_template("settings/specs.html", items=items, kind=kind, title=title, errors=["請確認必填欄位是否已完整填寫。"], field_errors=field_errors), 200


@settings_bp.route("/specs/<kind>/<int:item_id>/delete", methods=["POST"])
@login_required
def delete_spec(kind, item_id):
    model, _title = SPEC_MODELS.get(kind, SPEC_MODELS["colors"])
    delete_item(model, item_id)
    return redirect(url_for("settings.specs", kind=kind))
