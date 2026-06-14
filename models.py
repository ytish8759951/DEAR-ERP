from datetime import datetime, timezone

from werkzeug.security import check_password_hash, generate_password_hash

from database import db


def utc_now():
    return datetime.now(timezone.utc)


product_other_specs = db.Table(
    "product_other_specs",
    db.Column("product_id", db.Integer, db.ForeignKey("products.id"), primary_key=True),
    db.Column("other_spec_id", db.Integer, db.ForeignKey("other_specs.id"), primary_key=True),
)


class User(db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime(timezone=True), default=utc_now, nullable=False)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


class Employee(db.Model):
    __tablename__ = "employees"

    id = db.Column(db.Integer, primary_key=True)
    employee_code = db.Column(db.String(20), unique=True, index=True)
    name = db.Column(db.String(120), nullable=False, index=True)
    login_username = db.Column(db.String(80), unique=True, index=True)
    login_password_hash = db.Column(db.String(255))
    phone = db.Column(db.String(80))
    email = db.Column(db.String(160), unique=True)
    role = db.Column(db.String(80))
    role_id = db.Column(db.Integer, db.ForeignKey("employee_roles.id"), nullable=True)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    status = db.Column(db.String(20), nullable=False, default="在職", index=True)
    hire_date = db.Column(db.Date)
    resign_date = db.Column(db.Date)
    note = db.Column(db.Text)
    created_at = db.Column(db.DateTime(timezone=True), default=utc_now, nullable=False, index=True)

    role_master = db.relationship("EmployeeRole", back_populates="employees")
    attendance_records = db.relationship("AttendanceRecord", back_populates="employee")
    leave_requests = db.relationship(
        "LeaveRequest",
        foreign_keys="LeaveRequest.employee_id",
        back_populates="employee",
    )
    work_schedules = db.relationship("WorkSchedule", back_populates="employee")

    def set_login_password(self, password):
        self.login_password_hash = generate_password_hash(password) if password else None

    def check_login_password(self, password):
        if not self.login_password_hash:
            return False
        return check_password_hash(self.login_password_hash, password)


class EmployeeRole(db.Model):
    __tablename__ = "employee_roles"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), unique=True, nullable=False, index=True)
    is_active = db.Column(db.Boolean, nullable=False, default=True, index=True)
    created_at = db.Column(db.DateTime(timezone=True), default=utc_now, nullable=False)

    employees = db.relationship("Employee", back_populates="role_master")


class OrderSource(db.Model):
    __tablename__ = "order_sources"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), unique=True, nullable=False, index=True)
    is_active = db.Column(db.Boolean, nullable=False, default=True, index=True)
    created_at = db.Column(db.DateTime(timezone=True), default=utc_now, nullable=False)


class SystemSetting(db.Model):
    __tablename__ = "system_settings"

    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(120), unique=True, nullable=False, index=True)
    value = db.Column(db.Text)
    created_at = db.Column(db.DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at = db.Column(db.DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)


class AttendanceRecord(db.Model):
    __tablename__ = "attendance_records"
    __table_args__ = (
        db.Index("ix_attendance_records_employee_date", "employee_id", "record_date"),
    )

    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.Integer, db.ForeignKey("employees.id"), nullable=False)
    record_date = db.Column(db.Date, nullable=False, index=True)
    clock_in_at = db.Column(db.DateTime(timezone=True))
    clock_out_at = db.Column(db.DateTime(timezone=True))
    work_hours = db.Column(db.Numeric(6, 2), nullable=False, default=0)
    note = db.Column(db.Text)
    created_at = db.Column(db.DateTime(timezone=True), default=utc_now, nullable=False)

    employee = db.relationship("Employee", back_populates="attendance_records")


