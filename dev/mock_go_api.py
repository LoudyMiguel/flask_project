"""A tiny in-memory stand-in for the Go backend, for trying the web UI without MySQL.

    python dev/mock_go_api.py            # listens on :8080

Accounts (password for all: pass1234):
    maria  customer      juan  seller (store 10)      lita  seller (store 20)
    pedro  business_owner (rejected by the web login on purpose)

It mimics the response shapes and the rules the web app depends on. It is not the real server.
"""
import itertools
import time
from datetime import datetime, timezone

from flask import Flask, Response, jsonify, request

app = Flask(__name__)
now = lambda: datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

USERS = {
    1: dict(user_id=1, username="maria", email="maria@example.com", role="customer", store_id=0, status="active"),
    2: dict(user_id=2, username="juan", email="juan@example.com", role="seller", store_id=10, status="active"),
    3: dict(user_id=3, username="pedro", email="pedro@example.com", role="business_owner", store_id=0, status="active"),
    4: dict(user_id=4, username="lita", email="lita@example.com", role="seller", store_id=20, status="active"),
    5: dict(user_id=5, username="newbie", email="newbie@example.com", role="customer", store_id=0, status="pending"),
}
for u in USERS.values():
    u.update(avatar_url="", preferred_currency="PHP", theme_preference="light", is_verified=0, location="", presence_status="online")
USERS[2]["location"] = "Poblacion, Davao City"
USERS[2]["bio"] = "Fresh produce and pantry basics, packed daily."
STORES = {10: dict(name="Juan's Sari-Sari", owner=2, type="retail"), 20: dict(name="Lita's Bakeshop", owner=4, type="retail")}

# product_id -> data; variants: id, type, value, price, original, stock
PRODUCTS = {
    1: dict(title="Native Eggs (tray of 30)", seller=2, store=10, desc="Free-range eggs from a farm in Calinan.\nCollected this morning.", unit="tray", cur="PHP",
            variants=[(101, "default", "", 285, 320, 12)], new=True),
    2: dict(title="Barako Coffee Beans", seller=2, store=10, desc="Medium roast, whole beans.", unit="pcs", cur="PHP",
            variants=[(201, "default", "", 180, None, 0), (202, "Size", "250g", 180, None, 20), (203, "Size", "500g", 340, 360, 4)]),
    3: dict(title="Ensaymada", seller=4, store=20, desc="Soft, buttery, topped with cheese.", unit="pcs", cur="PHP",
            variants=[(301, "default", "", 35, None, 40)]),
    4: dict(title="Pan de Sal (dozen)", seller=4, store=20, desc="Hot from the oven at 6 AM.", unit="pcs", cur="PHP",
            variants=[(401, "default", "", 60, None, 25)]),
    5: dict(title="Linen Tote Bag", seller=2, store=10, desc="Matrix variants demo.", unit="pcs", cur="USD",
            variants=[(501, "default", "", 20, None, 0), (502, "x", "x", 20, None, 5), (503, "x", "x", 22, 30, 3), (504, "x", "x", 20, None, 0), (505, "x", "x", 25, None, 9)]),
}
ORIGINAL_VARIANTS = {pid: list(p["variants"]) for pid, p in PRODUCTS.items()}
MATRIX = {5: dict(types=[dict(type_id=1, type_name="Colour", sort_order=0, options=[dict(option_id=11, option_value="Natural", image_url=None, sort_order=0), dict(option_id=12, option_value="Black", image_url=None, sort_order=1)]),
                         dict(type_id=2, type_name="Size", sort_order=1, options=[dict(option_id=21, option_value="Small", image_url=None, sort_order=0), dict(option_id=22, option_value="Large", image_url=None, sort_order=1)])],
              variants=[(502, [11, 21]), (503, [11, 22]), (504, [12, 21]), (505, [12, 22])])}
