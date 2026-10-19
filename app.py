import hashlib
import logging
import os
import re
import secrets
import smtplib
import sqlite3
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from email.message import EmailMessage
from pathlib import Path
from urllib.parse import urljoin

from dotenv import load_dotenv
from flask import Flask, abort, flash, jsonify, redirect, render_template, request, send_from_directory, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash


ROOT = Path(__file__).resolve().parent
INSTANCE = ROOT / "instance"
DATABASE = INSTANCE / "bidmart.sqlite3"
DEVELOPMENT_SECRET_FILE = INSTANCE / "flask-secret.key"
DEMO_AUCTION_SLUG = "iphone-14-pro-max"
AUCTION_LISTINGS = (
    {
        "slug": DEMO_AUCTION_SLUG,
        "name": "iPhone 14 Pro Max (256GB)",
        "category": "Smartphones",
        "description": "Deep Purple · 256GB · Powerful triple-camera system.",
        "image": "products/iphone-14-pro.png",
        "icon": None,
        "original_price": 125000,
        "starting_bid": 92500,
        "duration_days": 7,
        "minimum_increment": 500,
    },
    {
        "slug": "smart-watch-bluetooth",
        "name": "Smart Watch (Bluetooth Calling)",
        "category": "Wearables",
        "description": "Bluetooth calling, heart-rate monitor, and IP68 water resistance.",
        "image": "products/smart-watch.png",
        "icon": None,
        "original_price": 4000,
        "starting_bid": 2200,
        "duration_days": 3,
        "minimum_increment": 100,
    },
    {
        "slug": "jbl-wireless-headphones",
        "name": "JBL Wireless Headphones",
        "category": "Audio",
        "description": "Wireless over-ear headphones with deep bass and long battery life.",
        "image": "products/jbl-headphones.png",
        "icon": None,
        "original_price": 5000,
        "starting_bid": 1800,
        "duration_days": 5,
        "minimum_increment": 100,
    },
    {
        "slug": "casual-sneakers",
        "name": "Casual Sneakers",
        "category": "Fashion",
        "description": "Lightweight, breathable everyday sneakers with a flexible sole.",
        "image": "products/casual-sneakers.svg",
        "icon": None,
        "original_price": 2500,
        "starting_bid": 1200,
        "duration_days": 2,
        "minimum_increment": 100,
    },
    {
        "slug": "wireless-earbuds",
        "name": "Wireless Earbuds",
        "category": "Audio",
        "description": "Compact earbuds with touch controls and a charging case.",
        "image": "products/wireless-earbuds.svg",
        "icon": None,
        "original_price": 2500,
        "starting_bid": 1000,
        "duration_days": 4,
        "minimum_increment": 100,
    },
    {
        "slug": "ideapad-slim-3-laptop",
        "name": "IdeaPad Slim 3 Laptop",
        "category": "Computers",
        "description": "A versatile laptop for study, work, and everyday tasks.",
        "image": None,
        "icon": "💻",
        "original_price": 72000,
        "starting_bid": 45000,
        "duration_days": 6,
        "minimum_increment": 500,
    },
)
PRODUCT_CATALOG = (
    {
        "slug": "iphone-14-pro-max-256gb",
        "name": "iPhone 14 Pro Max (256GB)",
        "category": "Smartphones",
        "description": "Powerful. Premium. Perfect.",
        "image": "products/iphone-14-pro.png",
        "icon": None,
        "rating": "4.8",
        "reviews": "1.2k",
        "price": 92500,
        "old_price": 125000,
        "features": ("A16 Bionic chip", "48MP Pro camera", "All-day battery"),
    },
    {
        "slug": "smart-watch-bluetooth-calling",
        "name": "Smart Watch (Bluetooth Calling)",
        "category": "Wearables",
        "description": "Stay connected, stay fit.",
        "image": "products/smart-watch.png",
        "icon": None,
        "rating": "4.6",
        "reviews": "850",
        "price": 2999,
        "old_price": 4000,
        "features": ("Bluetooth calling", "Heart rate monitor", "IP68 waterproof"),
    },
    {
        "slug": "jbl-wireless-headphones",
        "name": "JBL Wireless Headphones",
        "category": "Audio",
        "description": "Feel the bass, feel the music.",
        "image": "products/jbl-headphones.png",
        "icon": None,
        "rating": "4.7",
        "reviews": "2.4k",
        "price": 2999,
        "old_price": 5000,
        "features": ("Pure bass sound", "Up to 40 hours playtime", "Bluetooth 5.3"),
    },
    {
        "slug": "casual-sneakers",
        "name": "Casual Sneakers",
        "category": "Fashion",
        "description": "Everyday comfort, fresh style.",
        "image": "products/casual-sneakers.svg",
        "icon": None,
        "rating": "4.5",
        "reviews": "420",
        "price": 2000,
        "old_price": 2500,
        "features": ("Lightweight design", "Breathable fabric", "Flexible sole"),
    },
    {
        "slug": "wireless-earbuds",
        "name": "Wireless Earbuds",
        "category": "Audio",
        "description": "Clear sound, all day long.",
        "image": "products/wireless-earbuds.svg",
        "icon": None,
        "rating": "4.6",
        "reviews": "680",
        "price": 1850,
        "old_price": 2500,
        "features": ("Noise reduction", "Touch controls", "Charging case included"),
    },
    {
        "slug": "compact-digital-camera",
        "name": "Compact Digital Camera",
        "category": "Photography",
        "description": "Capture every moment in detail.",
        "image": "products/digital-camera.svg",
        "icon": None,
        "rating": "4.8",
        "reviews": "315",
        "price": 18500,
        "old_price": 22000,
        "features": ("4K video recording", "Optical image focus", "Rechargeable battery"),
    },
    {
        "slug": "ideapad-slim-3-laptop",
        "name": "IdeaPad Slim 3 Laptop",
        "category": "Computers",
        "description": "A reliable laptop for work, study, and everyday use.",
        "image": None,
        "icon": "💻",
        "rating": "4.7",
        "reviews": "96",
        "price": 72000,
        "old_price": None,
        "features": ("Slim everyday design", "Built for work and study", "Reliable performance"),
    },
    {
        "slug": "wireless-keyboard-mouse",
        "name": "Wireless Keyboard and Mouse",
        "category": "Accessories",
        "description": "A comfortable wireless set for your desk.",
        "image": None,
        "icon": "⌨",
        "rating": "4.5",
        "reviews": "73",
        "price": 3200,
        "old_price": None,
        "features": ("Wireless connection", "Comfortable keyboard", "Matching mouse included"),
    },
    {
        "slug": "ceramic-table-lamp",
        "name": "Ceramic Table Lamp",
        "category": "Home",
        "description": "A warm, simple accent for your home.",
        "image": None,
        "icon": "💡",
        "rating": "4.4",
        "reviews": "51",
        "price": 2450,
        "old_price": None,
        "features": ("Ceramic base", "Warm ambient lighting", "Simple home accent"),
    },
)
INITIAL_PRODUCT_STOCK = 10
DELIVERY_FEES = {
    "Dhaka": 60,
    "Chattogram": 120,
    "Rajshahi": 120,
    "Khulna": 120,
    "Barishal": 120,
    "Sylhet": 120,
    "Rangpur": 120,
    "Mymensingh": 120,
}
CHECKOUT_COUPONS = {"SAVE50": {"minimum": 500, "discount": 50}}
load_dotenv(ROOT / ".env")