class LeaveRequest(db.Model):
    __tablename__ = "leave_requests"
    __table_args__ = (
        db.Index("ix_leave_requests_employee_dates", "employee_id", "start_date", "end_date"),
    )

    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.Integer, db.ForeignKey("employees.id"), nullable=False)
    leave_type = db.Column(db.String(80), nullable=False, default="請假")
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date, nullable=False)
    status = db.Column(db.String(40), nullable=False, default="pending")
    reason = db.Column(db.Text)
    reviewer_id = db.Column(db.Integer, db.ForeignKey("employees.id"))
    reviewed_at = db.Column(db.DateTime(timezone=True))
    created_at = db.Column(db.DateTime(timezone=True), default=utc_now, nullable=False)

    employee = db.relationship("Employee", foreign_keys=[employee_id], back_populates="leave_requests")
    reviewer = db.relationship("Employee", foreign_keys=[reviewer_id])


class WorkSchedule(db.Model):
    __tablename__ = "work_schedules"
    __table_args__ = (
        db.Index("ix_work_schedules_employee_date", "employee_id", "work_date"),
    )

    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.Integer, db.ForeignKey("employees.id"), nullable=False)
    work_date = db.Column(db.Date, nullable=False, index=True)
    shift_name = db.Column(db.String(80))
    start_time = db.Column(db.Time)
    end_time = db.Column(db.Time)
    is_day_off = db.Column(db.Boolean, nullable=False, default=False, index=True)
    note = db.Column(db.Text)
    created_at = db.Column(db.DateTime(timezone=True), default=utc_now, nullable=False)

    employee = db.relationship("Employee", back_populates="work_schedules")


class ShiftChangeRequest(db.Model):
    __tablename__ = "shift_change_requests"

    id = db.Column(db.Integer, primary_key=True)
    requester_employee_id = db.Column(db.Integer, db.ForeignKey("employees.id"), nullable=False)
    target_employee_id = db.Column(db.Integer, db.ForeignKey("employees.id"))
    original_work_date = db.Column(db.Date, nullable=False)
    requested_work_date = db.Column(db.Date)
    request_type = db.Column(db.String(40), nullable=False, default="shift_change")
    status = db.Column(db.String(40), nullable=False, default="pending")
    reason = db.Column(db.Text)
    reviewed_at = db.Column(db.DateTime(timezone=True))
    created_at = db.Column(db.DateTime(timezone=True), default=utc_now, nullable=False)

    requester = db.relationship("Employee", foreign_keys=[requester_employee_id])
    target_employee = db.relationship("Employee", foreign_keys=[target_employee_id])


class Supplier(db.Model):
    __tablename__ = "suppliers"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), unique=True, nullable=False, index=True)
    contact_person = db.Column(db.String(120), index=True)
    phone = db.Column(db.String(80), index=True)
    line = db.Column(db.String(120))
    address = db.Column(db.String(255))
    note = db.Column(db.Text)
    created_at = db.Column(db.DateTime(timezone=True), default=utc_now, nullable=False, index=True)
    updated_at = db.Column(db.DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)

    products = db.relationship("Product", back_populates="supplier")


class Customer(db.Model):
    __tablename__ = "customers"

    id = db.Column(db.Integer, primary_key=True)
    customer_code = db.Column(db.String(20), unique=True, index=True)
    name = db.Column(db.String(120), nullable=False, index=True)
    phone = db.Column(db.String(80), index=True)
    line = db.Column(db.String(120))
    category_id = db.Column(db.Integer, db.ForeignKey("customer_categories.id"), nullable=True)
    wholesale_paid = db.Column(db.Boolean, nullable=False, default=False, index=True)
    wholesale_paid_date = db.Column(db.Date)
    address = db.Column(db.String(255))
    note = db.Column(db.Text)
    is_active = db.Column(db.Boolean, nullable=False, default=True, index=True)
    created_at = db.Column(db.DateTime(timezone=True), default=utc_now, nullable=False, index=True)

    category = db.relationship("CustomerCategory", back_populates="customers")
    orders = db.relationship("Order", back_populates="customer")


class CustomerCategory(db.Model):
    __tablename__ = "customer_categories"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), unique=True, nullable=False, index=True)
    is_active = db.Column(db.Boolean, nullable=False, default=True, index=True)
    created_at = db.Column(db.DateTime(timezone=True), default=utc_now, nullable=False)

    customers = db.relationship("Customer", back_populates="category")