REVIEWS = {1: [dict(review_id=1, user_id=1, username="maria", rating=5, comment="Fresh and well packed.", is_verified_purchase=True, helpful_count=0, created_at="Sep 20, 2026", is_user_verified=False)]}

CARTS, ORDERS, ORDER_ITEMS, HISTORY = {}, {}, {}, {}
CONVOS, MESSAGES = {}, {}
cart_id_seq, order_id_seq, item_id_seq, convo_seq, msg_seq = (itertools.count(1) for _ in range(5))


def variant_of(vid):
    for pid, p in PRODUCTS.items():
        for v in p["variants"]:
            if v[0] == vid:
                return pid, p, v
    return None, None, None


def set_stock(vid, delta):
    p = next(p for p in PRODUCTS.values() if any(v[0] == vid for v in p["variants"]))
    p["variants"] = [(v[0], v[1], v[2], v[3], v[4], v[5] + delta) if v[0] == vid else v for v in p["variants"]]


def auth():
    h = request.headers.get("Authorization", "")
    if not h.startswith("Bearer token-"):
        return None
    return USERS.get(int(h.split("token-")[1]))


def need_auth(fn):
    def wrapper(*a, **kw):
        if not auth():
            return Response("Unauthorized: missing or invalid authentication", 401)
        return fn(*a, **kw)
    wrapper.__name__ = fn.__name__
    return wrapper


def err(msg, code):
    return Response(msg, code)


# ── auth ───────────────────────────────────────────────────────────────────
@app.post("/api/v1/login")
def login():
    b = request.get_json()
    u = next((u for u in USERS.values() if b["username"] in (u["username"], u["email"])), None)
    if not u or b["password"] != u.get("password", "pass1234"):
        return err("Invalid credentials", 401)
    if u["status"] != "active":
        return err("Account not verified. Please verify your email.", 403)
    return jsonify(token=f"token-{u['user_id']}", user={k: v for k, v in u.items() if k not in ("bio", "password")})


@app.post("/api/v1/register")
def register():
    b = request.get_json()
    if not b.get("username") or not b.get("email") or not b.get("password"):
        return err("Missing fields", 400)
    if any(b["username"] == u["username"] or b["email"] == u["email"] for u in USERS.values()):
        return jsonify(error="username_taken", message="Username or Email is already in use"), 409
    uid = max(USERS) + 1
    USERS[uid] = dict(user_id=uid, username=b["username"], email=b["email"], role=b["role"], store_id=0, status="pending",
                      avatar_url="", preferred_currency="PHP", theme_preference="light", is_verified=0, location="", presence_status="online", password=b["password"])
    return jsonify(message="User registered. Please verify your email."), 201


@app.post("/api/v1/verify-otp")
def verify_otp():
    b = request.get_json()
    u = next((u for u in USERS.values() if u["email"] == b["email"]), None)
    if not u:
        return err("User not found", 404)
    if b["otp"] != "123456":  # the mock's fixed code
        return err("Invalid OTP", 401)
    u["status"] = "active"
    return jsonify(message="Email verified successfully.")


@app.get("/uploads/<path:p>")
def uploads(p):
    svg = f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 200 200"><rect width="200" height="200" fill="#{abs(hash(p)) % 0xFFFFFF:06x}" opacity=".35"/><circle cx="100" cy="100" r="46" fill="#0e4a43" opacity=".5"/></svg>'
    return Response(svg, mimetype="image/svg+xml")


# ── products ───────────────────────────────────────────────────────────────
def card(pid, p):
    d = next(v for v in p["variants"] if v[1] == "default")
    return dict(product_id=pid, title=p["title"], subtitle="", is_new=p.get("new", False), is_on_sale=bool(d[4]), free_shipping=pid == 3, store_id=p["store"], seller_id=p["seller"],
                price=d[3], original_price=d[4] or 0, stock=sum(v[5] for v in p["variants"] if v[1] == "default"),
                product_image=f"uploads/p{pid}.jpg", store_name=STORES[p["store"]]["name"], seller_username=USERS[p["seller"]]["username"],
                review_count=len(REVIEWS.get(pid, [])), avg_rating=5 if pid in REVIEWS else 0, total_sold=pid * 3, currency_code=p["cur"], unit_type=p["unit"], created_at="Sep 01, 2026")


