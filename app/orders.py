from flask import Blueprint, Response, abort, flash, redirect, render_template, request, session, url_for

from .api import ApiError, go
from .helpers import login_required, seller_required, store_id, uid

bp = Blueprint("orders", __name__)

BUYER_CANCELLABLE = {"pending", "processing", "awaiting_rider"}
CLOSED = {"completed", "cancelled", "delivered"}

# Tabs on both order lists: (key, label, statuses it covers). None = everything.
BUYER_TABS = [
    ("active", "In progress", {"pending", "processing", "awaiting_rider", "ready_to_claim"}),
    ("done", "Completed", {"completed", "delivered"}),
    ("cancelled", "Cancelled", {"cancelled"}),
    ("all", "All", None),
]
STORE_TABS = [
    ("new", "New", {"pending"}),
    ("preparing", "Preparing", {"processing", "awaiting_rider"}),
    ("ready", "Ready for pickup", {"ready_to_claim"}),
    ("done", "Finished", {"completed", "delivered", "cancelled"}),
    ("all", "All", None),
]


def _tabbed(orders, tabs, active):
    keys = [t[0] for t in tabs]
    if active not in keys:
        active = tabs[0][0]
    counts = {key: sum(1 for o in orders if statuses is None or o["status"] in statuses) for key, _, statuses in tabs}
    statuses = next(s for key, _, s in tabs if key == active)
    shown = [o for o in orders if statuses is None or o["status"] in statuses]
    return active, counts, shown


# ── lists ──────────────────────────────────────────────────────────────────

@bp.get("/orders")
@login_required
def my_orders():
    """Purchases made by this account (a seller can buy too)."""
    orders = go("GET", "/api/v1/orders/list", params={"user_id": uid(), "role": "customer"}) or []
    active, counts, shown = _tabbed(orders, BUYER_TABS, request.args.get("tab", "active"))
    return render_template("orders.html", mode="buyer", tabs=BUYER_TABS, active=active, counts=counts, orders=shown)


@bp.get("/store/orders")
@seller_required
def store_orders():
    """Orders that customers placed with this seller's store."""
    params = {"user_id": uid(), "role": "seller"}
    if store_id():
        params["store_id"] = store_id()
    orders = go("GET", "/api/v1/orders/list", params=params) or []
    active, counts, shown = _tabbed(orders, STORE_TABS, request.args.get("tab", "new"))
    return render_template("orders.html", mode="store", tabs=STORE_TABS, active=active, counts=counts, orders=shown)


# ── detail ─────────────────────────────────────────────────────────────────

def _load_order(order_id):
    """Fetch an order the current user may see, with the side they're on."""
    data = go("GET", "/api/v1/orders/details", params={"order_id": order_id, "user_id": uid()})
    order, items = data["order"], data.get("items") or []
    is_buyer = order["buyer_user_id"] == uid()
    on_store_side = (
        not is_buyer
        and session["user"]["role"] == "seller"
        and (order["seller_id"] == uid() or (store_id() and order["store_id"] == store_id()))
    )
    if not is_buyer and not on_store_side:
        abort(404)
    return order, items, ("buyer" if is_buyer else "store")


def _timeline(order, history):
    """Steps shown on the tracking strip, with how far the order has got."""
    delivery = order["delivery_method"] == "delivery"
    steps = [("pending", "Order placed"), ("processing", "Being prepared")]
    if delivery:
        steps.append(("awaiting_rider", "Rider assigned"))
    steps += [("ready_to_claim", "Ready for pickup" if not delivery else "Ready"), ("completed", "Completed")]

    reached = {h["new_status"]: h["changed_at"] for h in history if h.get("new_status")}
    reached.setdefault("pending", order["created_at"])

    order_keys = [k for k, _ in steps]
    status = order["status"]
    if status == "delivered":
        status = "completed"
    position = order_keys.index(status) if status in order_keys else 0
    return [
        {
            "label": label,
            "state": "done" if i < position else "current" if i == position else "todo",
            "at": reached.get(key) if i <= position else None,
        }
        for i, (key, label) in enumerate(steps)
    ]


