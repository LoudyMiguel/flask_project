from flask import Blueprint, current_app, flash, redirect, render_template, request, url_for

from .api import ApiError, go
from .helpers import int_arg, login_required, normalize_product, store_id, uid

bp = Blueprint("shop", __name__)

PAGE_SIZE = 20
FEED_FILTERS = [
    ("all", "All"),
    ("sale", "On sale"),
    ("top_rated", "Top rated"),
    ("most_popular", "Most popular"),
    ("free_shipping", "Free shipping"),
]
SEARCH_FILTERS = FEED_FILTERS[:2]  # /search only understands "all products" and "sale"


# ── browse ─────────────────────────────────────────────────────────────────

@bp.get("/shop")
@login_required
def browse():
    q = request.args.get("q", "").strip()
    page = int_arg("page")
    allowed = dict(SEARCH_FILTERS if q else FEED_FILTERS)
    active = request.args.get("filter", "all")
    if active not in allowed:
        active = "all"

    if q:
        data = go(
            "GET",
            "/api/v1/search",
            params={"q": q, "filter": "sale" if active == "sale" else "products", "user_id": uid(), "page": page, "limit": PAGE_SIZE},
        )
        raw = data.get("products") or []
    else:
        params = {"user_id": uid(), "page": page, "limit": PAGE_SIZE}
        if active != "all":
            params["filter"] = active
        raw = go("GET", "/api/v1/customer/products", params=params) or []

    return render_template(
        "browse.html",
        products=[normalize_product(p) for p in raw],
        q=q,
        active=active,
        filters=SEARCH_FILTERS if q else FEED_FILTERS,
        page=page,
        has_next=len(raw) >= PAGE_SIZE,
    )


# ── product ────────────────────────────────────────────────────────────────

def _variant_model(detail):
    """Describe how the buyer picks a variant, in the shape product.js expects."""
    variants = detail.get("variants") or []
    default = next((v for v in variants if v.get("variant_type") == "default"), None)

    matrix = {"variant_types": [], "variants": []}
    try:
        matrix = go("GET", "/api/v1/products/variant-details", params={"product_id": detail["product_id"]})
    except ApiError:
        pass

    if matrix.get("variant_types") and matrix.get("variants"):
        return {
            "mode": "matrix",
            "types": matrix["variant_types"],
            "variants": [
                {
                    "id": v["variant_id"],
                    "price": v["price"],
                    "original_price": v.get("original_price"),
                    "stock": v["stock"],
                    "option_ids": v.get("option_ids") or [],
                }
                for v in matrix["variants"]
            ],
        }

    named = [v for v in variants if v.get("variant_type") != "default"]
    if named:
        return {
            "mode": "list",
            "variants": [
                {
                    "id": v["variant_id"],
                    "label": f"{v.get('variant_type', '')}: {v.get('variant_value', '')}".strip(": "),
                    "price": v["price"],
                    "original_price": v.get("original_price") or None,
                    "stock": v["stock"],
                }
                for v in named
            ],
        }

    if default is None and variants:
        default = variants[0]
    if default is None:
        return {"mode": "none", "variants": []}
    return {
        "mode": "single",
        "variants": [
            {
                "id": default["variant_id"],
                "price": default["price"],
                "original_price": default.get("original_price") or None,
                "stock": default["stock"],
            }
        ],
    }


@bp.get("/product/<int:pid>")
@login_required
def product(pid):
    detail = go("GET", f"/api/v1/products/{pid}")
    try:
        reviews = go("GET", f"/api/v1/products/{pid}/reviews")
    except ApiError:
        reviews = {"reviews": [], "total": 0, "average_rating": 0}

    own_store = store_id() and detail.get("store_id") == store_id()
    is_own = detail.get("seller_id") == uid() or bool(own_store)
    return render_template(
        "product.html",
        p=detail,
        model=_variant_model(detail),
        reviews=reviews,
        is_own=is_own,
    )


# ── cart ───────────────────────────────────────────────────────────────────

def _currency_for(product_id):
    """Cart rows carry no currency, so look it up once per product."""
    cache = current_app.extensions["currency_cache"]
    if product_id not in cache:
        try:
            cache[product_id] = go("GET", f"/api/v1/products/{product_id}").get("currency_code") or "PHP"
        except ApiError:
            return "PHP"
    return cache[product_id]


def _load_cart():
    data = go("GET", "/api/v1/cart/items", params={"user_id": uid()}) or {}
    items = data.get("items") or []
    for item in items:
        item["currency"] = _currency_for(item["product_id"])
        item["line_total"] = item["price"] * item["quantity"]
    return items


def _group_by_seller(items):
    groups = {}
    for item in items:
        key = item["seller_id"]
        group = groups.setdefault(
            key,
            {
                "seller_id": key,
                "seller_name": item.get("seller_username") or "Seller",
                "store_name": item["store_name"],
                "items": [],
            },
        )
        group["items"].append(item)
    return list(groups.values())