@app.get("/api/v1/customer/products")
@need_auth
def feed():
    me = auth()
    f = request.args.get("filter", "")
    out = [card(i, p) for i, p in PRODUCTS.items() if p["store"] != me["store_id"]]
    if f == "sale":
        out = [c for c in out if c["original_price"] > c["price"]]
    if f == "top_rated":
        out = [c for c in out if c["avg_rating"] >= 4]
    if f == "free_shipping":
        out = [c for c in out if c["free_shipping"]]
    return jsonify(out)


@app.get("/api/v1/search")
@need_auth
def search():
    q = request.args.get("q", "").lower()
    res = [dict(card(i, p), image_url=f"uploads/p{i}.jpg", average_rating=0) for i, p in PRODUCTS.items() if q in p["title"].lower()]
    for r in res:
        r.pop("product_image")
    return jsonify(products=res, query=q, total_results=len(res))


@app.get("/api/v1/products/variant-details")
def variant_details():
    pid = int(request.args["product_id"])
    m = MATRIX.get(pid)
    if not m:
        return jsonify(variant_types=[], variants=[])
    out = []
    for vid, opts in m["variants"]:
        _, _, v = variant_of(vid)
        out.append(dict(variant_id=vid, price=v[3], original_price=v[4], stock=v[5], image_url=None, option_ids=opts))
    return jsonify(variant_types=m["types"], variants=out)


@app.get("/api/v1/products/<int:pid>/reviews")
@need_auth
def reviews(pid):
    r = REVIEWS.get(pid, [])
    return jsonify(reviews=r, total=len(r), average_rating=5 if r else 0, page=1, total_pages=1)


@app.get("/api/v1/products/<int:pid>")
@need_auth
def product(pid):
    p = PRODUCTS.get(pid)
    if not p:
        return err("Product not found", 404)
    variants = [dict(variant_id=v[0], variant_type=v[1], variant_value=v[2], price=v[3], original_price=v[4] or 0, stock=v[5]) for v in p["variants"]]
    if pid in MATRIX:
        variants = [v for v in variants if v["variant_type"] == "default"] + [v for v in variants if v["variant_type"] != "default"]
    return jsonify(product_id=pid, title=p["title"], description=p["desc"], is_new=p.get("new", False), store_id=p["store"], seller_id=p["seller"], currency_code=p["cur"], unit_type=p["unit"],
                   images=[f"uploads/p{pid}.jpg", f"uploads/p{pid}b.jpg"] if pid == 1 else [f"uploads/p{pid}.jpg"], variants=variants,
                   store_name=STORES[p["store"]]["name"], store_logo=None, seller_username=USERS[p["seller"]]["username"])


# ── cart ───────────────────────────────────────────────────────────────────
@app.post("/api/v1/cart/add")
@need_auth
def cart_add():
    b = request.get_json()
    pid, p, v = variant_of(b["variant_id"])
    if not v:
        return err("Variant not found", 404)
    cart = CARTS.setdefault(b["user_id"], {})
    have = cart.get(b["variant_id"], 0)
    if v[5] < have + b["quantity"]:
        return jsonify(success=False, message="Insufficient stock"), 400
    cart[b["variant_id"]] = have + b["quantity"]
    return jsonify(success=True, cart_item_id=b["variant_id"], message="Item added to cart")


