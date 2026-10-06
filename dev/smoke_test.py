"""End-to-end check of the web app against the mock Go API (python dev/mock_go_api.py).

    python dev/smoke_test.py
"""
import re
import sys

import requests

sys.path.insert(0, ".")
from app import create_app  # noqa: E402

requests.post("http://localhost:8080/__reset", timeout=5).raise_for_status()

app = create_app()
app.config["TESTING"] = True
passed = failed = 0


def check(label, cond, extra=""):
    global passed, failed
    if cond:
        passed += 1
        print(f"  ok   {label}")
    else:
        failed += 1
        print(f"  FAIL {label} {extra}")


class User:
    def __init__(self, name, password="pass1234"):
        self.c = app.test_client()
        self.name, self.password = name, password

    def csrf(self):
        with self.c.session_transaction() as s:
            return s.get("csrf", "")

    def get(self, url, **kw):
        return self.c.get(url, **kw)

    def post(self, url, data=None, json=None, **kw):
        if json is not None:
            return self.c.post(url, json=json, headers={"X-CSRF-Token": self.csrf()}, **kw)
        return self.c.post(url, data={**(data or {}), "csrf_token": self.csrf()}, **kw)

    def login(self):
        self.get("/login")
        return self.post("/login", {"username": self.name, "password": self.password})


def text(resp):
    return resp.get_data(as_text=True)


print("auth")
anon = User("x")
r = anon.get("/shop")
check("anonymous /shop redirects to login", r.status_code == 302 and "/login" in r.location)
r = anon.post("/login", {"username": "maria", "password": "pass1234"})
check("POST without csrf is rejected", r.status_code == 400)
r = User("maria", "wrong").login()
check("wrong password shows a friendly error", r.status_code == 401 and "match an account" in text(r))
r = User("pedro").login()
check("business_owner is refused", r.status_code == 403 and "customer and seller" in text(r))
r = User("newbie").login()
check("unverified account explains why", r.status_code == 403 and "verified yet" in text(r))
r = anon.get("/login?next=//evil.example")
check("login page renders", r.status_code == 200)
maria = User("maria")
r = maria.login()
check("customer logs in", r.status_code == 302 and r.location.endswith("/shop"), r.location)

print("sign up")
nu = User("rosa")
check("signup page renders", nu.get("/signup").status_code == 200 and "Create your account" in text(nu.get("/signup")))
r = nu.post("/signup", {"username": "ro", "email": "rosa@example.com", "password": "longenough1", "role": "customer"})
check("short username rejected", r.status_code == 400 and "at least 3" in text(r))
r = nu.post("/signup", {"username": "rosa", "email": "nope", "password": "longenough1", "role": "customer"})
check("bad email rejected", r.status_code == 400 and "valid email" in text(r))
r = nu.post("/signup", {"username": "rosa", "email": "rosa@example.com", "password": "short", "role": "customer"})
check("short password rejected", r.status_code == 400 and "8 characters" in text(r))
r = nu.post("/signup", {"username": "rosa", "email": "rosa@example.com", "password": "longenough1", "role": "business_owner"})
check("web signup refuses other roles", r.status_code == 400)
r = nu.post("/signup", {"username": "maria", "email": "new@example.com", "password": "longenough1", "role": "customer"})
check("duplicate username explained", r.status_code == 409 and "already in use" in text(r))
r = nu.post("/signup", {"username": "rosa", "email": "rosa@example.com", "password": "longenough1", "role": "customer"})
check("signup redirects to verify", r.status_code == 302 and "/verify?email=rosa@example.com" in r.location, r.location)
nu.password = "longenough1"
check("cannot log in before verifying", nu.login().status_code == 403)
r = nu.post("/verify", {"email": "rosa@example.com", "otp": "000000"})
check("wrong code explained", r.status_code == 401 and "wrong or has expired" in text(r))
r = nu.post("/verify", {"email": "nobody@example.com", "otp": "123456"})
check("unknown email explained", r.status_code == 404)
r = nu.post("/verify", {"email": "rosa@example.com", "otp": "123456"})
check("correct code sends to login", r.status_code == 302 and r.location.endswith("/login"))
check("new account can log in", nu.login().status_code == 302)

print("browse")
r = maria.get("/shop")
html = text(r)
check("feed lists products", r.status_code == 200 and "Native Eggs" in html and "Ensaymada" in html)
check("price tags show currency", "₱285.00" in html and "$20.00" in html)
check("sale tag shows original price", "<s>₱320.00</s>" in html)
check("images go through /media", "/media/uploads/p1.jpg" in html)
r = maria.get("/shop?filter=sale")
check("sale filter narrows results", "Native Eggs" in text(r) and "Ensaymada" not in text(r))
r = maria.get("/shop?q=coffee")
check("search finds coffee", "Barako Coffee" in text(r) and "Ensaymada" not in text(r))
r = maria.get("/shop?q=zzzz")
check("empty search shows guidance", "Nothing matches yet" in text(r))
r = maria.get("/media/uploads/p1.jpg")
check("media proxy streams image", r.status_code == 200 and r.mimetype == "image/svg+xml")
check("media proxy blocks traversal", maria.get("/media/../etc/passwd").status_code == 404 and maria.get("/media/secret.txt").status_code == 404)

