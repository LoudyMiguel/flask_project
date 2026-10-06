import logging

from flask import Flask, abort, flash, jsonify, redirect, render_template, request, session, url_for

from config import Config

from .api import ApiError, GoApi
from .helpers import FILTERS, csrf_token, current_user

log = logging.getLogger("marketflow")


def create_app(config_object=Config):
    app = Flask(__name__)
    app.config.from_object(config_object)

    if app.config.get("SECRET_KEY_IS_EPHEMERAL"):
        log.warning("SECRET_KEY is not set: sessions will reset whenever the app restarts.")

    app.extensions["go_api"] = GoApi(app.config["GO_API_URL"], app.config["GO_API_TIMEOUT"])
    app.extensions["currency_cache"] = {}
    app.jinja_env.filters.update(FILTERS)

    from . import auth, chat, main, orders, profile, shop

    for module in (main, auth, shop, orders, chat, profile):
        app.register_blueprint(module.bp)

    @app.context_processor
    def inject_globals():
        return {"me": current_user(), "csrf_token": csrf_token, "go_api_url": app.config["GO_API_URL"]}

    @app.before_request
    def check_csrf():
        if request.method in ("POST", "PUT", "PATCH", "DELETE"):
            sent = request.form.get("csrf_token") or request.headers.get("X-CSRF-Token")
            if not sent or sent != session.get("csrf"):
                abort(400, description="Your session form expired. Reload the page and try again.")

    @app.after_request
    def security_headers(resp):
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("X-Frame-Options", "DENY")
        resp.headers.setdefault("Referrer-Policy", "same-origin")
        if request.endpoint not in ("main.media", "static"):
            resp.headers.setdefault("Cache-Control", "no-store")
        return resp

    def wants_json():
        return request.path.startswith("/api/")

    @app.errorhandler(ApiError)
    def api_error(err):
        if err.status == 401 and session.get("token"):
            session.clear()
            if wants_json():
                return jsonify(error="Your session expired. Log in again."), 401
            flash("Your session expired. Log in again.", "error")
            return redirect(url_for("auth.login"))
        status = err.status if 400 <= err.status < 500 else 502 if err.status < 500 else err.status
        if wants_json():
            return jsonify(error=err.message), status
        return render_template("error.html", status=status, message=err.message), status

    @app.errorhandler(400)
    @app.errorhandler(401)
    @app.errorhandler(403)
    @app.errorhandler(404)
    def http_error(err):
        messages = {
            400: err.description,
            401: "Log in to continue.",
            403: "Your account can't open this page.",
            404: "We couldn't find that page.",
        }
        message = messages.get(err.code, err.description)
        if wants_json():
            return jsonify(error=message), err.code
        return render_template("error.html", status=err.code, message=message), err.code

    return app