class Location(db.Model):
    __tablename__ = "locations"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), unique=True, nullable=False)
    products = db.relationship("Product", back_populates="location")


class Color(db.Model):
    __tablename__ = "colors"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), unique=True, nullable=False)
    variants = db.relationship("ProductVariant", back_populates="color")


class Size(db.Model):
    __tablename__ = "sizes"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), unique=True, nullable=False)
    variants = db.relationship("ProductVariant", back_populates="size")


class OtherSpec(db.Model):
    __tablename__ = "other_specs"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), unique=True, nullable=False)


class Product(db.Model):
    __tablename__ = "products"
    __table_args__ = (
        db.Index("ix_products_sku", "sku"),
        db.Index("ix_products_name", "name"),
        db.Index("ix_products_created_at", "created_at"),
        db.Index("ix_products_supplier_id", "supplier_id"),
        db.Index("ix_products_location_id", "location_id"),
    )

    id = db.Column(db.Integer, primary_key=True)
    sku = db.Column(db.String(80), unique=True, nullable=False)
    name = db.Column(db.String(160), nullable=False)
    price = db.Column(db.Numeric(10, 2), nullable=False, default=0)
    cost = db.Column(db.Numeric(10, 2), nullable=False, default=0)
    supply_mode = db.Column(db.String(20), nullable=False, default="一般商品", index=True)
    image_path = db.Column(db.String(255))
    size_chart = db.Column(db.Text)
    ai_description = db.Column(db.Text)
    line_group_text = db.Column(db.Text)
    live_script = db.Column(db.Text)
    created_at = db.Column(db.DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at = db.Column(db.DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)

    supplier_id = db.Column(db.Integer, db.ForeignKey("suppliers.id"), nullable=True)
    location_id = db.Column(db.Integer, db.ForeignKey("locations.id"), nullable=True)

    supplier = db.relationship("Supplier", back_populates="products")
    location = db.relationship("Location", back_populates="products")
    variants = db.relationship(
        "ProductVariant",
        back_populates="product",
        cascade="all, delete-orphan",
        order_by="ProductVariant.id",
    )
    other_specs = db.relationship("OtherSpec", secondary=product_other_specs, lazy="selectin")
    order_items = db.relationship("OrderItem", back_populates="product")

    @property
    def stock_display(self):
        if not self.variants:
            return "-"
        return " ".join(variant.stock_label for variant in self.variants)

    @property
    def other_spec_text(self):
        if not self.other_specs:
            return "無"
        return "、".join(spec.name for spec in self.other_specs)


class ProductVariant(db.Model):
    __tablename__ = "product_variants"
    __table_args__ = (
        db.UniqueConstraint("product_id", "color_id", "size_id", name="uq_product_color_size"),
        db.Index("ix_product_variants_product_id", "product_id"),
        db.Index("ix_product_variants_color_id", "color_id"),
        db.Index("ix_product_variants_size_id", "size_id"),
    )

    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey("products.id"), nullable=False)
    color_id = db.Column(db.Integer, db.ForeignKey("colors.id"), nullable=False)
    size_id = db.Column(db.Integer, db.ForeignKey("sizes.id"), nullable=False)
    stock = db.Column(db.Integer, nullable=False, default=0)

    product = db.relationship("Product", back_populates="variants")
    color = db.relationship("Color", back_populates="variants")
    size = db.relationship("Size", back_populates="variants")

    @property
    def spec_name(self):
        return f"{self.color.name}{self.size.name}"

    @property
    def stock_label(self):
        return f"{self.color.name[:1]}{self.size.name}({self.stock})"


