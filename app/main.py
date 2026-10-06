from flask import Blueprint, Response, abort, current_app, jsonify, redirect, session, url_for

from .api import ApiError, go
from .helpers import login_required, uid

bp = Blueprint("main", __name__)


@bp.get("/")
def home():
    return redirect(url_for("shop.browse" if session.get("token") else "auth.login"))


@bp.get("/favicon.ico")
def favicon():
    # The page declares an inline icon; this just answers browsers that probe for the file anyway.
    return Response(status=204)


@bp.get("/media/<path:path>")
def media(path):
    """Stream an uploaded image from the Go server so the browser never needs to reach it directly."""
    if not path.startswith("uploads/") or ".." in path.split("/"):
        abort(404)
    client = current_app.extensions["go_api"]
    try:
        upstream = client.request("GET", "/" + path, stream=True)
    except ApiError:
        abort(404)
    headers = {"Cache-Control": "public, max-age=86400"}
    return Response(
        upstream.iter_content(chunk_size=64 * 1024),
        content_type=upstream.headers.get("Content-Type", "application/octet-stream"),
        headers=headers,
    )


@bp.get("/api/badges")
@login_required
def badges():
    """Cart count and unread messages for the header. Failures degrade to zero."""
    cart = unread = 0
    try:
        cart = int(go("GET", "/api/v1/cart/count", params={"user_id": uid()}).get("count") or 0)
    except (ApiError, ValueError):
        pass
    try:
        data = go("GET", "/api/chat/conversations", params={"limit": 50})
        unread = sum(c.get("unread_count") or 0 for c in data.get("conversations") or [])
    except ApiError:
        pass
    return jsonify(cart=cart, unread=unread)
