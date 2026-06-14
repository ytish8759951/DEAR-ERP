from datetime import datetime, time
from decimal import Decimal

from flask import Blueprint, render_template
from sqlalchemy import func

from decorators import login_required
from models import Order, Product, ProductVariant, utc_now


dashboard_bp = Blueprint("dashboard", __name__, url_prefix="/dashboard")


@dashboard_bp.route("/")
@login_required
def index():
    product_count = Product.query.count()
    variant_count = ProductVariant.query.count()
    low_stock_count = ProductVariant.query.filter(ProductVariant.stock <= 2).count()
    today = utc_now().date()
    month_start = today.replace(day=1)
    today_start = datetime.combine(today, time.min)
    today_end = datetime.combine(today, time.max)
    month_start_at = datetime.combine(month_start, time.min)
    completed_query = Order.query.filter(Order.status == "已完成", Order.completed_at.isnot(None))
    today_completed_count = completed_query.filter(
        Order.completed_at >= today_start,
        Order.completed_at <= today_end,
    ).count()
    month_completed_count = completed_query.filter(Order.completed_at >= month_start_at).count()
    completed_total_amount = (
        db_total
        if (db_total := completed_query.with_entities(func.coalesce(func.sum(Order.receivable_amount), 0)).scalar())
        is not None
        else Decimal("0")
    )
    return render_template(
        "dashboard.html",
        product_count=product_count,
        variant_count=variant_count,
        low_stock_count=low_stock_count,
        today_completed_count=today_completed_count,
        month_completed_count=month_completed_count,
        completed_total_amount=completed_total_amount,
    )
