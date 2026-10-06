"""Template filters, session helpers and shape-normalisers for Go responses."""
import secrets
from datetime import datetime
from urllib.parse import urlparse

from flask import abort, redirect, request, session, url_for
from functools import wraps

CURRENCY_SYMBOLS = {"PHP": "₱", "USD": "$", "EUR": "€", "GBP": "£", "JPY": "¥"}

STATUS = {
    "pending": ("Waiting for the seller", "amber"),
    "processing": ("Being prepared", "blue"),
    "awaiting_rider": ("Waiting for a rider", "blue"),
    "ready_to_claim": ("Ready for pickup", "green"),
    "delivered": ("Delivered", "green"),
    "completed": ("Completed", "green"),
    "cancelled": ("Cancelled", "red"),
}

ROLE_LABELS = {
    "customer": "Customer",
    "seller": "Seller",
    "business_owner": "Business owner",
    "manufacturer": "Manufacturer",
    "delivery_rider": "Rider",
    "courier": "Courier",
}


# ── session ────────────────────────────────────────────────────────────────

def current_user():
    return session.get("user")


def uid():
    user = current_user()
    return int(user["user_id"]) if user else 0


def store_id():
    user = current_user()
    return int(user.get("store_id") or 0) if user else 0


def csrf_token():
    if "csrf" not in session:
        session["csrf"] = secrets.token_urlsafe(32)
    return session["csrf"]


def login_required(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        if not session.get("token"):
            if request.path.startswith("/api/"):
                abort(401)
            return redirect(url_for("auth.login", next=request.full_path.rstrip("?")))
        return view(*args, **kwargs)

    return wrapper


def seller_required(view):
    @wraps(view)
    @login_required
    def wrapper(*args, **kwargs):
        user = current_user()
        if not user or user.get("role") != "seller":
            abort(403)
        return view(*args, **kwargs)

    return wrapper


def safe_next(target):
    """Only allow same-site relative redirects."""
    if not target:
        return None
    parsed = urlparse(target)
    if parsed.scheme or parsed.netloc or not target.startswith("/") or target.startswith("//"):
        return None
    return target


def int_arg(name, default=1, minimum=1):
    try:
        return max(int(request.args.get(name, default)), minimum)
    except (TypeError, ValueError):
        return default


# ── template filters ───────────────────────────────────────────────────────

def money(value, code="PHP"):
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = 0.0
    code = (code or "PHP").upper()
    symbol = CURRENCY_SYMBOLS.get(code, code + " ")
    return f"{symbol}{number:,.2f}"


def qty(value):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "0"
    return str(int(number)) if number == int(number) else f"{number:g}"


def media(path):
    """Uploaded files live on the Go server; serve them through our own /media route."""
    if not path:
        return ""
    if path.startswith(("http://", "https://")):
        return path
    return url_for("main.media", path=path.lstrip("/"))


def parse_dt(value):
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    text = str(value).replace("Z", "+00:00")
    for candidate in (text, text.replace(" ", "T")):
        try:
            return datetime.fromisoformat(candidate)
        except ValueError:
            continue
    for fmt in ("%b %d, %Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(str(value), fmt)
        except ValueError:
            continue
    return None


def dt(value, with_time=True):
    parsed = parse_dt(value)
    if not parsed:
        return value or ""
    if with_time:
        return parsed.strftime("%b %d, %Y, %I:%M %p").replace(" 0", " ")
    return parsed.strftime("%b %d, %Y")


def status_label(status):
    return STATUS.get(status, (str(status).replace("_", " ").capitalize(), "grey"))[0]


def status_tone(status):
    return STATUS.get(status, ("", "grey"))[1]


def role_label(role):
    return ROLE_LABELS.get(role, str(role or "").replace("_", " ").capitalize())


def initials(name):
    parts = (name or "?").replace("_", " ").split()
    return "".join(p[0] for p in parts[:2]).upper() or "?"


FILTERS = {
    "money": money,
    "qty": qty,
    "media": media,
    "dt": dt,
    "status_label": status_label,
    "status_tone": status_tone,
    "role_label": role_label,
    "initials": initials,
}


# ── response normalisers ───────────────────────────────────────────────────

def normalize_product(p):
    """Feed and search endpoints return slightly different keys; unify them."""
    price = p.get("price") or 0
    original = p.get("original_price") or 0
    stock = p.get("stock", p.get("total_stock"))
    return {
        "id": p.get("product_id"),
        "title": p.get("title") or "Untitled product",
        "subtitle": p.get("subtitle") or "",
        "price": price,
        "original_price": original if original and original > price else None,
        "image": p.get("product_image") or p.get("image_url") or p.get("image") or "",
        "store_name": p.get("store_name") or "",
        "seller_name": p.get("seller_username") or "",
        "seller_id": p.get("seller_id") or 0,
        "store_id": p.get("store_id") or 0,
        "rating": p.get("avg_rating") or p.get("average_rating") or 0,
        "reviews": p.get("review_count") or 0,
        "sold": p.get("total_sold") or 0,
        "stock": stock,
        "currency": p.get("currency_code") or "PHP",
        "unit": p.get("unit_type") or "pcs",
        "is_new": bool(p.get("is_new")),
        "free_shipping": bool(p.get("free_shipping")),
    }
