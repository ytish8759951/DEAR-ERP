import json
import os
import tempfile

from flask import Blueprint, current_app, jsonify, request

from decorators import login_required
from services.gemini_service import (
    AI_UNAVAILABLE_MESSAGE,
    GeminiServiceError,
    generate_group_buy_text,
    generate_live_script,
    generate_product_description,
    generate_product_name_suggestions,
    generate_size_chart,
)


ai_bp = Blueprint("ai", __name__, url_prefix="/api/ai")


def clean(value):
    return (value or "").strip()


def _json_error(message=AI_UNAVAILABLE_MESSAGE, status_code=200):
    return jsonify({"success": False, "content": "", "message": message}), status_code


def _save_temp_image(file_storage):
    if not file_storage or not file_storage.filename:
        return None
    suffix = os.path.splitext(file_storage.filename)[1].lower()
    if suffix not in {".jpg", ".jpeg", ".png", ".webp"}:
        raise GeminiServiceError("商品圖片格式僅支援 jpg、jpeg、png、webp")
    temp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    temp.close()
    file_storage.save(temp.name)
    return temp.name


@ai_bp.route("/product-description", methods=["POST"])
@login_required
def product_description():
    data = request.get_json(silent=True) or {}
    product_name = clean(data.get("product_name"))
    if not product_name:
        return _json_error("請輸入商品名稱")
    try:
        content = generate_product_description(product_name)
        return jsonify({"success": True, "content": content})
    except GeminiServiceError as error:
        current_app.logger.exception("Gemini product description failed: %s", getattr(error, "detail", str(error)))
        return _json_error(str(error))
    except Exception:
        current_app.logger.exception("Gemini product description failed")
        return _json_error()


@ai_bp.route("/group-buy", methods=["POST"])
@login_required
def group_buy():
    data = request.get_json(silent=True) or {}
    product_name = clean(data.get("product_name"))
    price = clean(data.get("price"))
    if not product_name:
        return _json_error("請輸入商品名稱")
    try:
        content = generate_group_buy_text(product_name, price or "未定")
        return jsonify({"success": True, "content": content})
    except GeminiServiceError as error:
        current_app.logger.exception("Gemini group buy text failed: %s", getattr(error, "detail", str(error)))
        return _json_error(str(error))
    except Exception:
        current_app.logger.exception("Gemini group buy text failed")
        return _json_error()


@ai_bp.route("/live-script", methods=["POST"])
@login_required
def live_script():
    data = request.get_json(silent=True) or {}
    product_name = clean(data.get("product_name"))
    if not product_name:
        return _json_error("請輸入商品名稱")
    try:
        content = generate_live_script(product_name)
        return jsonify({"success": True, "content": content})
    except GeminiServiceError as error:
        current_app.logger.exception("Gemini live script failed: %s", getattr(error, "detail", str(error)))
        return _json_error(str(error))


@ai_bp.route("/size-chart", methods=["POST"])
@login_required
def size_chart():
    data = request.get_json(silent=True) or {}
    product_name = clean(data.get("product_name"))
    if not product_name:
        return _json_error("請先輸入商品名稱")
    try:
        content = generate_size_chart(product_name)
        return jsonify({"success": True, "content": content})
    except GeminiServiceError as error:
        current_app.logger.exception("Gemini size chart failed: %s", getattr(error, "detail", str(error)))
        return _json_error(str(error))
    except Exception:
        current_app.logger.exception("Gemini size chart failed")
        return _json_error()
    except Exception:
        current_app.logger.exception("Gemini live script failed")
        return _json_error()


@ai_bp.route("/product-name-suggestions", methods=["POST"])
@login_required
def product_name_suggestions():
    temp_path = None
    try:
        product_name = clean(request.form.get("product_name"))
        recognized_raw = request.form.get("recognized_data") or "{}"
        try:
            recognized_data = json.loads(recognized_raw)
        except Exception:
            recognized_data = {}
        temp_path = _save_temp_image(request.files.get("image"))
        suggestions = generate_product_name_suggestions(
            product_name=product_name,
            recognized_data=recognized_data,
            image_path=temp_path,
        )
        return jsonify({"success": True, "suggestions": suggestions})
    except GeminiServiceError as error:
        current_app.logger.exception("Gemini product name suggestions failed: %s", getattr(error, "detail", str(error)))
        return jsonify({"success": False, "suggestions": [], "message": str(error)})
    except Exception:
        current_app.logger.exception("Gemini product name suggestions failed")
        return jsonify({"success": False, "suggestions": [], "message": AI_UNAVAILABLE_MESSAGE})
    finally:
        if temp_path:
            try:
                os.remove(temp_path)
            except OSError:
                pass