print("product")
r = maria.get("/product/1")
html = text(r)
check("simple product renders", r.status_code == 200 and "Native Eggs" in html and 'name="variant_id"' in html and 'value="101"' in html)
check("reviews shown", "Fresh and well packed" in html and "Verified purchase" in html)
r = maria.get("/product/2")
html = text(r)
check("list-variant product offers named variants", "Size: 250g" in html and "Size: 500g" in html)
r = maria.get("/product/5")
html = text(r)
check("matrix product renders option groups + model json", "Colour" in html and "variant-model" in html and '"mode": "matrix"' in html.replace('":"', '": "') or '"mode":"matrix"' in html)
check("missing product gives 404 page", maria.get("/product/999").status_code == 404)

print("cart + checkout")
r = maria.post("/cart/add", {"variant_id": "101", "quantity": "2", "next": "/product/1", "action": "add"})
check("add to cart redirects back", r.status_code == 302 and r.location.endswith("/product/1"))
r = maria.post("/cart/add", {"variant_id": "301", "quantity": "3", "action": "add", "next": "/shop"})
r = maria.post("/cart/add", {"variant_id": "101", "quantity": "99", "next": "/product/1"}, follow_redirects=True)
check("over-stock add shows a clear message", "Insufficient stock" in text(r))
r = maria.get("/api/badges")
check("badge count sums quantities", r.get_json() == {"cart": 5, "unread": 0}, r.get_json())
r = maria.get("/cart")
html = text(r)
check("cart groups by seller", "Juan&#39;s Sari-Sari" in html and "Lita&#39;s Bakeshop" in html)
check("cart line totals", "₱570.00" in html and "₱105.00" in html)
r = maria.post("/cart/update", {"cart_item_id": "301", "quantity": "4"})
r = maria.get("/cart")
check("quantity update saved", "₱140.00" in text(r))
r = maria.post("/cart/update", {"cart_item_id": "301", "quantity": "999"}, follow_redirects=True)
check("update beyond stock explains", "Insufficient stock" in text(r))
r = maria.post("/cart/add", {"variant_id": "401", "quantity": "1", "next": "/shop"})
r = maria.post("/cart/remove", {"cart_item_id": "401"})
r = maria.get("/cart")
check("remove works", "Pan de Sal" not in text(r))
r = maria.get("/checkout")
check("checkout without selection bounces to cart", r.status_code == 302 and r.location.endswith("/cart"))
r = maria.get("/checkout?items=101&items=301")
html = text(r)
check("checkout shows summary", r.status_code == 200 and "Pickup details" in html and "₱710.00" in html)
r = maria.post("/checkout", {"items": ["101", "301"], "buyer_name": "", "buyer_phone": ""}, follow_redirects=True)
check("checkout requires contact details", "Add a contact name and phone" in text(r))
r = maria.post("/checkout", {"items": ["101", "301"], "buyer_name": "Maria Santos", "buyer_phone": "0917 123 4567"})
check("two sellers -> two orders -> orders list", r.status_code == 302 and r.location.endswith("/orders"), r.location)
r = maria.get("/orders")
html = text(r)
check("orders list shows both pending orders", "Order #1" in html and "Order #2" in html and "Waiting for the seller" in html)
check("cart emptied after checkout", maria.get("/api/badges").get_json()["cart"] == 0)

print("seller flow (juan, store 10, order #1)")
juan = User("juan")
check("seller logs in", juan.login().status_code == 302)
check("seller sees Store orders nav", "Store orders" in text(juan.get("/shop")))
check("customer cannot open store orders", maria.get("/store/orders").status_code == 403)
r = juan.get("/store/orders")
html = text(r)
check("store orders list shows new order from maria", "Order #1" in html and "From maria" in html and "Order #2" not in html)
r = juan.get("/orders/1")
html = text(r)
check("seller sees customer panel + accept", "Accept order" in html and "0917 123 4567" in html and "Message customer" in html)
lita = User("lita")
check("second seller logs in", lita.login().status_code == 302)
check("lita (other store) gets 404 for order 1", lita.get("/orders/1").status_code == 404)
check("customer cannot accept orders", maria.post("/orders/1/accept").status_code == 403)
r = juan.post("/orders/1/accept", follow_redirects=True)
html = text(r)
check("accept moves order to preparing", "Order accepted" in html and "Prepare items" in html and "Being prepared" in html)
r = juan.post("/orders/1/ready", {}, follow_redirects=True)
check("ready is refused until items are ticked", "Tick every item" in text(r))
r = juan.post("/orders/1/ready", {"prepared": ["1"]}, follow_redirects=True)
html = text(r)
check("ready works", "Marked ready" in html and "Waiting for pickup" in html and "Complete order" in html)
check("stock was deducted (12 -> 10)", re.search(r'"stock":\s*10', text(maria.get("/product/1"))) is not None)
r = maria.get("/orders/1")
html = text(r)
check("customer sees ready for pickup + message button, no cancel at this stage", "Ready for pickup" in html and "Message seller" in html and "Cancel this order" not in html)
check("progress strip has timestamps from tracking", "<time>" in html)
r = juan.post("/orders/1/complete", follow_redirects=True)
check("complete works", "Order completed" in text(r) and "Completed" in text(r))
r = juan.post("/orders/1/complete", follow_redirects=True)
check("repeat action is handled gracefully", "already moved on" in text(r))
r = maria.get("/orders/1/receipt")
check("receipt downloads as pdf", r.status_code == 200 and r.mimetype == "application/pdf" and r.data.startswith(b"%PDF"))