def get_secret_key():
    configured_secret = os.getenv("FLASK_SECRET_KEY")
    if configured_secret:
        return configured_secret

    INSTANCE.mkdir(exist_ok=True)
    if DEVELOPMENT_SECRET_FILE.exists():
        return DEVELOPMENT_SECRET_FILE.read_text(encoding="utf-8").strip()

    development_secret = secrets.token_urlsafe(48)
    DEVELOPMENT_SECRET_FILE.write_text(development_secret, encoding="utf-8")
    logging.warning("FLASK_SECRET_KEY is unset; using a persistent local development key.")
    return development_secret


app = Flask(__name__, template_folder=str(ROOT))
app.secret_key = get_secret_key()
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.getenv("COOKIE_SECURE", "false").lower() == "true",
)
logging.basicConfig(level=logging.INFO)


@contextmanager
def database():
    INSTANCE.mkdir(exist_ok=True)
    connection = sqlite3.connect(DATABASE)
    connection.row_factory = sqlite3.Row
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def initialize_database():
    with database() as connection:
        connection.execute(
            """CREATE TABLE IF NOT EXISTS accounts (
                id INTEGER PRIMARY KEY,
                full_name TEXT NOT NULL,
                email TEXT NOT NULL UNIQUE,
                phone TEXT NOT NULL,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL CHECK (role IN ('user', 'admin', 'superadmin')),
                is_verified INTEGER NOT NULL DEFAULT 0,
                verification_token_hash TEXT,
                verification_expires_at INTEGER,
                password_reset_token_hash TEXT,
                password_reset_expires_at INTEGER,
                created_at INTEGER NOT NULL
            )"""
        )
        table = connection.execute(
            "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'accounts'"
        ).fetchone()
        if table and "CHECK (role = 'user')" in table["sql"]:
            connection.execute(
                """CREATE TABLE accounts_new (
                    id INTEGER PRIMARY KEY,
                    full_name TEXT NOT NULL,
                    email TEXT NOT NULL UNIQUE,
                    phone TEXT NOT NULL,
                    password_hash TEXT NOT NULL,
                    role TEXT NOT NULL CHECK (role IN ('user', 'admin', 'superadmin')),
                    is_verified INTEGER NOT NULL DEFAULT 0,
                    verification_token_hash TEXT,
                    verification_expires_at INTEGER,
                    password_reset_token_hash TEXT,
                    password_reset_expires_at INTEGER,
                    created_at INTEGER NOT NULL
                )"""
            )
            connection.execute(
                "INSERT INTO accounts_new SELECT id, full_name, email, phone, password_hash, role, "
                "is_verified, verification_token_hash, verification_expires_at, "
                "password_reset_token_hash, password_reset_expires_at, created_at FROM accounts"
            )
            connection.execute("DROP TABLE accounts")
            connection.execute("ALTER TABLE accounts_new RENAME TO accounts")

        columns = {
            row["name"] for row in connection.execute("PRAGMA table_info(accounts)")
        }
        if "password_reset_token_hash" not in columns:
            connection.execute("ALTER TABLE accounts ADD COLUMN password_reset_token_hash TEXT")
        if "password_reset_expires_at" not in columns:
            connection.execute("ALTER TABLE accounts ADD COLUMN password_reset_expires_at INTEGER")
        connection.execute(
            """CREATE TABLE IF NOT EXISTS auctions (
                id INTEGER PRIMARY KEY,
                slug TEXT NOT NULL UNIQUE,
                current_bid INTEGER NOT NULL CHECK (current_bid >= 0),
                ends_at INTEGER NOT NULL
            )"""
        )
        connection.execute(
            """CREATE TABLE IF NOT EXISTS auction_bids (
                id INTEGER PRIMARY KEY,
                auction_id INTEGER NOT NULL REFERENCES auctions(id),
                account_id INTEGER NOT NULL REFERENCES accounts(id),
                amount INTEGER NOT NULL CHECK (amount > 0),
                created_at INTEGER NOT NULL
            )"""
        )
        connection.execute(
            """CREATE TABLE IF NOT EXISTS product_inventory (
                product_slug TEXT PRIMARY KEY,
                stock INTEGER NOT NULL CHECK (stock >= 0)
            )"""
        )
        connection.execute(
            """CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY,
                order_number TEXT NOT NULL UNIQUE,
                checkout_key TEXT NOT NULL UNIQUE,
                tracking_token_hash TEXT NOT NULL UNIQUE,
                account_id INTEGER REFERENCES accounts(id),
                customer_name TEXT NOT NULL,
                customer_email TEXT,
                customer_phone TEXT NOT NULL,
                division TEXT NOT NULL,
                district TEXT NOT NULL,
                address TEXT NOT NULL,
                postal_code TEXT,
                delivery_note TEXT,
                subtotal INTEGER NOT NULL CHECK (subtotal >= 0),
                delivery_fee INTEGER NOT NULL CHECK (delivery_fee >= 0),
                discount INTEGER NOT NULL CHECK (discount >= 0),
                total INTEGER NOT NULL CHECK (total >= 0),
                coupon_code TEXT,
                payment_method TEXT NOT NULL CHECK (
                    payment_method IN ('cod', 'bkash', 'nagad', 'card')
                ),
                order_status TEXT NOT NULL CHECK (
                    order_status IN ('pending', 'confirmed', 'processing', 'shipped', 'delivered')
                ),
                payment_status TEXT NOT NULL CHECK (
                    payment_status IN ('unpaid', 'paid', 'failed', 'refunded')
                ),
                created_at INTEGER NOT NULL
            )"""
        )
        connection.execute(
            """CREATE TABLE IF NOT EXISTS order_items (
                id INTEGER PRIMARY KEY,
                order_id INTEGER NOT NULL REFERENCES orders(id),
                product_slug TEXT NOT NULL,
                product_name TEXT NOT NULL,
                quantity INTEGER NOT NULL CHECK (quantity > 0),
                unit_price INTEGER NOT NULL CHECK (unit_price >= 0),
                variant_id TEXT
            )"""
        )
        now = int(time.time())
        for product in PRODUCT_CATALOG:
            connection.execute(
                "INSERT OR IGNORE INTO product_inventory (product_slug, stock) VALUES (?, ?)",
                (product["slug"], INITIAL_PRODUCT_STOCK),
            )
        for listing in AUCTION_LISTINGS:
            connection.execute(
                "INSERT OR IGNORE INTO auctions (slug, current_bid, ends_at) VALUES (?, ?, ?)",
                (
                    listing["slug"],
                    listing["starting_bid"],
                    now + listing["duration_days"] * 24 * 60 * 60,
                ),
            )