@app.get("/api/v1/cart/items")
@need_auth
def cart_items():
    uid = int(request.args["user_id"])
    items, total = [], 0
    for vid, q in CARTS.get(uid, {}).items():
        pid, p, v = variant_of(vid)
        items.append(dict(cart_item_id=vid, product_id=pid, title=p["title"], subtitle="", variant_id=vid, variant_type=v[1], variant_value=v[2], quantity=q, price=v[3], stock=v[5],
                          image_url=f"uploads/p{pid}.jpg", store_id=p["store"], store_name=STORES[p["store"]]["name"], store_logo="", store_owner_id=STORES[p["store"]]["owner"],
                          seller_id=p["seller"], seller_user_id=p["seller"], seller_username=USERS[p["seller"]]["username"], seller_is_verified=0, seller_avatar_url="", unit_type=p["unit"]))
        total += v[3] * q
    items.sort(key=lambda i: i["seller_id"])
    return jsonify(items=items, total_items=len(items), total_amount=total)


@app.post("/api/v1/cart/update")
@need_auth
def cart_update():
    b = request.get_json()
    cart = CARTS.get(b["user_id"], {})
    if b["cart_item_id"] not in cart:
        return err("Cart item not found", 404)
    if b["quantity"] == 0:
        del cart[b["cart_item_id"]]
    else:
        if b["quantity"] > variant_of(b["cart_item_id"])[2][5]:
            return jsonify(success=False, message="Insufficient stock"), 400
        cart[b["cart_item_id"]] = b["quantity"]
    return jsonify(success=True, message="Cart updated")


@app.post("/api/v1/cart/remove")
@need_auth
def cart_remove():
    b = request.get_json()
    if CARTS.get(b["user_id"], {}).pop(b["cart_item_id"], None) is None:
        return err("Cart item not found", 404)
    return jsonify(success=True, message="Item removed from cart")


@app.get("/api/v1/cart/count")
@need_auth
def cart_count():
    return jsonify(count=sum(CARTS.get(int(request.args["user_id"]), {}).values()))


# ── orders ─────────────────────────────────────────────────────────────────
@app.post("/api/v1/orders/create-from-cart")
@need_auth
def create_from_cart():
    b = request.get_json()
    groups = {}
    for it in b["selected_items"]:
        pid, p, v = variant_of(it["variant_id"])
        if v[5] < it["quantity"]:
            return Response(f'{{"error":"Insufficient stock for variant {it["variant_id"]} (available: {v[5]}, requested: {it["quantity"]})"}}', 400)
        groups.setdefault(it["seller_id"], []).append(it)
    created = []
    for seller, items in groups.items():
        oid = next(order_id_seq)
        ORDERS[oid] = dict(order_id=oid, buyer_user_id=b["user_id"], seller_id=seller, store_id=items[0]["store_id"], status="pending", delivery_method="pickup", contact_name=b["buyer_name"],
                           contact_phone=b["buyer_phone"], contact_address=b["buyer_address"], total_amount=sum(i["price"] * i["quantity"] for i in items), created_at=now())
        ORDER_ITEMS[oid] = [dict(id=next(item_id_seq), product_id=i["product_id"], variant_id=i["variant_id"], quantity=i["quantity"], price=i["price"], is_prepared=0) for i in items]
        HISTORY[oid] = [dict(previous_status="", new_status="pending", changed_at=now(), notes="Order placed")]
        for i in items:
            CARTS.get(b["user_id"], {}).pop(i["cart_item_id"], None)
        created.append(dict(order_id=oid, seller_id=seller, seller_username=USERS[seller]["username"], total_amount=ORDERS[oid]["total_amount"], items_count=len(items)))
    return jsonify(success=True, orders_created=created, cart_items_removed=[]), 201


def cur_of(oid):
    return PRODUCTS[ORDER_ITEMS[oid][0]["product_id"]]["cur"]