class Order(db.Model):
    __tablename__ = "orders"
    __table_args__ = (
        db.Index("ix_orders_created_at", "created_at"),
        db.Index("ix_orders_order_date", "order_date"),
        db.Index("ix_orders_order_source_id", "order_source_id"),
        db.Index("ix_orders_status", "status"),
    )

    id = db.Column(db.Integer, primary_key=True)
    order_no = db.Column(db.String(80), unique=True, nullable=False)
    customer_id = db.Column(db.Integer, db.ForeignKey("customers.id"))
    order_source_id = db.Column(db.Integer, db.ForeignKey("order_sources.id"))
    group_buy_order_id = db.Column(db.Integer, db.ForeignKey("group_buy_orders.id"))
    group_buy_code = db.Column(db.String(80), index=True)
    order_date = db.Column(db.Date, nullable=False, default=lambda: utc_now().date())
    total_amount = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    discount_amount = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    shipping_fee = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    receivable_amount = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    status = db.Column(db.String(40), nullable=False, default="待付款")
    note = db.Column(db.Text)
    canceled_at = db.Column(db.DateTime(timezone=True))
    completed_at = db.Column(db.DateTime(timezone=True))
    created_at = db.Column(db.DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at = db.Column(db.DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)

    customer = db.relationship("Customer", back_populates="orders")
    order_source = db.relationship("OrderSource")
    items = db.relationship("OrderItem", back_populates="order", cascade="all, delete-orphan")
    returns = db.relationship("Return", back_populates="order", cascade="all, delete-orphan")


class OrderItem(db.Model):
    __tablename__ = "order_items"
    __table_args__ = (
        db.Index("ix_order_items_product_id", "product_id"),
        db.Index("ix_order_items_product_variant_id", "product_variant_id"),
        db.Index("ix_order_items_backorder_quantity", "backorder_quantity"),
    )

    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey("orders.id"), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey("products.id"), nullable=False)
    product_variant_id = db.Column(db.Integer, db.ForeignKey("product_variants.id"))
    quantity = db.Column(db.Integer, nullable=False, default=1)
    allocated_quantity = db.Column(db.Integer, nullable=False, default=0)
    backorder_quantity = db.Column(db.Integer, nullable=False, default=0)
    unit_price = db.Column(db.Numeric(10, 2), nullable=False, default=0)
    subtotal = db.Column(db.Numeric(12, 2), nullable=False, default=0)

    order = db.relationship("Order", back_populates="items")
    product = db.relationship("Product", back_populates="order_items")
    product_variant = db.relationship("ProductVariant")
    return_items = db.relationship("ReturnItem", back_populates="order_item")

    @property
    def fulfillment_status(self):
        if self.backorder_quantity > 0:
            return "預購中"
        return "已齊貨"


