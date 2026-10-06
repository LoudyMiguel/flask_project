from flask import Blueprint, current_app, flash, redirect, render_template, request, session, url_for

from .api import ApiError, go
from .helpers import safe_next

bp = Blueprint("auth", __name__)


@bp.route("/login", methods=["GET", "POST"])
def login():
    if session.get("token") and request.method == "GET":
        return redirect(url_for("shop.browse"))

    next_url = safe_next(request.values.get("next"))
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        if not username or not password:
            flash("Enter your username or email and your password.", "error")
            return render_template("login.html", username=username, next_url=next_url), 400

        try:
            data = go("POST", "/api/v1/login", auth=False, json={"username": username, "password": password})
        except ApiError as err:
            if err.status == 401:
                message = "That username or password doesn't match an account."
            elif err.status == 403:
                message = "This account isn't verified yet. Verify your email in the MarketFlow app, then log in here."
            elif err.status == 429:
                message = "Too many attempts. Wait a minute and try again."
            else:
                message = err.message
            flash(message, "error")
            return render_template("login.html", username=username, next_url=next_url), (
                err.status if err.status < 500 else 502
            )

        user = data.get("user") or {}
        if user.get("role") not in current_app.config["ALLOWED_ROLES"]:
            flash("This site is for customer and seller accounts. Use the MarketFlow app for other account types.", "error")
            return render_template("login.html", username=username, next_url=next_url), 403

        csrf = session.get("csrf")
        session.clear()
        session.permanent = True
        if csrf:
            session["csrf"] = csrf
        session["token"] = data["token"]
        session["user"] = {
            "user_id": user["user_id"],
            "username": user["username"],
            "email": user.get("email", ""),
            "role": user["role"],
            "store_id": user.get("store_id") or 0,
            "avatar_url": user.get("avatar_url") or "",
        }
        return redirect(next_url or url_for("shop.browse"))

    return render_template("login.html", username="", next_url=next_url)


@bp.post("/logout")
def logout():
    session.clear()
    flash("You're logged out.", "info")
    return redirect(url_for("auth.login"))


@bp.route("/signup", methods=["GET", "POST"])
def signup():
    if session.get("token"):
        return redirect(url_for("shop.browse"))

    form = {"username": "", "email": "", "role": "customer"}
    if request.method == "POST":
        form = {
            "username": request.form.get("username", "").strip(),
            "email": request.form.get("email", "").strip(),
            "role": request.form.get("role", "customer"),
        }
        password = request.form.get("password", "")

        problem = None
        if len(form["username"]) < 3:
            problem = "Pick a username with at least 3 characters."
        elif "@" not in form["email"] or "." not in form["email"].split("@")[-1]:
            problem = "Enter a valid email address."
        elif len(password) < 8:
            problem = "Use a password with at least 8 characters."
        elif form["role"] not in current_app.config["ALLOWED_ROLES"]:
            problem = "Choose whether you're buying or selling."
        if problem:
            flash(problem, "error")
            return render_template("signup.html", form=form), 400

        try:
            go("POST", "/api/v1/register", auth=False, json={**form, "password": password})
        except ApiError as err:
            if err.status == 409:
                message = "That username or email is already in use. Try another, or log in."
            elif err.status == 429:
                message = "Too many attempts. Wait a minute and try again."
            else:
                message = err.message
            flash(message, "error")
            return render_template("signup.html", form=form), (err.status if err.status < 500 else 502)

        flash("Account created. Enter the code we emailed you to finish.", "success")
        return redirect(url_for("auth.verify", email=form["email"]))

    return render_template("signup.html", form=form)


@bp.route("/verify", methods=["GET", "POST"])
def verify():
    email = request.values.get("email", "").strip()
    if request.method == "POST":
        otp = request.form.get("otp", "").strip()
        if not email or not otp:
            flash("Enter your email and the code we sent.", "error")
            return render_template("verify.html", email=email), 400
        try:
            go("POST", "/api/v1/verify-otp", auth=False, json={"email": email, "otp": otp})
        except ApiError as err:
            message = {
                404: "We couldn't find an account with that email.",
                401: "That code is wrong or has expired.",
                429: "Too many attempts. Wait a minute and try again.",
            }.get(err.status, err.message)
            flash(message, "error")
            return render_template("verify.html", email=email), (err.status if err.status < 500 else 502)
        flash("Email verified. You can log in now.", "success")
        return redirect(url_for("auth.login"))
    return render_template("verify.html", email=email)
