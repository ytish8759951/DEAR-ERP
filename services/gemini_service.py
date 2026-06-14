import json
import logging
import re
from pathlib import Path

from config import GEMINI_API_KEY
from extensions import db
from models import SystemSetting, utc_now


MODEL_NAME = "gemini-2.5-flash"
AI_UNAVAILABLE_MESSAGE = "AI服務暫時無法使用"

logger = logging.getLogger(__name__)


class GeminiServiceError(Exception):
    def __init__(self, message=AI_UNAVAILABLE_MESSAGE, detail=None):
        super().__init__(message)
        self.detail = detail or message


def _setting(key, default=""):
    try:
        row = SystemSetting.query.filter_by(key=key).first()
        return row.value if row and row.value is not None else default
    except Exception:
        return default


def _save_setting(key, value):
    row = SystemSetting.query.filter_by(key=key).first()
    if not row:
        row = SystemSetting(key=key)
        db.session.add(row)
    row.value = value
    row.updated_at = utc_now()
    return row


def get_ai_settings():
    api_key = _setting("gemini_api_key", "") or GEMINI_API_KEY
    return {
        "api_key": api_key,
        "api_key_source": "database" if _setting("gemini_api_key", "") else "config",
        "model": _setting("gemini_model", MODEL_NAME) or MODEL_NAME,
        "last_tested_at": _setting("gemini_last_tested_at", ""),
        "connection_status": _setting("gemini_connection_status", "尚未測試"),
        "last_error": _setting("gemini_last_error", ""),
    }


def update_ai_api_key(api_key):
    _save_setting("gemini_api_key", (api_key or "").strip())
    _save_setting("gemini_model", MODEL_NAME)
    _save_setting("gemini_connection_status", "尚未測試")
    _save_setting("gemini_last_error", "")
    db.session.commit()


def masked_api_key(api_key):
    if not api_key:
        return ""
    if len(api_key) <= 10:
        return "*" * len(api_key)
    return f"{api_key[:6]}{'*' * max(len(api_key) - 10, 4)}{api_key[-4:]}"


def _client():
    try:
        from google import genai
    except Exception as error:
        logger.exception("Google GenAI SDK import failed")
        raise GeminiServiceError("AI SDK 尚未安裝或載入失敗", detail=repr(error)) from error

    settings = get_ai_settings()
    api_key = settings["api_key"]
    if not api_key:
        raise GeminiServiceError("尚未設定 Google AI API Key", detail="Missing GEMINI_API_KEY")

    try:
        return genai.Client(api_key=api_key)
    except Exception as error:
        logger.exception("Google GenAI client initialization failed")
        raise GeminiServiceError("Google AI API Key 無法初始化", detail=repr(error)) from error


def _response_text(response):
    text = (getattr(response, "text", "") or "").strip()
    if text:
        return text
    candidates = getattr(response, "candidates", None) or []
    parts = []
    for candidate in candidates:
        content = getattr(candidate, "content", None)
        for part in getattr(content, "parts", []) or []:
            value = getattr(part, "text", None)
            if value:
                parts.append(value)
    return "\n".join(parts).strip()


def _generate(prompt):
    try:
        client = _client()
        response = client.models.generate_content(model=MODEL_NAME, contents=prompt)
        content = _response_text(response)
    except GeminiServiceError:
        raise
    except Exception as error:
        logger.exception("Gemini text generation failed")
        raise GeminiServiceError(AI_UNAVAILABLE_MESSAGE, detail=repr(error)) from error

    if not content:
        raise GeminiServiceError("AI 沒有回傳內容", detail="Empty Gemini response")
    return content


def _image_part(image_path):
    path = Path(image_path)
    mime_type = {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".webp": "image/webp",
    }.get(path.suffix.lower())
    if not mime_type:
        raise GeminiServiceError("商品圖片格式僅支援 jpg、jpeg、png、webp", detail=f"Unsupported image suffix: {path.suffix}")
    try:
        from google.genai import types
        return types.Part.from_bytes(data=path.read_bytes(), mime_type=mime_type)
    except GeminiServiceError:
        raise
    except Exception as error:
        logger.exception("Gemini image payload creation failed")
        raise GeminiServiceError("圖片讀取失敗", detail=repr(error)) from error


def _generate_with_optional_image(prompt, image_path=None):
    try:
        contents = [prompt, _image_part(image_path)] if image_path else prompt
        client = _client()
        response = client.models.generate_content(model=MODEL_NAME, contents=contents)
        content = _response_text(response)
    except GeminiServiceError:
        raise
    except Exception as error:
        logger.exception("Gemini image/text generation failed")
        raise GeminiServiceError(AI_UNAVAILABLE_MESSAGE, detail=repr(error)) from error

    if not content:
        raise GeminiServiceError("AI 沒有回傳內容", detail="Empty Gemini response")
    return content


def _extract_json_object(text):
    raw_text = (text or "").strip()
    text = raw_text
    if text.startswith("```"):
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:].strip()
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        text = text[start : end + 1]
    try:
        return json.loads(text)
    except Exception as error:
        logger.exception("Gemini JSON parse failed. Raw response: %s", raw_text)
        raise GeminiServiceError("AI 回傳格式無法解析", detail=f"{repr(error)}; raw={raw_text[:1000]}") from error