class ReplenishmentOrder(db.Model):
    __tablename__ = "replenishment_orders"
    __table_args__ = (
        db.Index("ix_replenishment_orders_order_no", "order_no"),
        db.Index("ix_replenishment_orders_supplier_id", "supplier_id"),
        db.Index("ix_replenishment_orders_status", "status"),
        db.Index("ix_replenishment_orders_created_at", "created_at"),
    )

    id = db.Column(db.Integer, primary_key=True)
    order_no = db.Column(db.String(80), unique=True, nullable=False)
    supplier_id = db.Column(db.Integer, db.ForeignKey("suppliers.id"))
    expected_arrival_date = db.Column(db.Date)
    status = db.Column(db.String(40), nullable=False, default="追貨中")
    note = db.Column(db.Text)
    created_at = db.Column(db.DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at = db.Column(db.DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)

    supplier = db.relationship("Supplier")
    items = db.relationship("ReplenishmentItem", back_populates="replenishment_order", cascade="all, delete-orphan")
    receipts = db.relationship("ReplenishmentReceipt", back_populates="replenishment_order", cascade="all, delete-orphan")


class ReplenishmentItem(db.Model):
    __tablename__ = "replenishment_items"
    __table_args__ = (
        db.Index("ix_replenishment_items_order_id", "replenishment_order_id"),
        db.Index("ix_replenishment_items_product_variant_id", "product_variant_id"),
        db.Index("ix_replenishment_items_status", "status"),
    )

    id = db.Column(db.Integer, primary_key=True)
    replenishment_order_id = db.Column(db.Integer, db.ForeignKey("replenishment_orders.id"), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey("products.id"), nullable=False)
    product_variant_id = db.Column(db.Integer, db.ForeignKey("product_variants.id"), nullable=False)
    required_quantity = db.Column(db.Integer, nullable=False, default=0)
    received_quantity = db.Column(db.Integer, nullable=False, default=0)
    remaining_quantity = db.Column(db.Integer, nullable=False, default=0)
    status = db.Column(db.String(40), nullable=False, default="追貨中")
    created_at = db.Column(db.DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at = db.Column(db.DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)

    replenishment_order = db.relationship("ReplenishmentOrder", back_populates="items")
    product = db.relationship("Product")
    product_variant = db.relationship("ProductVariant")
    receipts = db.relationship("ReplenishmentReceipt", back_populates="replenishment_item", cascade="all, delete-orphan")


class ReplenishmentReceipt(db.Model):
    __tablename__ = "replenishment_receipts"
    __table_args__ = (
        db.Index("ix_replenishment_receipts_order_id", "replenishment_order_id"),
        db.Index("ix_replenishment_receipts_item_id", "replenishment_item_id"),
        db.Index("ix_replenishment_receipts_created_at", "created_at"),
    )

    id = db.Column(db.Integer, primary_key=True)
    replenishment_order_id = db.Column(db.Integer, db.ForeignKey("replenishment_orders.id"), nullable=False)
    replenishment_item_id = db.Column(db.Integer, db.ForeignKey("replenishment_items.id"), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey("products.id"), nullable=False)
    product_variant_id = db.Column(db.Integer, db.ForeignKey("product_variants.id"), nullable=False)
    quantity = db.Column(db.Integer, nullable=False, default=0)
    operator = db.Column(db.String(80))
    created_at = db.Column(db.DateTime(timezone=True), default=utc_now, nullable=False)

    replenishment_order = db.relationship("ReplenishmentOrder", back_populates="receipts")
    replenishment_item = db.relationship("ReplenishmentItem", back_populates="receipts")
    product = db.relationship("Product")
    product_variant = db.relationship("ProductVariant")


class GroupBuy(db.Model):
    __tablename__ = "group_buys"
    __table_args__ = (
        db.Index("ix_group_buys_group_buy_no", "group_buy_no"),
        db.Index("ix_group_buys_name", "name"),
        db.Index("ix_group_buys_status", "status"),
        db.Index("ix_group_buys_created_at", "created_at"),
    )

    id = db.Column(db.Integer, primary_key=True)
    group_buy_no = db.Column(db.String(80), unique=True, nullable=False)
    public_code = db.Column(db.String(80), unique=True, index=True)
    name = db.Column(db.String(160), nullable=False)
    start_date = db.Column(db.Date)
    end_date = db.Column(db.Date)
    status = db.Column(db.String(40), nullable=False, default="進行中")
    description = db.Column(db.Text)
    note = db.Column(db.Text)
    is_active = db.Column(db.Boolean, nullable=False, default=True, index=True)
    created_at = db.Column(db.DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at = db.Column(db.DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)

    orders = db.relationship("GroupBuyOrder", back_populates="group_buy")
    items = db.relationship("GroupBuyItem", back_populates="group_buy", cascade="all, delete-orphan")


class GroupBuyItem(db.Model):
    __tablename__ = "group_buy_items"
    __table_args__ = (
        db.Index("ix_group_buy_items_group_buy_id", "group_buy_id"),
        db.Index("ix_group_buy_items_product_id", "product_id"),
        db.Index("ix_group_buy_items_product_variant_id", "product_variant_id"),
        db.Index("ix_group_buy_items_supply_mode", "supply_mode"),
    )

    id = db.Column(db.Integer, primary_key=True)
    group_buy_id = db.Column(db.Integer, db.ForeignKey("group_buys.id"), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey("products.id"), nullable=False)
    product_variant_id = db.Column(db.Integer, db.ForeignKey("product_variants.id"), nullable=False)
    supply_mode = db.Column(db.String(20), nullable=False, default="一般商品")
    original_price = db.Column(db.Numeric(10, 2), nullable=False, default=0)
    group_price = db.Column(db.Numeric(10, 2), nullable=False, default=0)
    order_limit = db.Column(db.Integer, nullable=False, default=0)
    allow_preorder = db.Column(db.Boolean, nullable=False, default=False)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at = db.Column(db.DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)

    group_buy = db.relationship("GroupBuy", back_populates="items")
    product = db.relationship("Product")
    product_variant = db.relationship("ProductVariant")


class GroupBuyOrder(db.Model):
    __tablename__ = "group_buy_orders"
    __table_args__ = (
        db.Index("ix_group_buy_orders_order_no", "order_no"),
        db.Index("ix_group_buy_orders_group_buy_id", "group_buy_id"),
        db.Index("ix_group_buy_orders_customer_id", "customer_id"),
        db.Index("ix_group_buy_orders_customer_name", "customer_name"),
        db.Index("ix_group_buy_orders_customer_code", "customer_code"),
        db.Index("ix_group_buy_orders_phone", "phone"),
        db.Index("ix_group_buy_orders_order_status", "order_status"),
        db.Index("ix_group_buy_orders_created_at", "created_at"),
    )

    id = db.Column(db.Integer, primary_key=True)
    order_no = db.Column(db.String(80), unique=True, nullable=False)
    group_buy_id = db.Column(db.Integer, db.ForeignKey("group_buys.id"), nullable=True)
    customer_id = db.Column(db.Integer, db.ForeignKey("customers.id"), nullable=True)
    customer_name = db.Column(db.String(120))
    customer_code = db.Column(db.String(20))
    line_name = db.Column(db.String(120))
    phone = db.Column(db.String(80))
    order_status = db.Column(db.String(40), nullable=False, default="未轉訂單")
    group_buy_code = db.Column(db.String(80), index=True)
    formal_order_id = db.Column(db.Integer, db.ForeignKey("orders.id"))
    is_test_order = db.Column(db.Boolean, nullable=False, default=False, index=True)
    total_amount = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    note = db.Column(db.Text)
    created_at = db.Column(db.DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at = db.Column(db.DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)

    group_buy = db.relationship("GroupBuy", back_populates="orders")
    customer = db.relationship("Customer")
    formal_order = db.relationship("Order", foreign_keys=[formal_order_id])
    items = db.relationship("GroupBuyOrderItem", back_populates="group_buy_order", cascade="all, delete-orphan")


class GroupBuyOrderItem(db.Model):
    __tablename__ = "group_buy_order_items"
    __table_args__ = (
        db.Index("ix_group_buy_order_items_group_buy_order_id", "group_buy_order_id"),
        db.Index("ix_group_buy_order_items_group_buy_id", "group_buy_id"),
        db.Index("ix_group_buy_order_items_product_id", "product_id"),
        db.Index("ix_group_buy_order_items_product_variant_id", "product_variant_id"),
        db.Index("ix_group_buy_order_items_product_code", "product_code"),
        db.Index("ix_group_buy_order_items_product_name", "product_name"),
        db.Index("ix_group_buy_order_items_created_at", "created_at"),
    )

    id = db.Column(db.Integer, primary_key=True)
    group_buy_order_id = db.Column(db.Integer, db.ForeignKey("group_buy_orders.id"), nullable=False)
    group_buy_id = db.Column(db.Integer, db.ForeignKey("group_buys.id"), nullable=True)
    product_id = db.Column(db.Integer, db.ForeignKey("products.id"), nullable=True)
    product_variant_id = db.Column(db.Integer, db.ForeignKey("product_variants.id"), nullable=True)
    product_code = db.Column(db.String(80))
    product_name = db.Column(db.String(160))
    color_name = db.Column(db.String(80))
    size_name = db.Column(db.String(80))
    supply_mode = db.Column(db.String(20), nullable=False, default="一般商品")
    quantity = db.Column(db.Integer, nullable=False, default=0)
    unit_price = db.Column(db.Numeric(10, 2), nullable=False, default=0)
    subtotal = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    backorder_quantity = db.Column(db.Integer, nullable=False, default=0)
    converted_quantity = db.Column(db.Integer, nullable=False, default=0)
    created_at = db.Column(db.DateTime(timezone=True), default=utc_now, nullable=False)

    group_buy_order = db.relationship("GroupBuyOrder", back_populates="items")
    group_buy = db.relationship("GroupBuy")
    product = db.relationship("Product")
    product_variant = db.relationship("ProductVariant")


class Return(db.Model):
    __tablename__ = "returns"
    __table_args__ = (
        db.Index("ix_returns_order_id", "order_id"),
        db.Index("ix_returns_return_no", "return_no"),
        db.Index("ix_returns_created_at", "created_at"),
    )

    id = db.Column(db.Integer, primary_key=True)
    return_no = db.Column(db.String(80), unique=True, nullable=False)
    order_id = db.Column(db.Integer, db.ForeignKey("orders.id"), nullable=False)
    return_type = db.Column(db.String(40), nullable=False)
    reason = db.Column(db.String(255))
    note = db.Column(db.Text)
    created_at = db.Column(db.DateTime(timezone=True), default=utc_now, nullable=False)

    order = db.relationship("Order", back_populates="returns")
    items = db.relationship("ReturnItem", back_populates="return_record", cascade="all, delete-orphan")


class ReturnItem(db.Model):
    __tablename__ = "return_items"
    __table_args__ = (
        db.Index("ix_return_items_return_id", "return_id"),
        db.Index("ix_return_items_order_item_id", "order_item_id"),
        db.Index("ix_return_items_product_variant_id", "product_variant_id"),
    )

    id = db.Column(db.Integer, primary_key=True)
    return_id = db.Column(db.Integer, db.ForeignKey("returns.id"), nullable=False)
    order_item_id = db.Column(db.Integer, db.ForeignKey("order_items.id"), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey("products.id"), nullable=False)
    product_variant_id = db.Column(db.Integer, db.ForeignKey("product_variants.id"), nullable=False)
    quantity = db.Column(db.Integer, nullable=False, default=1)
    reason = db.Column(db.String(255))
    note = db.Column(db.Text)
    process_status = db.Column(db.String(40), nullable=False, default="待處理")
    created_at = db.Column(db.DateTime(timezone=True), default=utc_now, nullable=False)

    return_record = db.relationship("Return", back_populates="items")
    order_item = db.relationship("OrderItem", back_populates="return_items")
    product = db.relationship("Product")
    product_variant = db.relationship("ProductVariant")


class DefectiveInventory(db.Model):
    __tablename__ = "defective_inventory"
    __table_args__ = (
        db.UniqueConstraint("product_variant_id", name="uq_defective_inventory_variant"),
        db.Index("ix_defective_inventory_product_id", "product_id"),
        db.Index("ix_defective_inventory_product_variant_id", "product_variant_id"),
    )

    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey("products.id"), nullable=False)
    product_variant_id = db.Column(db.Integer, db.ForeignKey("product_variants.id"), nullable=False)
    quantity = db.Column(db.Integer, nullable=False, default=0)
    updated_at = db.Column(db.DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)

    product = db.relationship("Product")
    product_variant = db.relationship("ProductVariant")


class InventoryMovement(db.Model):
    __tablename__ = "inventory_movements"
    __table_args__ = (
        db.Index("ix_inventory_movements_product_id", "product_id"),
        db.Index("ix_inventory_movements_product_variant_id", "product_variant_id"),
        db.Index("ix_inventory_movements_reference", "reference_type", "reference_id"),
        db.Index("ix_inventory_movements_created_at", "created_at"),
    )

    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey("products.id"), nullable=False)
    product_variant_id = db.Column(db.Integer, db.ForeignKey("product_variants.id"), nullable=False)
    movement_type = db.Column(db.String(80), nullable=False)
    before_quantity = db.Column(db.Integer)
    quantity = db.Column(db.Integer, nullable=False)
    after_quantity = db.Column(db.Integer)
    reference_type = db.Column(db.String(80))
    reference_id = db.Column(db.Integer)
    source_no = db.Column(db.String(80))
    operator = db.Column(db.String(80))
    note = db.Column(db.Text)
    created_at = db.Column(db.DateTime(timezone=True), default=utc_now, nullable=False)

    product = db.relationship("Product")
    product_variant = db.relationship("ProductVariant")


# Compatibility aliases for the return/inventory-log naming used by the ERP roadmap.
ReturnOrder = Return
InventoryLog = InventoryMovement