@bp.get("/orders/<int:order_id>")
@login_required
def detail(order_id):
    order, items, side = _load_order(order_id)

    # The Go tracking handler pulls the id out of the path with
    # `parts[4] == "tracking"`, which only matches this odd-looking route.
    # If the lookup fails the page still works from the order's current status.
    history = []
    try:
        data = go("GET", f"/api/v1/orders/tracking/{order_id}/tracking", params={"user_id": uid()})
        history = data.get("status_history") or []
    except ApiError as err:
        if err.status == 401:
            raise

    delivery = None
    if order["delivery_method"] == "delivery":
        try:
            delivery = go("GET", "/api/v1/delivery/by-order", params={"order_id": order_id})
        except ApiError as err:
            if err.status == 401:
                raise

    status = order["status"]
    can_cancel = (side == "buyer" and status in BUYER_CANCELLABLE) or (side == "store" and status not in CLOSED)
    all_prepared = all(i.get("is_prepared") for i in items) if items else False

    # Buyer talks to the order's seller; the seller who owns the order talks to the buyer.
    # Other store staff fall back to a direct chat because the order chat is limited to its seller.
    if side == "buyer":
        chat = {"type": "buyer_seller", "recipient_id": order["seller_id"], "order_id": order_id} if order["seller_id"] else None
    elif order["seller_id"] == uid():
        chat = {"type": "buyer_seller", "recipient_id": order["buyer_user_id"], "order_id": order_id}
    else:
        chat = {"type": "direct", "recipient_id": order["buyer_user_id"], "order_id": None}

    return render_template(
        "order_detail.html",
        order=order,
        items=items,
        side=side,
        steps=_timeline(order, history),
        delivery=delivery,
        can_cancel=can_cancel,
        all_prepared=all_prepared,
        chat=chat,
        low_stock=[i for i in items if i["current_stock"] < i["quantity"]],
    )


# ── actions ────────────────────────────────────────────────────────────────

def _act(order_id, expect_side, expect_status, success, call):
    """Shared guard for every order action: right side, right status, friendly errors."""
    order, items, side = _load_order(order_id)
    if side != expect_side:
        abort(403)
    if order["status"] not in expect_status:
        flash("This order has already moved on. Here's where it stands now.", "info")
        return redirect(url_for("orders.detail", order_id=order_id))
    try:
        call(order, items)
        flash(success, "success")
    except ApiError as err:
        if err.status == 401:
            raise
        flash(err.message, "error")
    return redirect(url_for("orders.detail", order_id=order_id))


@bp.post("/orders/<int:order_id>/accept")
@seller_required
def accept(order_id):
    return _act(
        order_id, "store", {"pending"}, "Order accepted. Start preparing the items.",
        lambda o, i: go("POST", "/api/v1/orders/status", json={"order_id": order_id, "status": "processing", "user_id": uid()}),
    )


@bp.post("/orders/<int:order_id>/ready")
@seller_required
def ready(order_id):
    checked = {int(x) for x in request.form.getlist("prepared") if x.isdigit()}

    def call(order, items):
        if {i["id"] for i in items} - checked:
            raise ApiError(400, "Tick every item before marking the order ready.")
        go(
            "POST",
            "/api/v1/orders/mark-ready",
            json={"order_id": order_id, "prepared_by": uid(), "item_statuses": {str(i["id"]): True for i in items}},
        )

    return _act(order_id, "store", {"processing"}, "Marked ready. The customer has been told it's waiting.", call)


@bp.post("/orders/<int:order_id>/complete")
@seller_required
def complete(order_id):
    return _act(
        order_id, "store", {"ready_to_claim"}, "Order completed.",
        lambda o, i: go("POST", "/api/v1/orders/complete", json={"order_id": order_id, "user_id": uid()}),
    )


@bp.post("/orders/<int:order_id>/cancel")
@login_required
def cancel(order_id):
    order, _items, side = _load_order(order_id)
    allowed = BUYER_CANCELLABLE if side == "buyer" else {"pending", "processing", "awaiting_rider", "ready_to_claim"}
    reason = request.form.get("reason", "").strip() or ("Cancelled by customer" if side == "buyer" else "Cancelled by seller")
    return _act(
        order_id, side, allowed, "Order cancelled.",
        lambda o, i: go(
            "POST",
            "/api/v1/orders/cancel",
            json={"order_id": order_id, "user_id": uid(), "reason": reason, "role": session["user"]["role"]},
        ),
    )


@bp.get("/orders/<int:order_id>/receipt")
@login_required
def receipt(order_id):
    _order, _items, side = _load_order(order_id)
    upstream = go(
        "GET",
        f"/api/v1/orders/{order_id}/receipt",
        params={"type": "seller" if side == "store" else "customer", "user_id": uid()},
        stream=True,
    )
    return Response(
        upstream.iter_content(chunk_size=64 * 1024),
        content_type=upstream.headers.get("Content-Type", "application/pdf"),
        headers={"Content-Disposition": f"attachment; filename=receipt_{order_id}.pdf"},
    )
