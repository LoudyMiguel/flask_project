from flask import Blueprint, abort, redirect, render_template, url_for

from .api import ApiError, go
from .helpers import login_required, uid

bp = Blueprint("profile", __name__)


@bp.get("/profile")
@login_required
def mine():
    return redirect(url_for("profile.view", user_id=uid()))


@bp.get("/profile/<int:user_id>")
@login_required
def view(user_id):
    try:
        data = go("GET", "/api/v1/profile", params={"user_id": user_id, "current_user_id": uid()})
    except ApiError as err:
        if err.status == 404:
            abort(404)
        raise
    return render_template(
        "profile.html",
        person=data["user"],
        store=data.get("store"),
        stats=data.get("stats") or {},
        is_self=user_id == uid(),
    )