def generate_size_chart(product_name):
    prompt = f"""你是韓系女裝商品資料助理。

商品名稱：
{product_name}

請產生適合此商品的尺寸表，使用繁體中文。

格式：
尺寸：
肩寬：
胸圍：
袖長：
衣長：
腰圍：
臀圍：
褲長：

若欄位不適用請填「-」。
"""
    return _generate(prompt)


def generate_product_description(product_name):
    prompt = f"""你是韓系女裝電商文案專家。

商品名稱：
{product_name}

請輸出：

【商品特色】
【穿搭建議】
【商品文案】

使用繁體中文。
"""
    return _generate(prompt)


def generate_group_buy_text(product_name, price):
    prompt = f"""你是服飾團購主。

商品名稱：
{product_name}

售價：
{price}

請產生LINE團購貼文。

格式：

🔥商品名稱

特色1
特色2
特色3

售價：xxx元

留言+1登記

使用繁體中文。
"""
    return _generate(prompt)


def generate_live_script(product_name):
    prompt = f"""你是女裝直播主。

商品：
{product_name}

請產生直播銷售話術。

語氣自然。
具促單能力。
使用繁體中文。
"""
    return _generate(prompt)


def analyze_product_image(image_path):
    if not image_path:
        raise GeminiServiceError("請先上傳商品圖片", detail="Missing image path")

    prompt = """你是韓系女裝商品辨識助理。
請根據圖片判斷商品資訊，並只回傳 JSON，不要 Markdown。
JSON 格式：
{
  "product_name": "商品名稱",
  "product_type": "商品類型",
  "color": "顏色",
  "material": "材質",
  "fit": "版型",
  "features": "商品特色",
  "other_specs": "其他規格關鍵字"
}
"""
    data = _extract_json_object(_generate_with_optional_image(prompt, image_path))
    product_name = (data.get("product_name") or "").strip()
    if not product_name:
        raise GeminiServiceError("AI 未辨識出商品名稱", detail=f"Missing product_name in response: {data}")

    details = [
        f"商品類型：{data.get('product_type') or '-'}",
        f"顏色：{data.get('color') or '-'}",
        f"材質：{data.get('material') or '-'}",
        f"版型：{data.get('fit') or '-'}",
        f"商品特色：{data.get('features') or '-'}",
    ]
    return {
        "product_name": product_name,
        "product_type": data.get("product_type") or "",
        "color": data.get("color") or "",
        "material": data.get("material") or "",
        "fit": data.get("fit") or "",
        "features": data.get("features") or "",
        "other_specs": data.get("other_specs") or "",
        "ai_description": "\n".join(details),
    }


def _parse_name_suggestions(text):
    try:
        data = _extract_json_object(text)
        suggestions = data.get("suggestions") or []
    except GeminiServiceError:
        suggestions = []

    if not suggestions:
        for line in (text or "").splitlines():
            cleaned = re.sub(r"^\s*[-*\d.、)）]+\s*", "", line).strip()
            if cleaned:
                suggestions.append(cleaned)

    result = []
    for item in suggestions:
        name = str(item or "").strip().strip('"').strip("'")
        if name and name not in result:
            result.append(name)
        if len(result) == 3:
            break
    if len(result) < 3:
        raise GeminiServiceError("AI 未產生足夠的名稱建議", detail=f"Raw suggestions response: {text}")
    return result


def generate_product_name_suggestions(product_name="", recognized_data=None, image_path=None):
    recognized_data = recognized_data or {}
    prompt = f"""你是韓系女裝電商商品命名專家。

請根據目前商品圖片與已辨識資料，重新產生 3 個更適合上架銷售的商品名稱。

目前商品名稱：
{product_name or "未命名商品"}

已辨識資料：
商品類型：{recognized_data.get("product_type") or "-"}
顏色：{recognized_data.get("color") or "-"}
材質：{recognized_data.get("material") or "-"}
版型：{recognized_data.get("fit") or "-"}
商品特色：{recognized_data.get("features") or "-"}

命名規則：
1. 使用繁體中文。
2. 每個名稱 8 到 18 個中文字。
3. 名稱要適合韓系女裝電商。
4. 不要使用標點符號、引號或編號。
5. 三個名稱要有差異。

只回傳 JSON，不要 Markdown：
{{"suggestions":["名稱1","名稱2","名稱3"]}}
"""
    return _parse_name_suggestions(_generate_with_optional_image(prompt, image_path))


def test_gemini_connection(api_key=None):
    previous = None
    if api_key is not None:
        previous = _setting("gemini_api_key", "")
        _save_setting("gemini_api_key", api_key.strip())
        db.session.flush()
    try:
        content = _generate("請用繁體中文回覆：DEAR ERP AI 連線測試成功。")
        now_text = utc_now().isoformat()
        _save_setting("gemini_model", MODEL_NAME)
        _save_setting("gemini_last_tested_at", now_text)
        _save_setting("gemini_connection_status", "連線成功")
        _save_setting("gemini_last_error", "")
        db.session.commit()
        return {"ok": True, "message": "連線成功", "content": content, "tested_at": now_text}
    except GeminiServiceError as error:
        db.session.rollback()
        detail = getattr(error, "detail", str(error))
        logger.exception("Gemini connection test failed: %s", detail)
        _save_setting("gemini_last_tested_at", utc_now().isoformat())
        _save_setting("gemini_connection_status", "連線失敗")
        _save_setting("gemini_last_error", detail)
        if api_key is not None and previous is not None:
            _save_setting("gemini_api_key", api_key.strip())
        db.session.commit()
        return {"ok": False, "message": str(error), "error": detail}
