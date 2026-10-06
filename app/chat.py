from flask import Blueprint, flash, jsonify, redirect, render_template, request, url_for

from .api import ApiError, go
from .helpers import login_required, media, uid

bp = Blueprint("chat", __name__)

CHAT_ROOT = "/api/chat"


def _fix_avatar(person):
    if person and person.get("avatar_url"):
        person["avatar_url"] = media(person["avatar_url"])
    return person


# ── pages ──────────────────────────────────────────────────────────────────

@bp.get("/messages")
@login_required
def inbox():
    return render_template("messages.html", conversation=None, other=None)


@bp.get("/messages/<int:conversation_id>")
@login_required
def thread(conversation_id):
    conversation = go("GET", f"{CHAT_ROOT}/conversations/{conversation_id}")
    other = next((p for p in conversation.get("participants") or [] if p["user_id"] != uid()), None)
    return render_template("messages.html", conversation=conversation, other=_fix_avatar(other))


@bp.post("/messages/start")
@login_required
def start():
    """Open (or reuse) a conversation, then land in it."""
    try:
        recipient = int(request.form["recipient_id"])
    except (KeyError, ValueError):
        flash("We couldn't tell who to message.", "error")
        return redirect(url_for("chat.inbox"))

    body = {"type": request.form.get("type", "direct"), "recipient_id": recipient}
    for key in ("order_id", "product_id"):
        if request.form.get(key, "").isdigit():
            body[key] = int(request.form[key])

    try:
        conversation = go("POST", f"{CHAT_ROOT}/conversations", json=body)
    except ApiError as err:
        if err.status == 401:
            raise
        flash(err.message, "error")
        return redirect(request.referrer or url_for("chat.inbox"))
    return redirect(url_for("chat.thread", conversation_id=conversation["conversation_id"]))


# ── JSON endpoints used by chat.js ─────────────────────────────────────────

@bp.get("/api/chat/conversations")
@login_required
def api_conversations():
    data = go("GET", f"{CHAT_ROOT}/conversations", params={"limit": 50})
    conversations = data.get("conversations") or []
    for c in conversations:
        _fix_avatar(c.get("other_participant"))
    return jsonify(conversations=conversations)


@bp.get("/api/chat/<int:conversation_id>/messages")
@login_required
def api_messages(conversation_id):
    params = {"limit": min(int(request.args.get("limit", 40) or 40), 100)}
    if request.args.get("before_id", "").isdigit():
        params["before_id"] = request.args["before_id"]
    data = go("GET", f"{CHAT_ROOT}/conversations/{conversation_id}/messages", params=params)
    for m in data.get("messages") or []:
        if m.get("sender_avatar"):
            m["sender_avatar"] = media(m["sender_avatar"])
    return jsonify(data)


@bp.post("/api/chat/<int:conversation_id>/messages")
@login_required
def api_send(conversation_id):
    text = ((request.get_json(silent=True) or {}).get("body") or "").strip()
    if not text:
        return jsonify(error="Write a message first."), 400
    if len(text) > 2000:
        return jsonify(error="Messages can be up to 2,000 characters."), 400
    message = go(
        "POST",
        f"{CHAT_ROOT}/conversations/{conversation_id}/messages",
        json={"message_type": "text", "body": text},
    )
    return jsonify(message), 201


@bp.post("/api/chat/<int:conversation_id>/read")
@login_required
def api_read(conversation_id):
    go("POST", f"{CHAT_ROOT}/conversations/{conversation_id}/read")
    return jsonify(ok=True)


@bp.delete("/api/chat/messages/<int:message_id>")
@login_required
def api_delete(message_id):
    go("DELETE", f"{CHAT_ROOT}/messages/{message_id}")
    return jsonify(ok=True)
