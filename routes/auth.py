from flask import Blueprint, flash, redirect, render_template, request, session, url_for

from models import Employee, User


auth_bp = Blueprint("auth", __name__)


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        user = User.query.filter_by(username=username).first()

        if user and user.check_password(password):
            session.clear()
            session["user_id"] = user.id
            session["username"] = user.username
            return redirect(url_for("dashboard.index"))

        employee = Employee.query.filter_by(login_username=username).first()
        if employee and employee.check_login_password(password):
            if employee.status != "在職" or not employee.is_active:
                flash("此員工已停用或離職，無法登入。", "danger")
                return render_template("login.html")
            session.clear()
            session["user_id"] = f"employee:{employee.id}"
            session["employee_id"] = employee.id
            session["username"] = employee.login_username
            session["employee_name"] = employee.name
            return redirect(url_for("dashboard.index"))

        flash("帳號或密碼錯誤", "danger")

    return render_template("login.html")


@auth_bp.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return redirect(url_for("auth.login"))