@app.get("/api/v1/orders/list")
@need_auth
def orders_list():
    uid, role = int(request.args["user_id"]), request.args.get("role")
    out = []
    for o in ORDERS.values():
        items = ORDER_ITEMS[o["order_id"]]
        if role == "seller":
            if o["store_id"] != int(request.args.get("store_id", 0)):
                continue
            out.append(dict(order_id=o["order_id"], buyer_user_id=o["buyer_user_id"], buyer_name=USERS[o["buyer_user_id"]]["username"], buyer_avatar_url="", seller_id=o["seller_id"], store_id=o["store_id"],
                            status=o["status"], delivery_method="pickup", contact_name=o["contact_name"], buyer_phone=o["contact_phone"], buyer_address="", total_amount=o["total_amount"],
                            created_at=o["created_at"], is_reviewed=False, items_count=len(items), prepared_count=sum(i["is_prepared"] for i in items), currency_code=cur_of(o["order_id"])))
        elif o["buyer_user_id"] == uid:
            out.append(dict(order_id=o["order_id"], buyer_user_id=uid, seller_id=o["seller_id"], seller_name=USERS[o["seller_id"]]["username"], store_id=o["store_id"], store_name=STORES[o["store_id"]]["name"],
                            store_logo="", status=o["status"], delivery_method="pickup", total_amount=o["total_amount"], created_at=o["created_at"], is_reviewed=False, items_count=len(items), currency_code=cur_of(o["order_id"]), items=[]))
    return jsonify(sorted(out, key=lambda o: -o["order_id"]))


@app.get("/api/v1/orders/details")
@need_auth
def order_details():
    oid, uid = int(request.args["order_id"]), int(request.args["user_id"])
    o = ORDERS.get(oid)
    me = USERS[uid]
    if not o or not (o["buyer_user_id"] == uid or o["seller_id"] == uid or o["store_id"] == me["store_id"]):
        return err("Order not found or access denied", 404)
    order = dict(o, buyer_name=USERS[o["buyer_user_id"]]["username"], buyer_avatar_url=None, buyer_is_verified=False, seller_username=USERS[o["seller_id"]]["username"],
                 store_name=STORES[o["store_id"]]["name"], currency_code=cur_of(oid))
    items = []
    for i in ORDER_ITEMS[oid]:
        pid, p, v = variant_of(i["variant_id"])
        items.append(dict(i, title=p["title"], variant_type=v[1] if v[1] != "default" else "", variant_value=v[2], image_url=f"uploads/p{pid}.jpg", currency_code=p["cur"], current_stock=v[5]))
    return jsonify(order=order, items=items)


def log(oid, new, by):
    HISTORY[oid].append(dict(previous_status=ORDERS[oid]["status"], new_status=new, changed_at=now(), notes=""))
    ORDERS[oid]["status"] = new


@app.post("/api/v1/orders/status")
@need_auth
def order_status():
    b = request.get_json()
    log(b["order_id"], b["status"], b["user_id"])
    return Response("", 200)


@app.post("/api/v1/orders/mark-ready")
@need_auth
def mark_ready():
    b = request.get_json()
    oid = b["order_id"]
    for i in ORDER_ITEMS[oid]:
        i["is_prepared"] = 1 if b["item_statuses"].get(str(i["id"])) else 0
        set_stock(i["variant_id"], -i["quantity"])
    log(oid, "ready_to_claim", b["prepared_by"])
    ORDERS[oid]["seller_id"] = b["prepared_by"]
    return jsonify(success=True, message="Order marked as ready")


@app.post("/api/v1/orders/complete")
@need_auth
def complete():
    b = request.get_json()
    o = ORDERS[b["order_id"]]
    if o["seller_id"] != b["user_id"]:
        return err("Unauthorized", 403)
    if o["status"] != "ready_to_claim":
        return err("Order must be ready to claim before completing", 400)
    log(b["order_id"], "completed", b["user_id"])
    return jsonify(success=True, message="Order completed")


