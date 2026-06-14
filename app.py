from flask import Flask, redirect, session, url_for
from flask_migrate import Migrate

from config import Config
from database import db
from models import Color, Customer, CustomerCategory, Employee, EmployeeRole, GroupBuy, Location, Order, OrderItem, OrderSource, OtherSpec, Product, Size, SystemSetting, User


migrate = Migrate()


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    app.config["PRODUCT_UPLOAD_FOLDER"].mkdir(parents=True, exist_ok=True)

    db.init_app(app)
    migrate.init_app(app, db)

    from routes.ai import ai_bp
    from routes.auth import auth_bp
    from routes.customers import customers_bp
    from routes.dashboard import dashboard_bp
    from routes.group_buys import group_buys_bp, public_groupbuy_bp
    from routes.operations import operations_bp
    from routes.employees import employees_bp
    from routes.orders import orders_bp
    from routes.products import products_bp
    from routes.replenishment import replenishment_bp
    from routes.settings import settings_bp
    from routes.system import system_bp
    from routes.suppliers import suppliers_bp

    app.register_blueprint(ai_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(customers_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(employees_bp)
    app.register_blueprint(group_buys_bp)
    app.register_blueprint(public_groupbuy_bp)
    app.register_blueprint(orders_bp)
    app.register_blueprint(operations_bp)
    app.register_blueprint(products_bp)
    app.register_blueprint(replenishment_bp)
    app.register_blueprint(settings_bp)
    app.register_blueprint(system_bp)
    app.register_blueprint(suppliers_bp)

    @app.route("/")
    def index():
        if session.get("user_id"):
            return redirect(url_for("dashboard.index"))
        return redirect(url_for("auth.login"))

    @app.cli.command("init-db")
    def init_db_command():
        init_database()
        print("Database initialized.")

    with app.app_context():
        init_database()

    return app


def seed_lookup(model, names):
    for name in names:
        if not model.query.filter_by(name=name).first():
            db.session.add(model(name=name))


def sqlite_columns(table_name):
    rows = db.session.execute(db.text(f"PRAGMA table_info({table_name})")).fetchall()
    return {row[1] for row in rows}


def sqlite_table_exists(table_name):
    row = db.session.execute(
        db.text("SELECT name FROM sqlite_master WHERE type='table' AND name=:name"),
        {"name": table_name},
    ).first()
    return row is not None


def ensure_sqlite_dev_columns():
    if not db.engine.url.drivername.startswith("sqlite"):
        return

    def add_columns(table_name, column_sql):
        if not sqlite_table_exists(table_name):
            return
        existing = sqlite_columns(table_name)
        for column_name, sql in column_sql.items():
            if column_name not in existing:
                db.session.execute(db.text(f"ALTER TABLE {table_name} ADD COLUMN {sql}"))

    add_columns(
        "suppliers",
        {
            "contact_person": "contact_person VARCHAR(120)",
            "phone": "phone VARCHAR(80)",
            "line": "line VARCHAR(120)",
            "address": "address VARCHAR(255)",
            "note": "note TEXT",
            "created_at": "created_at DATETIME",
            "updated_at": "updated_at DATETIME",
        },
    )
    add_columns(
        "products",
        {
            "image_path": "image_path VARCHAR(255)",
            "supply_mode": "supply_mode VARCHAR(20) DEFAULT '一般商品' NOT NULL",
            "size_chart": "size_chart TEXT",
            "ai_description": "ai_description TEXT",
            "line_group_text": "line_group_text TEXT",
            "live_script": "live_script TEXT",
        },
    )
    add_columns(
        "customers",
        {
            "customer_code": "customer_code VARCHAR(20)",
            "category_id": "category_id INTEGER",
            "wholesale_paid": "wholesale_paid BOOLEAN DEFAULT 0 NOT NULL",
            "wholesale_paid_date": "wholesale_paid_date DATE",
            "is_active": "is_active BOOLEAN DEFAULT 1 NOT NULL",
        },
    )
    add_columns(
        "employees",
        {
            "employee_code": "employee_code VARCHAR(20)",
            "login_username": "login_username VARCHAR(80)",
            "login_password_hash": "login_password_hash VARCHAR(255)",
            "role_id": "role_id INTEGER",
            "status": "status VARCHAR(20) DEFAULT '在職' NOT NULL",
            "hire_date": "hire_date DATE",
            "resign_date": "resign_date DATE",
            "note": "note TEXT",
        },
    )
    add_columns(
        "orders",
        {
            "order_source_id": "order_source_id INTEGER",
            "group_buy_order_id": "group_buy_order_id INTEGER",
            "group_buy_code": "group_buy_code VARCHAR(80)",
            "order_date": "order_date DATE",
            "discount_amount": "discount_amount NUMERIC(12, 2) DEFAULT 0 NOT NULL",
            "shipping_fee": "shipping_fee NUMERIC(12, 2) DEFAULT 0 NOT NULL",
            "receivable_amount": "receivable_amount NUMERIC(12, 2) DEFAULT 0 NOT NULL",
            "note": "note TEXT",
            "canceled_at": "canceled_at DATETIME",
            "completed_at": "completed_at DATETIME",
            "updated_at": "updated_at DATETIME",
        },
    )
    add_columns(
        "order_items",
        {
            "subtotal": "subtotal NUMERIC(12, 2) DEFAULT 0 NOT NULL",
            "allocated_quantity": "allocated_quantity INTEGER DEFAULT 0 NOT NULL",
            "backorder_quantity": "backorder_quantity INTEGER DEFAULT 0 NOT NULL",
        },
    )
    if sqlite_table_exists("order_items"):
        db.session.execute(
            db.text(
                """
                UPDATE order_items
                SET allocated_quantity = quantity
                WHERE allocated_quantity = 0
                  AND backorder_quantity = 0
                  AND quantity > 0
                """
            )
        )
    add_columns(
        "return_items",
        {
            "process_status": "process_status VARCHAR(40) DEFAULT '待處理' NOT NULL",
        },
    )
    add_columns(
        "group_buys",
        {
            "public_code": "public_code VARCHAR(80)",
            "description": "description TEXT",
            "is_active": "is_active BOOLEAN DEFAULT 1 NOT NULL",
            "updated_at": "updated_at DATETIME",
        },
    )
    add_columns(
        "group_buy_orders",
        {
            "line_name": "line_name VARCHAR(120)",
            "group_buy_code": "group_buy_code VARCHAR(80)",
            "formal_order_id": "formal_order_id INTEGER",
            "is_test_order": "is_test_order BOOLEAN DEFAULT 0 NOT NULL",
            "updated_at": "updated_at DATETIME",
        },
    )
    add_columns(
        "group_buy_order_items",
        {
            "supply_mode": "supply_mode VARCHAR(20) DEFAULT '一般商品' NOT NULL",
            "backorder_quantity": "backorder_quantity INTEGER DEFAULT 0 NOT NULL",
            "converted_quantity": "converted_quantity INTEGER DEFAULT 0 NOT NULL",
        },
    )
    add_columns(
        "inventory_movements",
        {
            "before_quantity": "before_quantity INTEGER",
            "after_quantity": "after_quantity INTEGER",
            "source_no": "source_no VARCHAR(80)",
            "operator": "operator VARCHAR(80)",
        },
    )

    db.session.execute(
        db.text(
            "CREATE UNIQUE INDEX IF NOT EXISTS ux_employees_login_username "
            "ON employees(login_username) WHERE login_username IS NOT NULL"
        )
    )
    db.session.execute(
        db.text(
            "CREATE UNIQUE INDEX IF NOT EXISTS ux_employees_employee_code "
            "ON employees(employee_code) WHERE employee_code IS NOT NULL"
        )
    )
    db.session.execute(
        db.text(
            "CREATE UNIQUE INDEX IF NOT EXISTS ux_customers_customer_code "
            "ON customers(customer_code) WHERE customer_code IS NOT NULL"
        )
    )

    product_columns = sqlite_columns("products") if sqlite_table_exists("products") else set()
    if "image_filename" in product_columns and "image_path" in product_columns:
        pending_image_path_rows = db.session.execute(
            db.text(
                """
                SELECT COUNT(*)
                FROM products
                WHERE image_path IS NULL
                  AND image_filename IS NOT NULL
                  AND image_filename != ''
                """
            )
        ).scalar()
        if pending_image_path_rows:
            db.session.execute(
                db.text(
                    """
                    UPDATE products
                    SET image_path = 'uploads/products/' || image_filename
                    WHERE image_path IS NULL
                      AND image_filename IS NOT NULL
                      AND image_filename != ''
                    """
                )
            )
    db.session.commit()


def seed_master_data():
    seed_lookup(CustomerCategory, ["一般客", "VIP客", "批發客", "直播客", "團購客"])
    seed_lookup(EmployeeRole, ["老闆", "店長", "倉管", "客服", "會計", "直播", "小幫手"])
    seed_lookup(OrderSource, ["現場客", "直播客", "LINE團購", "其他", "批發客"])


def backfill_employee_roles():
    roles = {role.name: role for role in EmployeeRole.query.all()}
    for employee in Employee.query.filter(
        Employee.role_id.is_(None),
        Employee.role.isnot(None),
        Employee.role != "",
    ):
        role = roles.get(employee.role)
        if role:
            employee.role_id = role.id
    for employee in Employee.query.all():
        if not employee.status:
            employee.status = "在職" if employee.is_active else "停用"
        elif employee.status == "在職" and not employee.is_active:
            employee.status = "停用"
        else:
            employee.is_active = employee.status == "在職"


def next_employee_code():
    latest = Employee.query.with_entities(Employee.employee_code).filter(
        Employee.employee_code.like("E%")
    ).order_by(Employee.employee_code.desc()).first()
    sequence = 0
    if latest and latest.employee_code and latest.employee_code[1:].isdigit():
        sequence = int(latest.employee_code[1:])
    return f"E{sequence + 1:06d}"


def backfill_employee_codes():
    for employee in Employee.query.filter(
        (Employee.employee_code.is_(None)) | (Employee.employee_code == "")
    ).order_by(Employee.id):
        employee.employee_code = next_employee_code()


def next_customer_code():
    latest = Customer.query.with_entities(Customer.customer_code).filter(
        Customer.customer_code.like("D%")
    ).order_by(Customer.customer_code.desc()).first()
    sequence = 0
    if latest and latest.customer_code and latest.customer_code[1:].isdigit():
        sequence = int(latest.customer_code[1:])
    return f"D{sequence + 1:07d}"


def backfill_customer_codes():
    for customer in Customer.query.filter(
        (Customer.customer_code.is_(None)) | (Customer.customer_code == "")
    ).order_by(Customer.id):
        customer.customer_code = next_customer_code()


def backfill_orders():
    for order in Order.query.all():
        if not order.order_date:
            order.order_date = order.created_at.date() if order.created_at else utc_today()
        if order.status == "全部退貨":
            order.status = "已退貨"
        elif order.status == "已出貨":
            order.status = "已完成"
            if not order.completed_at:
                order.completed_at = order.updated_at or order.created_at
        elif order.status == "部分到貨":
            order.status = "預購中"
        total = sum((item.subtotal or 0) for item in order.items)
        if total == 0:
            total = sum((item.quantity or 0) * (item.unit_price or 0) for item in order.items)
        order.total_amount = total
        order.receivable_amount = (order.total_amount or 0) - (order.discount_amount or 0) + (order.shipping_fee or 0)

        for item in order.items:
            item.subtotal = (item.quantity or 0) * (item.unit_price or 0)


def backfill_group_buys():
    for product in Product.query.filter((Product.supply_mode.is_(None)) | (Product.supply_mode == "")).all():
        product.supply_mode = "一般商品"
    for group_buy in GroupBuy.query.all():
        if not group_buy.public_code:
            group_buy.public_code = group_buy.group_buy_no
        if group_buy.is_active is None:
            group_buy.is_active = group_buy.status != "已停用"


def utc_today():
    from models import utc_now

    return utc_now().date()


def init_database():
    db.create_all()
    ensure_sqlite_dev_columns()

    if not User.query.filter_by(username="admin").first():
        admin = User(username="admin")
        admin.set_password("admin123")
        db.session.add(admin)

    seed_master_data()
    backfill_employee_roles()
    backfill_employee_codes()
    backfill_customer_codes()
    backfill_orders()
    backfill_group_buys()

    seed_lookup(Location, ["A區", "B區", "C區", "直播區", "新品區", "暫存區"])
    seed_lookup(Color, ["黑色", "白色", "灰色", "粉色", "藍色"])
    seed_lookup(Size, ["F", "S", "M", "L", "XL"])
    seed_lookup(OtherSpec, ["現貨", "預購", "薄款", "厚款", "彈性"])
    db.session.commit()


app = create_app()


if __name__ == "__main__":
    app.run(debug=True)