def _totals_by_currency(items):
    totals = {}
    for item in items:
        totals[item["currency"]] = totals.get(item["currency"], 0) + item["line_total"]
    return totals


def _back(default="shop.browse"):
    target = request.form.get("next", "")
    if target.startswith("/") and not target.startswith("//"):
        return redirect(target)
    return redirect(url_for(default))


@bp.get("/cart")
@login_required
def cart():
    items = _load_cart()
    return render_template("cart.html", groups=_group_by_seller(items), count=len(items))


@bp.post("/cart/add")
@login_required
def cart_add():
    try:
        variant_id = int(request.form["variant_id"])
        quantity = float(request.form.get("quantity", 1))
    except (KeyError, ValueError):
        flash("Choose an option before adding to your cart.", "error")
        return _back()
    if quantity <= 0:
        quantity = 1

    try:
        go("POST", "/api/v1/cart/add", json={"user_id": uid(), "variant_id": variant_id, "quantity": quantity})
    except ApiError as err:
        if err.status == 401:
            raise
        flash(err.message if "stock" in err.message.lower() else f"Couldn't add that to your cart. {err.message}", "error")
        return _back()

    if request.form.get("action") == "buy":
        return redirect(url_for("shop.cart"))
    flash("Added to your cart.", "success")
    return _back()


@bp.post("/cart/update")
@login_required
def cart_update():
    try:
        item_id = int(request.form["cart_item_id"])
        quantity = float(request.form["quantity"])
    except (KeyError, ValueError):
        flash("Enter a quantity of 0 or more.", "error")
        return redirect(url_for("shop.cart"))
    try:
        go("POST", "/api/v1/cart/update", json={"cart_item_id": item_id, "user_id": uid(), "quantity": max(quantity, 0)})
    except ApiError as err:
        if err.status == 401:
            raise
        flash(err.message if "stock" in err.message.lower() else f"Couldn't update your cart. {err.message}", "error")
    return redirect(url_for("shop.cart"))


@bp.post("/cart/remove")
@login_required
def cart_remove():
    try:
        item_id = int(request.form["cart_item_id"])
        go("POST", "/api/v1/cart/remove", json={"cart_item_id": item_id, "user_id": uid()})
        flash("Removed from your cart.", "info")
    except (KeyError, ValueError):
        pass
    except ApiError as err:
        if err.status == 401:
            raise
        flash(f"Couldn't remove that item. {err.message}", "error")
    return redirect(url_for("shop.cart"))


# ── checkout ───────────────────────────────────────────────────────────────

def _selected_items(raw_ids):
    wanted = {i for i in raw_ids if i.isdigit()}
    return [i for i in _load_cart() if str(i["cart_item_id"]) in wanted]


@bp.get("/checkout")
@login_required
def checkout():
    items = _selected_items(request.args.getlist("items"))
    if not items:
        flash("Pick at least one item in your cart to check out.", "error")
        return redirect(url_for("shop.cart"))
    return render_template("checkout.html", groups=_group_by_seller(items), totals=_totals_by_currency(items), items=items)


@bp.post("/checkout")
@login_required
def place_order():
    # Prices, sellers and stores come from the server-side cart, never from the form.
    items = _selected_items(request.form.getlist("items"))
    name = request.form.get("buyer_name", "").strip()
    phone = request.form.get("buyer_phone", "").strip()

    def retry():
        return redirect(url_for("shop.checkout", items=[i["cart_item_id"] for i in items]))

    if not items:
        flash("Those items are no longer in your cart.", "error")
        return redirect(url_for("shop.cart"))
    if not name or not phone:
        flash("Add a contact name and phone number so the seller can reach you.", "error")
        return retry()
    if store_id() and any(i["store_id"] == store_id() for i in items):
        flash("You can't order from your own store. Remove those items to continue.", "error")
        return retry()

    payload = {
        "user_id": uid(),
        "delivery_method": "pickup",
        "buyer_name": name,
        "buyer_phone": phone,
        "buyer_address": "Store pickup",
        "selected_items": [
            {
                "cart_item_id": i["cart_item_id"],
                "product_id": i["product_id"],
                "variant_id": i["variant_id"],
                "quantity": i["quantity"],
                "price": i["price"],
                "seller_id": i["seller_id"],
                "store_id": i["store_id"],
            }
            for i in items
        ],
    }
    try:
        result = go("POST", "/api/v1/orders/create-from-cart", json=payload)
    except ApiError as err:
        if err.status == 401:
            raise
        flash(err.message, "error")
        return retry()

    created = result.get("orders_created") or []
    if len(created) == 1:
        flash("Order placed. The seller has been notified.", "success")
        return redirect(url_for("orders.detail", order_id=created[0]["order_id"]))
    flash(f"{len(created)} orders placed, one for each seller.", "success")
    return redirect(url_for("orders.my_orders"))