@app.post("/api/v1/orders/cancel")
@need_auth
def cancel():
    b = request.get_json()
    o = ORDERS[b["order_id"]]
    ok = (o["buyer_user_id"] == b["user_id"] and o["status"] in ("pending", "processing", "awaiting_rider")) or (o["seller_id"] == b["user_id"] and o["status"] not in ("completed", "cancelled"))
    if not ok:
        return err("Cannot cancel this order", 403)
    log(b["order_id"], "cancelled", b["user_id"])
    return jsonify(success=True)


@app.get("/api/v1/orders/<path:rest>")
@need_auth
def orders_dynamic(rest):
    parts = request.path.split("/")  # mirrors the Go handlers' path parsing
    if request.path.endswith("/tracking"):
        if not (len(parts) >= 5 and parts[4] == "tracking"):
            return err("Order not found", 404)  # what the real server does for /orders/<id>/tracking
        oid = int(parts[-2])
        o = ORDERS[oid]
        return jsonify(tracking=dict(order_id=oid, status=o["status"]), status_history=HISTORY[oid])
    if request.path.endswith("/receipt"):
        return Response(b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF", mimetype="application/pdf")
    return err("404 page not found", 404)


@app.get("/api/v1/delivery/by-order")
@need_auth
def delivery():
    return Response('{"error":"No delivery for this order"}', 404)


# ── profile ────────────────────────────────────────────────────────────────
@app.get("/api/v1/profile")
@need_auth
def profile():
    u = USERS.get(int(request.args["user_id"]))
    if not u:
        return err("User not found", 404)
    user = dict(id=u["user_id"], username=u["username"], role=u["role"], status="active", created_at="2026-03-02T09:00:00Z", email=u["email"], store_id=u["store_id"] or None,
                phone_number="0917 000 0000" if u["user_id"] == auth()["user_id"] else None, is_verified=u["is_verified"], bio=u.get("bio"), avatar_url=None, presence_status="online", location=u["location"])
    store = None
    if u["store_id"]:
        s = STORES[u["store_id"]]
        store = dict(id=u["store_id"], name=s["name"], company_type=s["type"])
    return jsonify(user=user, store=store, relationship_status="none", stats=dict(followers=3, following=1, products=sum(p["store"] == u["store_id"] for p in PRODUCTS.values()), sales=len([o for o in ORDERS.values() if o["store_id"] == u["store_id"] and o["status"] == "completed"])))


# ── chat ───────────────────────────────────────────────────────────────────
def convo_detail(cid, me):
    c = CONVOS[cid]
    return dict(conversation_id=cid, type=c["type"], order_id=c["order_id"], product_id=c["product_id"], last_message_at=c["last"], created_at=now(),
                participants=[dict(user_id=u, username=USERS[u]["username"], avatar_url=None, presence_status="online") for u in c["users"]])


def member(cid):
    me = auth()
    c = CONVOS.get(cid)
    return c if c and me and me["user_id"] in c["users"] else None


@app.route("/api/chat/conversations", methods=["GET", "POST"])
@need_auth
def convos():
    me = auth()["user_id"]
    if request.method == "POST":
        b = request.get_json()
        if b["type"] == "buyer_seller" and b.get("order_id"):
            o = ORDERS.get(b["order_id"])
            if not o or not ((me == o["buyer_user_id"] and b["recipient_id"] == o["seller_id"]) or (me == o["seller_id"] and b["recipient_id"] == o["buyer_user_id"])):
                return jsonify(error="not authorized for this conversation"), 403
        for cid, c in CONVOS.items():
            if c["type"] == b["type"] and c["order_id"] == b.get("order_id") and c["product_id"] == b.get("product_id") and set(c["users"]) == {me, b["recipient_id"]}:
                return jsonify(convo_detail(cid, me)), 200
        cid = next(convo_seq)
        CONVOS[cid] = dict(type=b["type"], order_id=b.get("order_id"), product_id=b.get("product_id"), users=[me, b["recipient_id"]], last=None, read={me: 0})
        MESSAGES[cid] = []
        return jsonify(convo_detail(cid, me)), 201
    out = []
    for cid, c in CONVOS.items():
        if me not in c["users"]:
            continue
        other = next(u for u in c["users"] if u != me)
        msgs = [m for m in MESSAGES[cid] if not m["is_deleted"]]
        out.append(dict(conversation_id=cid, type=c["type"], order_id=c["order_id"], product_id=c["product_id"], unread_count=sum(1 for m in msgs if m["sender_id"] != me and m["message_id"] > c["read"].get(me, 0)),
                        last_message_preview=msgs[-1]["body"] if msgs else None, last_message_type="text" if msgs else None, last_message_at=c["last"], created_at=now(),
                        other_participant=dict(user_id=other, username=USERS[other]["username"], avatar_url=None, presence_status="online", last_seen=now())))
    return jsonify(conversations=out, total=len(out))


@app.get("/api/chat/conversations/<int:cid>")
@need_auth
def convo_get(cid):
    if not member(cid):
        return jsonify(error="not a participant"), 403
    return jsonify(convo_detail(cid, auth()["user_id"]))


@app.route("/api/chat/conversations/<int:cid>/messages", methods=["GET", "POST"])
@need_auth
def convo_messages(cid):
    if not member(cid):
        return jsonify(error="not a participant"), 403
    me = auth()["user_id"]
    if request.method == "POST":
        b = request.get_json()
        m = dict(message_id=next(msg_seq), conversation_id=cid, sender_id=me, sender_username=USERS[me]["username"], sender_avatar=None, message_type="text", body=b["body"],
                 is_deleted=False, created_at=now(), ref_order=None, ref_product=None, location=None)
        MESSAGES[cid].append(m)
        CONVOS[cid]["last"] = now()
        return jsonify(m), 201
    limit = int(request.args.get("limit", 30))
    before = int(request.args.get("before_id", 0))
    msgs = [m for m in MESSAGES[cid] if not before or m["message_id"] < before][-limit:]
    return jsonify(messages=[dict(m, body=None if m["is_deleted"] else m["body"]) for m in msgs], has_more=len(msgs) == limit, next_before_id=msgs[0]["message_id"] if msgs and len(msgs) == limit else None)


@app.post("/api/chat/conversations/<int:cid>/read")
@need_auth
def convo_read(cid):
    c = member(cid)
    if not c:
        return jsonify(error="not a participant"), 403
    c["read"][auth()["user_id"]] = max((m["message_id"] for m in MESSAGES[cid]), default=0)
    return jsonify(ok=True)


@app.delete("/api/chat/messages/<int:mid>")
@need_auth
def msg_delete(mid):
    for ms in MESSAGES.values():
        for m in ms:
            if m["message_id"] == mid:
                if m["sender_id"] != auth()["user_id"]:
                    return jsonify(error="cannot delete another user's message"), 403
                m["is_deleted"] = True
                return jsonify(ok=True)
    return jsonify(error="message not found"), 404


@app.get("/api/v1/ping")
def ping():
    return "pong"


@app.post("/__reset")
def reset():
    """Dev-only: wipe carts, orders and chats (and restock) so test runs start clean."""
    global order_id_seq, item_id_seq, convo_seq, msg_seq
    for d in (CARTS, ORDERS, ORDER_ITEMS, HISTORY, CONVOS, MESSAGES):
        d.clear()
    order_id_seq, item_id_seq, convo_seq, msg_seq = (itertools.count(1) for _ in range(4))
    for pid, p in PRODUCTS.items():
        p["variants"] = list(ORIGINAL_VARIANTS[pid])
    return jsonify(ok=True)


if __name__ == "__main__":
    from waitress import serve
    print("Mock MarketFlow Go API on http://127.0.0.1:8080  (accounts: maria / juan / lita, password pass1234)")
    serve(app, host="127.0.0.1", port=8080, threads=8)