initialize_database()


@app.context_processor
def csrf_context():
    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_urlsafe(32)
    return {"csrf_token": session["csrf_token"]}


@app.template_filter("datetime")
def format_datetime(timestamp):
    return datetime.fromtimestamp(timestamp, timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


@app.before_request
def protect_post_requests():
    if request.method == "POST":
        submitted_token = request.form.get("csrf_token", "")
        session_token = session.get("csrf_token", "")
        if not submitted_token or not secrets.compare_digest(submitted_token, session_token):
            flash("Your form session expired. Please try submitting the form again.", "error")
            destinations = {
                "register": "registration_page",
                "resend_verification": "registration_page",
                "login": "login_page",
                "request_password_reset": "forgot_password_page",
                "reset_password": "forgot_password_page",
                "logout": "home",
                "place_bid": "auction_details",
                "start_checkout": "products_page",
                "apply_checkout_coupon": "checkout_page",
                "checkout_page": "checkout_page",
            }
            return redirect(url_for(destinations.get(request.endpoint, "home")))


def hash_token(token):
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def send_verification_email(email, token):
    base_url = os.getenv("APP_BASE_URL", "http://127.0.0.1:5000/")
    verification_url = urljoin(base_url.rstrip("/") + "/", f"verify/{token}")
    send_email(
        email,
        "Verify your BidMart email",
        "Welcome to BidMart. Verify your email within 30 minutes using this link:\n\n"
        f"{verification_url}\n\nIf you did not create this account, ignore this email.",
    )


def send_password_reset_email(email, token):
    base_url = os.getenv("APP_BASE_URL", "http://127.0.0.1:5000/")
    reset_url = urljoin(base_url.rstrip("/") + "/", f"reset-password/{token}")
    send_email(
        email,
        "Reset your BidMart password",
        "Use this link to reset your BidMart password within 30 minutes:\n\n"
        f"{reset_url}\n\nIf you did not request a password reset, ignore this email.",
    )


def send_email(email, subject, content):
    host = os.getenv("SMTP_HOST", "smtp.gmail.com")
    port = int(os.getenv("SMTP_PORT", "587"))
    username = os.getenv("SMTP_USERNAME", "")
    password = os.getenv("SMTP_PASSWORD", "")
    sender = os.getenv("SMTP_FROM", username)
    if not all((username, password, sender)):
        raise RuntimeError("SMTP_USERNAME, SMTP_PASSWORD, and SMTP_FROM must be configured in .env.")

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = sender
    message["To"] = email
    message.set_content(content)

    if port == 465:
        with smtplib.SMTP_SSL(host, port, timeout=20) as smtp:
            smtp.login(username, password)
            smtp.send_message(message)
    else:
        with smtplib.SMTP(host, port, timeout=20) as smtp:
            smtp.ehlo()
            smtp.starttls()
            smtp.ehlo()
            smtp.login(username, password)
            smtp.send_message(message)


def issue_verification(email):
    token = secrets.token_urlsafe(32)
    with database() as connection:
        connection.execute(
            "UPDATE accounts SET verification_token_hash = ?, verification_expires_at = ? "
            "WHERE email = ? AND is_verified = 0",
            (hash_token(token), int(time.time()) + 1800, email),
        )
    send_verification_email(email, token)


def issue_password_reset(email):
    token = secrets.token_urlsafe(32)
    token_hash = hash_token(token)
    with database() as connection:
        connection.execute(
            "UPDATE accounts SET password_reset_token_hash = ?, password_reset_expires_at = ? "
            "WHERE email = ?",
            (token_hash, int(time.time()) + 1800, email),
        )
    try:
        send_password_reset_email(email, token)
    except Exception:
        with database() as connection:
            connection.execute(
                "UPDATE accounts SET password_reset_token_hash = NULL, password_reset_expires_at = NULL "
                "WHERE email = ? AND password_reset_token_hash = ?",
                (email, token_hash),
            )
        raise


@app.get("/")
@app.get("/index.html")
def home():
    current_user_name = None
    if session.get("user_id"):
        with database() as connection:
            account = connection.execute(
                "SELECT full_name FROM accounts WHERE id = ?",
                (session["user_id"],),
            ).fetchone()
        if account:
            current_user_name = account["full_name"]
    with database() as connection:
        product_inventory = {
            row["product_slug"]: row["stock"]
            for row in connection.execute("SELECT product_slug, stock FROM product_inventory")
        }
    auction, _ = get_auction(DEMO_AUCTION_SLUG)
    return render_template(
        "index.html",
        current_user_email=session.get("user_email"),
        current_user_name=current_user_name,
        active_page="home",
        featured_auction=auction,
        product_inventory=product_inventory,
        now=int(time.time()),
    )


@app.get("/products")
def products_page():
    with database() as connection:
        inventory = {
            row["product_slug"]: row["stock"]
            for row in connection.execute("SELECT product_slug, stock FROM product_inventory")
        }
    return render_template(
        "products.html",
        products=[{**product, "stock": inventory.get(product["slug"], 0)} for product in PRODUCT_CATALOG],
        current_user_email=session.get("user_email"),
        current_user_name=session.get("user_name"),
        active_page="products",
    )


@app.get("/products/<slug>")
def product_details_page(slug):
    product = next((item for item in PRODUCT_CATALOG if item["slug"] == slug), None)
    if not product:
        abort(404)
    with database() as connection:
        inventory = connection.execute(
            "SELECT stock FROM product_inventory WHERE product_slug = ?", (slug,)
        ).fetchone()
    related_products = [
        item for item in PRODUCT_CATALOG
        if item["slug"] != slug
    ][:4]
    return render_template(
        "product_detail.html",
        product=product,
        stock=inventory["stock"] if inventory else 0,
        related_products=related_products,
        current_user_email=session.get("user_email"),
        current_user_name=session.get("user_name"),
        active_page="products",
    )


def _checkout_product():
    draft = session.get("checkout_draft")
    if not isinstance(draft, dict):
        return None
    slug = draft.get("product_slug")
    return next((item for item in PRODUCT_CATALOG if item["slug"] == slug), None)


def _parse_quantity(raw_quantity):
    try:
        quantity = int(raw_quantity)
    except (TypeError, ValueError):
        return None
    return quantity if 1 <= quantity <= 99 else None


def _checkout_stock(slug):
    with database() as connection:
        row = connection.execute(
            "SELECT stock FROM product_inventory WHERE product_slug = ?", (slug,)
        ).fetchone()
    return row["stock"] if row else 0


def _checkout_totals(product, quantity, division, coupon_code=""):
    subtotal = product["price"] * quantity
    delivery_fee = DELIVERY_FEES.get(division, DELIVERY_FEES["Dhaka"])
    coupon = CHECKOUT_COUPONS.get(coupon_code.strip().upper())
    discount = 0
    if coupon and subtotal >= coupon["minimum"]:
        discount = min(coupon["discount"], subtotal)
    return {
        "subtotal": subtotal,
        "delivery_fee": delivery_fee,
        "discount": discount,
        "total": subtotal + delivery_fee - discount,
    }


def _checkout_context(form_data=None, errors=None):
    draft = session.get("checkout_draft", {})
    product = _checkout_product()
    if not product:
        return None
    quantity = _parse_quantity(draft.get("quantity")) or 1
    stock = _checkout_stock(product["slug"])
    form_data = form_data or {}
    profile = {}
    if session.get("user_id"):
        with database() as connection:
            account = connection.execute(
                "SELECT full_name, email, phone FROM accounts WHERE id = ?",
                (session["user_id"],),
            ).fetchone()
        if account:
            profile = dict(account)
    values = {
        "customer_name": form_data.get("customer_name", profile.get("full_name", "")),
        "customer_email": form_data.get("customer_email", profile.get("email", "")),
        "customer_phone": form_data.get("customer_phone", profile.get("phone", "")),
        "division": form_data.get("division", "Dhaka"),
        "district": form_data.get("district", ""),
        "address": form_data.get("address", ""),
        "postal_code": form_data.get("postal_code", ""),
        "delivery_note": form_data.get("delivery_note", ""),
        "coupon_code": form_data.get("coupon_code", ""),
        "payment_method": form_data.get("payment_method", "cod"),
        "quantity": form_data.get("quantity", quantity),
    }
    parsed_quantity = _parse_quantity(values["quantity"]) or quantity
    totals = _checkout_totals(product, parsed_quantity, values["division"], values["coupon_code"])
    return {
        "product": product,
        "stock": stock,
        "values": values,
        "totals": totals,
        "errors": errors or {},
        "delivery_fees": DELIVERY_FEES,
        "current_user_name": session.get("user_name"),
        "current_user_email": session.get("user_email"),
        "active_page": "products",
    }


@app.post("/checkout/start")
def start_checkout():
    slug = request.form.get("product_slug", "")
    product = next((item for item in PRODUCT_CATALOG if item["slug"] == slug), None)
    if not product:
        abort(404)
    quantity = _parse_quantity(request.form.get("quantity"))
    if quantity is None:
        flash("Choose a quantity between 1 and 99.", "error")
        return redirect(url_for("product_details_page", slug=slug))
    stock = _checkout_stock(slug)
    if quantity > stock:
        flash(f"Only {stock} item(s) are currently available.", "error")
        return redirect(url_for("product_details_page", slug=slug))
    session["checkout_draft"] = {
        "product_slug": slug,
        "quantity": quantity,
        "checkout_key": secrets.token_urlsafe(24),
    }
    return redirect(url_for("checkout_page"))


@app.get("/checkout")
def checkout_page():
    draft = session.get("checkout_draft", {})
    if draft.get("order_number") and draft.get("tracking_token"):
        return redirect(url_for(
            "order_confirmation",
            order_number=draft["order_number"],
            token=draft["tracking_token"],
        ))
    context = _checkout_context()
    if not context:
        flash("Choose a product before starting checkout.", "error")
        return redirect(url_for("products_page"))
    return render_template("checkout.html", **context)


@app.post("/checkout/apply-coupon")
def apply_checkout_coupon():
    product = _checkout_product()
    if not product:
        return jsonify(error="Your checkout session expired. Choose the product again."), 400
    quantity = _parse_quantity(request.form.get("quantity"))
    if quantity is None:
        return jsonify(error="Choose a valid product quantity."), 400
    if quantity > _checkout_stock(product["slug"]):
        return jsonify(error="That quantity is not currently in stock."), 400
    coupon_code = request.form.get("coupon_code", "").strip().upper()
    coupon = CHECKOUT_COUPONS.get(coupon_code)
    if not coupon:
        return jsonify(error="That coupon code is not valid."), 400
    subtotal = product["price"] * quantity
    if subtotal < coupon["minimum"]:
        return jsonify(error=f"This coupon requires a subtotal of at least ৳ {coupon['minimum']:,}."), 400
    totals = _checkout_totals(product, quantity, request.form.get("division", "Dhaka"), coupon_code)
    return jsonify(**totals, message=f"Coupon {coupon_code} applied.")


@app.post("/checkout")
def place_checkout_order():
    draft = session.get("checkout_draft")
    product = _checkout_product()
    if not draft or not product:
        flash("Your checkout session expired. Choose the product again.", "error")
        return redirect(url_for("products_page"))
    if draft.get("order_number") and draft.get("tracking_token"):
        return redirect(url_for(
            "order_confirmation",
            order_number=draft["order_number"],
            token=draft["tracking_token"],
        ))

    form_data = request.form
    errors = {}
    name = form_data.get("customer_name", "").strip()
    email = form_data.get("customer_email", "").strip()
    phone = re.sub(r"[\s()-]", "", form_data.get("customer_phone", ""))
    division = form_data.get("division", "").strip()
    district = form_data.get("district", "").strip()
    address = form_data.get("address", "").strip()
    postal_code = form_data.get("postal_code", "").strip()
    delivery_note = form_data.get("delivery_note", "").strip()
    coupon_code = form_data.get("coupon_code", "").strip().upper()
    payment_method = form_data.get("payment_method", "")
    quantity = _parse_quantity(form_data.get("quantity"))

    if len(name) < 2 or len(name) > 100 or not re.search(r"[^\W\d_]", name, re.UNICODE):
        errors["customer_name"] = "Enter your full name (2–100 characters)."
    if email and (
        len(email) > 254
        or not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email)
    ):
        errors["customer_email"] = "Enter a valid email address, or leave it blank."
    if not re.fullmatch(r"(?:01[3-9]\d{8}|\+?8801[3-9]\d{8})", phone):
        errors["customer_phone"] = "Enter a valid Bangladesh mobile number, e.g. 01XXXXXXXXX."
    if division not in DELIVERY_FEES:
        errors["division"] = "Choose a valid delivery division."
    if not district or len(district) > 100:
        errors["district"] = "Enter your area or district (up to 100 characters)."
    if not address or len(address) > 500:
        errors["address"] = "Enter your full delivery address (up to 500 characters)."
    if postal_code and not re.fullmatch(r"\d{4}", postal_code):
        errors["postal_code"] = "Enter a 4-digit Bangladesh postal code, or leave it blank."
    if len(delivery_note) > 500:
        errors["delivery_note"] = "Keep your delivery note under 500 characters."
    if quantity is None:
        errors["quantity"] = "Choose a quantity between 1 and 99."
    if payment_method not in ("cod", "bkash", "nagad", "card"):
        errors["payment_method"] = "Choose a supported payment method."
    if coupon_code and coupon_code not in CHECKOUT_COUPONS:
        errors["coupon_code"] = "That coupon code is not valid."
    elif coupon_code and quantity is not None:
        if product["price"] * quantity < CHECKOUT_COUPONS[coupon_code]["minimum"]:
            errors["coupon_code"] = "This coupon requires a subtotal of at least ৳ 500."

    stock = _checkout_stock(product["slug"])
    if quantity is not None and quantity > stock:
        errors["quantity"] = f"Only {stock} item(s) are currently available."
    if errors:
        context = _checkout_context(form_data, errors)
        return render_template("checkout.html", **context), 400

    totals = _checkout_totals(product, quantity, division, coupon_code)
    checkout_key = draft.get("checkout_key")
    if not checkout_key:
        flash("Your checkout session expired. Choose the product again.", "error")
        return redirect(url_for("products_page"))

    payment_status = "unpaid"
    order_status = "confirmed" if payment_method == "cod" else "pending"
    order_number = f"BM-{secrets.token_hex(5).upper()}"
    tracking_token = secrets.token_urlsafe(32)
    account_id = session.get("user_id")
    now = int(time.time())
    with database() as connection:
        existing = connection.execute(
            "SELECT order_number FROM orders WHERE checkout_key = ?", (checkout_key,)
        ).fetchone()
        if existing:
            if draft.get("tracking_token"):
                return redirect(url_for(
                    "order_confirmation",
                    order_number=existing["order_number"],
                    token=draft["tracking_token"],
                ))
            flash("This checkout was already submitted.", "error")
            return redirect(url_for("products_page"))
        if payment_method == "cod":
            reserved = connection.execute(
                "UPDATE product_inventory SET stock = stock - ? "
                "WHERE product_slug = ? AND stock >= ?",
                (quantity, product["slug"], quantity),
            )
            if reserved.rowcount != 1:
                context = _checkout_context(
                    form_data,
                    {"quantity": "Stock changed while you were checking out. Review the available quantity."},
                )
                return render_template("checkout.html", **context), 409
        connection.execute(
            """INSERT INTO orders (
                order_number, checkout_key, tracking_token_hash, account_id,
                customer_name, customer_email, customer_phone, division, district,
                address, postal_code, delivery_note, subtotal, delivery_fee, discount,
                total, coupon_code, payment_method, order_status, payment_status, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                order_number, checkout_key, hashlib.sha256(tracking_token.encode()).hexdigest(),
                account_id, name, email or None, phone, division, district, address,
                postal_code or None, delivery_note or None, totals["subtotal"],
                totals["delivery_fee"], totals["discount"], totals["total"],
                coupon_code or None, payment_method, order_status, payment_status, now,
            ),
        )
        order_id = connection.execute("SELECT last_insert_rowid()").fetchone()[0]
        connection.execute(
            """INSERT INTO order_items
            (order_id, product_slug, product_name, quantity, unit_price, variant_id)
            VALUES (?, ?, ?, ?, ?, NULL)""",
            (order_id, product["slug"], product["name"], quantity, product["price"]),
        )

    draft["order_number"] = order_number
    draft["tracking_token"] = tracking_token
    session["checkout_draft"] = draft
    return redirect(url_for("order_confirmation", order_number=order_number, token=tracking_token))


def _render_order_page(order_number, token, tracking=False):
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    with database() as connection:
        order = connection.execute(
            "SELECT * FROM orders WHERE order_number = ? AND tracking_token_hash = ?",
            (order_number, token_hash),
        ).fetchone()
        if not order:
            abort(404)
        items = connection.execute(
            "SELECT product_slug, product_name, quantity, unit_price FROM order_items WHERE order_id = ?",
            (order["id"],),
        ).fetchall()
    return render_template(
        "order_confirmation.html",
        order=order,
        items=items,
        tracking=tracking,
        track_url=url_for("track_order", order_number=order_number, token=token),
        current_user_name=session.get("user_name"),
        current_user_email=session.get("user_email"),
        active_page="products",
    )


@app.get("/orders/<order_number>/confirmation/<token>")
def order_confirmation(order_number, token):
    return _render_order_page(order_number, token)


@app.get("/orders/<order_number>/track/<token>")
def track_order(order_number, token):
    return _render_order_page(order_number, token, tracking=True)


@app.get("/auctions")
def auctions_page():
    now = int(time.time())
    with database() as connection:
        auctions = connection.execute(
            "SELECT slug, current_bid, ends_at FROM auctions ORDER BY ends_at"
        ).fetchall()
    auction_by_slug = {auction["slug"]: auction for auction in auctions}
    listings = []
    for listing in AUCTION_LISTINGS:
        auction = auction_by_slug.get(listing["slug"])
        if auction:
            listings.append({
                **listing,
                "current_bid": auction["current_bid"],
                "ends_at": auction["ends_at"],
                "is_ended": auction["ends_at"] <= now,
            })
    return render_template(
        "auctions.html",
        auctions=listings,
        now=now,
        current_user_email=session.get("user_email"),
        current_user_name=session.get("user_name"),
        active_page="auctions",
    )


def get_auction(slug):
    listing = next((item for item in AUCTION_LISTINGS if item["slug"] == slug), None)
    if not listing:
        abort(404)
    with database() as connection:
        auction = connection.execute(
            "SELECT id, current_bid, ends_at FROM auctions WHERE slug = ?",
            (slug,),
        ).fetchone()
        if not auction:
            abort(404)
        recent_bids = connection.execute(
            "SELECT auction_bids.amount, auction_bids.created_at, accounts.full_name "
            "FROM auction_bids JOIN accounts ON accounts.id = auction_bids.account_id "
            "WHERE auction_bids.auction_id = ? ORDER BY auction_bids.created_at DESC, "
            "auction_bids.id DESC LIMIT 10",
            (auction["id"],),
        ).fetchall()
    return {**listing, **dict(auction)}, recent_bids


@app.get("/auction/<slug>")
@app.get("/auction/" + DEMO_AUCTION_SLUG, defaults={"slug": DEMO_AUCTION_SLUG})
def auction_details(slug):
    auction, recent_bids = get_auction(slug)
    bidder_history = []
    for bid in recent_bids:
        name_parts = bid["full_name"].split()
        bidder_label = " ".join(f"{part[0]}***" for part in name_parts if part)
        bidder_history.append({
            "amount": bid["amount"],
            "created_at": bid["created_at"],
            "bidder_label": bidder_label or "Bidder",
        })
    return render_template(
        "auction_detail.html",
        auction=auction,
        recent_bids=bidder_history,
        auction_url=url_for("auction_details", slug=slug),
        current_user_name=session.get("user_name"),
        current_user_email=session.get("user_email"),
        active_page="auctions",
        minimum_bid=auction["current_bid"] + auction["minimum_increment"],
        minimum_increment=auction["minimum_increment"],
        now=int(time.time()),
    )


@app.post("/auction/<slug>/bid")
@app.post("/auction/" + DEMO_AUCTION_SLUG + "/bid", defaults={"slug": DEMO_AUCTION_SLUG})
def place_bid(slug):
    listing = next((item for item in AUCTION_LISTINGS if item["slug"] == slug), None)
    if not listing:
        abort(404)
    auction_url = url_for("auction_details", slug=slug)
    if not session.get("user_id"):
        flash("Log in to your verified account before placing a bid.", "error")
        return redirect(url_for("login_page", next=auction_url))

    raw_amount = request.form.get("bid_amount", "").replace(",", "").strip()
    try:
        amount = int(raw_amount)
    except ValueError:
        flash("Enter a whole-number bid amount.", "error")
        return redirect(auction_url)

    now = int(time.time())
    with database() as connection:
        auction = connection.execute(
            "SELECT id, current_bid, ends_at FROM auctions WHERE slug = ?",
            (slug,),
        ).fetchone()
        if not auction:
            abort(404)
        if auction["ends_at"] <= now:
            flash("This auction has ended and is no longer accepting bids.", "error")
            return redirect(auction_url)
        minimum_bid = auction["current_bid"] + listing["minimum_increment"]
        if amount < minimum_bid:
            flash(f"Your bid must be at least ৳ {minimum_bid:,}.", "error")
            return redirect(auction_url)

        updated = connection.execute(
            "UPDATE auctions SET current_bid = ? WHERE id = ? AND current_bid = ? AND ends_at > ?",
            (amount, auction["id"], auction["current_bid"], now),
        )
        if updated.rowcount != 1:
            flash("Another bid was placed first. Review the new current bid and try again.", "error")
            return redirect(auction_url)
        connection.execute(
            "INSERT INTO auction_bids (auction_id, account_id, amount, created_at) VALUES (?, ?, ?, ?)",
            (auction["id"], session["user_id"], amount, now),
        )

    flash(f"Your bid of ৳ {amount:,} was placed successfully.", "success")
    return redirect(auction_url)


@app.get("/style.css")
def stylesheet():
    return send_from_directory(ROOT, "style.css", mimetype="text/css")


@app.get("/register.html")
def registration_page():
    return render_template("register.html")


@app.post("/register")
def register():
    full_name = request.form.get("full_name", "").strip()
    email = request.form.get("email", "").strip().casefold()
    phone = request.form.get("phone", "").strip()
    role = request.form.get("role", "user")
    password = request.form.get("password", "")
    confirm_password = request.form.get("confirm_password", "")

    if role != "user":
        flash("Admin and Superadmin accounts must be provisioned by an authorized owner.", "error")
        return redirect(url_for("registration_page"))
    if not full_name or "@" not in email or len(password) < 8:
        flash("Enter a valid name and email, and a password of at least 8 characters.", "error")
        return redirect(url_for("registration_page"))
    if password != confirm_password:
        flash("Passwords do not match.", "error")
        return redirect(url_for("registration_page"))

    try:
        with database() as connection:
            connection.execute(
                "INSERT INTO accounts (full_name, email, phone, password_hash, role, created_at) "
                "VALUES (?, ?, ?, ?, 'user', ?)",
                (full_name, email, phone, generate_password_hash(password), int(time.time())),
            )
        issue_verification(email)
    except sqlite3.IntegrityError:
        flash(
            "An account with this email already exists. If it is unverified, use the resend form below; otherwise log in.",
            "error",
        )
        return redirect(url_for("registration_page"))
    except Exception:
        logging.exception("Registration email could not be sent")
        flash(
            "Account created, but the verification email could not be sent. "
            "Configure SMTP in .env, restart BidMart, then use the resend form below.",
            "error",
        )
        return redirect(url_for("registration_page"))

    flash("Account created. Check your inbox for the verification link; it expires in 30 minutes.", "success")
    return redirect(url_for("login_page"))


@app.post("/resend-verification")
def resend_verification():
    email = request.form.get("email", "").strip().casefold()
    smtp_settings = ("SMTP_USERNAME", "SMTP_PASSWORD", "SMTP_FROM")
    if not all(os.getenv(setting) for setting in smtp_settings):
        flash("Verification email is unavailable. Configure SMTP in .env, restart BidMart, then try again.", "error")
        return redirect(url_for("registration_page"))

    with database() as connection:
        account = connection.execute(
            "SELECT is_verified FROM accounts WHERE email = ?", (email,)
        ).fetchone()
    if account and not account["is_verified"]:
        try:
            issue_verification(email)
        except Exception:
            logging.exception("Verification email resend failed")
    flash(
        "If that address has an unverified BidMart account, check your inbox and spam folder for a new link. "
        "If it does not arrive, check the SMTP settings and the app's server log.",
        "success",
    )
    return redirect(url_for("registration_page"))


@app.get("/verify/<token>")
def verify_email(token):
    token_hash = hash_token(token)
    with database() as connection:
        result = connection.execute(
            "UPDATE accounts SET is_verified = 1, verification_token_hash = NULL, "
            "verification_expires_at = NULL WHERE verification_token_hash = ? "
            "AND verification_expires_at > ? AND is_verified = 0",
            (token_hash, int(time.time())),
        )
    if result.rowcount == 1:
        flash("Email verified. You can now log in.", "success")
    else:
        flash("That verification link is invalid, expired, or already used.", "error")
    return redirect(url_for("login_page"))


@app.get("/login.html")
def login_page():
    next_url = request.args.get("next", "")
    if next_url not in (url_for("auction_details"), url_for("checkout_page")):
        next_url = ""
    return render_template("login.html", next_url=next_url)


@app.get("/forgot-password")
def forgot_password_page():
    return render_template("forgot_password.html")


@app.post("/forgot-password")
def request_password_reset():
    email = request.form.get("email", "").strip().casefold()
    try:
        with database() as connection:
            account = connection.execute(
                "SELECT id FROM accounts WHERE email = ?", (email,)
            ).fetchone()
        if account:
            issue_password_reset(email)
    except Exception:
        logging.exception("Password reset email could not be sent")
    flash(
        "If an account exists for that email, a password reset link will be sent. "
        "Check your inbox and spam folder.",
        "success",
    )
    return redirect(url_for("forgot_password_page"))


@app.get("/reset-password/<token>")
def reset_password_page(token):
    with database() as connection:
        account = connection.execute(
            "SELECT id FROM accounts WHERE password_reset_token_hash = ? "
            "AND password_reset_expires_at > ?",
            (hash_token(token), int(time.time())),
        ).fetchone()
    if not account:
        flash("That password reset link is invalid, expired, or already used.", "error")
        return redirect(url_for("forgot_password_page"))
    return render_template("reset_password.html", token=token)


@app.post("/reset-password/<token>")
def reset_password(token):
    password = request.form.get("password", "")
    confirm_password = request.form.get("confirm_password", "")
    if len(password) < 8:
        flash("Choose a password of at least 8 characters.", "error")
        return redirect(url_for("reset_password_page", token=token))
    if password != confirm_password:
        flash("Passwords do not match.", "error")
        return redirect(url_for("reset_password_page", token=token))

    with database() as connection:
        result = connection.execute(
            "UPDATE accounts SET password_hash = ?, password_reset_token_hash = NULL, "
            "password_reset_expires_at = NULL WHERE password_reset_token_hash = ? "
            "AND password_reset_expires_at > ?",
            (generate_password_hash(password), hash_token(token), int(time.time())),
        )
    if result.rowcount == 1:
        flash("Your password has been reset. You can now log in.", "success")
        return redirect(url_for("login_page"))
    flash("That password reset link is invalid, expired, or already used.", "error")
    return redirect(url_for("forgot_password_page"))


@app.post("/login")
def login():
    email = request.form.get("email", "").strip().casefold()
    password = request.form.get("password", "")
    next_url = request.form.get("next", "")
    if next_url not in (url_for("auction_details"), url_for("checkout_page")):
        next_url = ""
    with database() as connection:
        account = connection.execute(
            "SELECT id, email, full_name, password_hash, is_verified FROM accounts WHERE email = ?",
            (email,),
        ).fetchone()

    if (not account or not account["is_verified"]
            or not check_password_hash(account["password_hash"], password)):
        flash("Login failed. Check your details and verify your email before signing in.", "error")
        return redirect(url_for("login_page", next=next_url) if next_url else url_for("login_page"))

    checkout_draft = session.get("checkout_draft")
    session.clear()
    session["user_id"] = account["id"]
    session["user_email"] = account["email"]
    session["user_name"] = account["full_name"]
    if checkout_draft:
        session["checkout_draft"] = checkout_draft
    flash("You are logged in.", "success")
    return redirect(next_url or url_for("home"))


@app.post("/logout")
def logout():
    session.clear()
    flash("You have logged out.", "success")
    return redirect(url_for("home"))


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=int(os.getenv("PORT", "5000")), debug=False)