print("cancel (order #2, lita)")
r = maria.get("/orders/2")
check("customer sees cancel option while pending", "Cancel this order" in text(r))
r = maria.post("/orders/2/cancel", {"reason": "Changed my mind"}, follow_redirects=True)
html = text(r)
check("customer can cancel pending order", "Order cancelled" in html and "This order was cancelled" in html)
r = maria.get("/orders?tab=cancelled")
check("cancelled tab lists it", "Order #2" in text(r))

print("chat")
r = maria.post("/messages/start", {"type": "buyer_seller", "recipient_id": "2", "order_id": "1"})
check("start chat from order", r.status_code == 302 and "/messages/1" in r.location, r.location)
r = maria.post("/messages/start", {"type": "buyer_seller", "recipient_id": "2", "order_id": "1"})
check("same chat is reused", r.location.endswith("/messages/1"))
r = maria.get("/messages/1")
html = text(r)
check("thread page renders with participant + order link", r.status_code == 200 and "juan" in html and "order #1" in html)
r = maria.post("/api/chat/1/messages", json={"body": "Hi! Is the order ready?"})
check("send message", r.status_code == 201 and r.get_json()["body"] == "Hi! Is the order ready?")
r = maria.post("/api/chat/1/messages", json={"body": "   "})
check("blank message rejected", r.status_code == 400)
r = maria.post("/api/chat/1/messages", json={"body": "x" * 2001})
check("overlong message rejected", r.status_code == 400)
check("chat POST without csrf rejected", maria.c.post("/api/chat/1/messages", json={"body": "hi"}).status_code == 400)
check("unread badge for seller", juan.get("/api/badges").get_json()["unread"] == 1)
r = juan.get("/api/chat/conversations")
c = r.get_json()["conversations"][0]
check("seller inbox shows preview + unread", c["unread_count"] == 1 and c["last_message_preview"].startswith("Hi!") and c["other_participant"]["username"] == "maria")
r = juan.get("/api/chat/1/messages?limit=40")
check("seller loads messages", len(r.get_json()["messages"]) == 1)
juan.post("/api/chat/1/messages", json={"body": "Yes, come by anytime."})
juan.post("/api/chat/1/read", json={})
check("unread cleared after read", juan.get("/api/badges").get_json()["unread"] == 0)
check("outsider cannot open thread", lita.get("/messages/1").status_code == 403)
check("outsider cannot read messages", lita.get("/api/chat/1/messages").status_code == 403)
mid = maria.get("/api/chat/1/messages").get_json()["messages"][0]["message_id"]
check("cannot delete someone else's message", juan.c.delete(f"/api/chat/messages/{mid}", headers={"X-CSRF-Token": juan.csrf()}).status_code == 403)
check("can delete own message", maria.c.delete(f"/api/chat/messages/{mid}", headers={"X-CSRF-Token": maria.csrf()}).status_code == 200)
r = maria.post("/messages/start", {"type": "buyer_seller", "recipient_id": "2", "product_id": "1"})
check("start chat from product", r.status_code == 302 and "/messages/2" in r.location, r.location)
r = maria.post("/messages/start", {"type": "direct", "recipient_id": "4"})
check("start direct chat from profile", r.status_code == 302)

print("profile")
r = juan.get("/profile/1")
html = text(r)
check("seller can view customer profile", r.status_code == 200 and "maria" in html and "Customer" in html and "maria@example.com" not in html)
r = maria.get("/profile")
check("own profile redirects + shows own email", maria.get("/profile", follow_redirects=True).status_code == 200 and "maria@example.com" in text(maria.get("/profile", follow_redirects=True)))
r = maria.get("/profile/2")
html = text(r)
check("customer sees seller store card", "Juan&#39;s Sari-Sari" in html and "Poblacion" in html and "juan@example.com" not in html)
check("unknown profile is 404", maria.get("/profile/999").status_code == 404)

print("misc")
r = maria.post("/logout")
check("logout clears session", r.status_code == 302 and maria.get("/shop").status_code == 302)
check("token never reaches the browser", "token-" not in text(juan.get("/shop")))

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
