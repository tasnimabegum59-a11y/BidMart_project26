import hashlib
import json
import logging
import os
import re
import secrets
import smtplib
import sqlite3
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from email.message import EmailMessage
from pathlib import Path
from urllib.error import URLError
from urllib.parse import urlencode, urljoin, urlparse
from urllib.request import Request, urlopen

from dotenv import load_dotenv
from flask import Flask, abort, flash, jsonify, redirect, render_template, request, send_from_directory, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename


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
    MAX_CONTENT_LENGTH=8 * 1024 * 1024,
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
        if "is_active" not in columns:
            connection.execute("ALTER TABLE accounts ADD COLUMN is_active INTEGER NOT NULL DEFAULT 1")
        connection.execute(
            """CREATE TABLE IF NOT EXISTS notifications (
                id INTEGER PRIMARY KEY,
                account_id INTEGER NOT NULL REFERENCES accounts(id),
                title TEXT NOT NULL,
                message TEXT NOT NULL,
                target_url TEXT NOT NULL,
                created_at INTEGER NOT NULL,
                read_at INTEGER
            )"""
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS notifications_account_unread "
            "ON notifications(account_id, read_at, created_at DESC)"
        )
        connection.execute(
            """CREATE TABLE IF NOT EXISTS admin_role_requests (
                account_id INTEGER PRIMARY KEY REFERENCES accounts(id),
                requested_role TEXT NOT NULL DEFAULT 'admin'
                    CHECK (requested_role IN ('admin', 'superadmin')),
                status TEXT NOT NULL CHECK (status IN ('pending', 'approved', 'rejected')),
                requested_at INTEGER NOT NULL,
                reviewed_at INTEGER,
                reviewed_by INTEGER REFERENCES accounts(id)
            )"""
        )
        request_columns = {
            row["name"] for row in connection.execute("PRAGMA table_info(admin_role_requests)")
        }
        if "requested_role" not in request_columns:
            connection.execute(
                "ALTER TABLE admin_role_requests ADD COLUMN requested_role TEXT NOT NULL DEFAULT 'admin'"
            )
        connection.execute(
            """CREATE TABLE IF NOT EXISTS auctions (
                id INTEGER PRIMARY KEY,
                slug TEXT NOT NULL UNIQUE,
                current_bid INTEGER NOT NULL CHECK (current_bid >= 0),
                ends_at INTEGER NOT NULL,
                starting_bid INTEGER NOT NULL DEFAULT 0,
                minimum_increment INTEGER NOT NULL DEFAULT 100,
                is_active INTEGER NOT NULL DEFAULT 1
            )"""
        )
        auction_columns = {
            row["name"] for row in connection.execute("PRAGMA table_info(auctions)")
        }
        for column, definition in (
            ("starting_bid", "INTEGER NOT NULL DEFAULT 0"),
            ("minimum_increment", "INTEGER NOT NULL DEFAULT 100"),
            ("is_active", "INTEGER NOT NULL DEFAULT 1"),
        ):
            if column not in auction_columns:
                connection.execute(f"ALTER TABLE auctions ADD COLUMN {column} {definition}")
        connection.execute(
            """CREATE TABLE IF NOT EXISTS catalog_products (
                slug TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                category TEXT NOT NULL,
                description TEXT NOT NULL,
                image TEXT,
                icon TEXT,
                rating TEXT NOT NULL DEFAULT '5.0',
                reviews TEXT NOT NULL DEFAULT '0',
                price INTEGER NOT NULL CHECK (price > 0),
                old_price INTEGER CHECK (old_price IS NULL OR old_price >= price),
                features_json TEXT NOT NULL DEFAULT '[]',
                is_active INTEGER NOT NULL DEFAULT 1,
                show_in_catalog INTEGER NOT NULL DEFAULT 1,
                updated_at INTEGER NOT NULL
            )"""
        )
        product_columns = {
            row["name"] for row in connection.execute("PRAGMA table_info(catalog_products)")
        }
        if "show_in_catalog" not in product_columns:
            connection.execute(
                "ALTER TABLE catalog_products ADD COLUMN show_in_catalog INTEGER NOT NULL DEFAULT 1"
            )
        connection.execute(
            """CREATE TABLE IF NOT EXISTS offers (
            id INTEGER PRIMARY KEY,
            product_slug TEXT NOT NULL UNIQUE REFERENCES catalog_products(slug),
            title TEXT NOT NULL,
            description TEXT NOT NULL,
            ends_at INTEGER NOT NULL,
            is_active INTEGER NOT NULL DEFAULT 1
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
            """CREATE TABLE IF NOT EXISTS cart_items (
                account_id INTEGER NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
                product_slug TEXT NOT NULL,
                quantity INTEGER NOT NULL CHECK (quantity BETWEEN 1 AND 99),
                updated_at INTEGER NOT NULL,
                PRIMARY KEY (account_id, product_slug)
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
                stock_reserved INTEGER NOT NULL DEFAULT 0,
                created_at INTEGER NOT NULL
            )"""
        )
        order_columns = {
            row["name"] for row in connection.execute("PRAGMA table_info(orders)")
        }
        if "stock_reserved" not in order_columns:
            connection.execute("ALTER TABLE orders ADD COLUMN stock_reserved INTEGER NOT NULL DEFAULT 0")
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_orders_account_created "
            "ON orders(account_id, created_at DESC)"
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
                """INSERT OR IGNORE INTO catalog_products
                (slug, name, category, description, image, icon, rating, reviews, price, old_price, features_json, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    product["slug"], product["name"], product["category"], product["description"],
                    product["image"], product["icon"], product["rating"], product["reviews"],
                    product["price"], product["old_price"], json.dumps(product["features"]), now,
                ),
            )
            connection.execute(
                "INSERT OR IGNORE INTO product_inventory (product_slug, stock) VALUES (?, ?)",
                (product["slug"], INITIAL_PRODUCT_STOCK),
            )
        for listing in AUCTION_LISTINGS:
            connection.execute(
                """INSERT OR IGNORE INTO catalog_products
                (slug, name, category, description, image, icon, price, features_json, show_in_catalog, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, '[]', 0, ?)""",
                (
                    listing["slug"], listing["name"], listing["category"], listing["description"],
                    listing["image"], listing["icon"], listing["original_price"], now,
                ),
            )
            connection.execute(
                "INSERT OR IGNORE INTO product_inventory (product_slug, stock) VALUES (?, ?)",
                (listing["slug"], INITIAL_PRODUCT_STOCK),
            )
        for listing in AUCTION_LISTINGS:
            connection.execute(
                """INSERT OR IGNORE INTO auctions
                (slug, current_bid, ends_at, starting_bid, minimum_increment) VALUES (?, ?, ?, ?, ?)""",
                (
                    listing["slug"],
                    listing["starting_bid"],
                    now + listing["duration_days"] * 24 * 60 * 60,
                    listing["starting_bid"],
                    listing["minimum_increment"],
                ),
            )
            connection.execute(
                "UPDATE auctions SET starting_bid = ?, minimum_increment = ? "
                "WHERE slug = ? AND starting_bid = 0",
                (listing["starting_bid"], listing["minimum_increment"], listing["slug"]),
            )
        connection.execute(
            "DELETE FROM offers WHERE (product_slug, title) IN "
            "(('jbl-wireless-headphones', 'JBL Headphones · 40% OFF'), "
            "('smart-watch-bluetooth-calling', 'Smart Watch · 25% OFF'), "
            "('wireless-earbuds', 'Wireless Earbuds · 26% OFF'))"
        )


initialize_database()


@app.context_processor
def csrf_context():
    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_urlsafe(32)
    user_role = None
    current_user_email = None
    current_user_name = None
    pending_role_request_count = 0
    unread_notification_count = 0
    if session.get("user_id"):
        with database() as connection:
            account = connection.execute(
                "SELECT role, full_name, email, is_active FROM accounts WHERE id = ?", (session["user_id"],)
            ).fetchone()
            if account and account["is_active"]:
                user_role = account["role"]
                current_user_name = account["full_name"]
                current_user_email = account["email"]
                unread_notification_count = connection.execute(
                    "SELECT COUNT(*) FROM notifications WHERE account_id = ? AND read_at IS NULL",
                    (session["user_id"],),
                ).fetchone()[0]
                if user_role == "superadmin":
                    pending_role_request_count = connection.execute(
                        "SELECT COUNT(*) FROM admin_role_requests WHERE status = 'pending'"
                    ).fetchone()[0]
    return {
        "csrf_token": session["csrf_token"],
        "current_user_role": user_role,
        "current_user_email": current_user_email,
        "current_user_name": current_user_name,
        "pending_role_request_count": pending_role_request_count,
        "unread_notification_count": unread_notification_count,
    }


def create_notification(connection, account_id, title, message, target_url, created_at=None):
    if not account_id:
        return
    connection.execute(
        "INSERT INTO notifications (account_id, title, message, target_url, created_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (account_id, title, message, target_url, created_at or int(time.time())),
    )


def notify_roles(
    connection, roles, title, message, target_url, *, exclude_account_id=None, created_at=None
):
    placeholders = ", ".join("?" for _ in roles)
    if not placeholders:
        return
    recipients = connection.execute(
        f"SELECT id FROM accounts WHERE role IN ({placeholders}) AND is_active = 1",
        tuple(roles),
    ).fetchall()
    for recipient in recipients:
        if recipient["id"] != exclude_account_id:
            create_notification(
                connection, recipient["id"], title, message, target_url, created_at
            )


def notify_staff(connection, title, message, target_url, *, exclude_account_id=None, created_at=None):
    notify_roles(
        connection,
        ("admin", "superadmin"),
        title,
        message,
        target_url,
        exclude_account_id=exclude_account_id,
        created_at=created_at,
    )


def notify_superadmins(
    connection, title, message, target_url, *, exclude_account_id=None, created_at=None
):
    notify_roles(
        connection,
        ("superadmin",),
        title,
        message,
        target_url,
        exclude_account_id=exclude_account_id,
        created_at=created_at,
    )


def notify_auction_bidders(connection, slug, title, message, target_url, created_at=None):
    bidders = connection.execute(
        "SELECT DISTINCT auction_bids.account_id "
        "FROM auction_bids JOIN auctions ON auctions.id = auction_bids.auction_id "
        "WHERE auctions.slug = ?",
        (slug,),
    ).fetchall()
    for bidder in bidders:
        create_notification(
            connection, bidder["account_id"], title, message, target_url, created_at
        )


@app.get("/notifications")
def notifications_page():
    account_id = session.get("user_id")
    if not account_id:
        abort(403)
    with database() as connection:
        notifications = connection.execute(
            "SELECT id, title, message, target_url, created_at, read_at "
            "FROM notifications WHERE account_id = ? ORDER BY created_at DESC, id DESC LIMIT 100",
            (account_id,),
        ).fetchall()
        unread_count = connection.execute(
            "SELECT COUNT(*) FROM notifications WHERE account_id = ? AND read_at IS NULL",
            (account_id,),
        ).fetchone()[0]
    return render_template(
        "notifications.html",
        notifications=notifications,
        unread_notification_count=unread_count,
        active_page="notifications",
    )


@app.get("/notifications/<int:notification_id>/open")
def open_notification(notification_id):
    account_id = session.get("user_id")
    if not account_id:
        abort(403)
    with database() as connection:
        notification = connection.execute(
            "SELECT target_url FROM notifications WHERE id = ? AND account_id = ?",
            (notification_id, account_id),
        ).fetchone()
        if not notification:
            abort(404)
        connection.execute(
            "UPDATE notifications SET read_at = COALESCE(read_at, ?) "
            "WHERE id = ? AND account_id = ?",
            (int(time.time()), notification_id, account_id),
        )
    return redirect(notification["target_url"])


@app.post("/notifications/read-all")
def mark_all_notifications_read():
    account_id = session.get("user_id")
    if not account_id:
        abort(403)
    with database() as connection:
        connection.execute(
            "UPDATE notifications SET read_at = ? WHERE account_id = ? AND read_at IS NULL",
            (int(time.time()), account_id),
        )
    flash("All notifications marked as read.", "success")
    return redirect(url_for("notifications_page"))


@app.get("/my-orders")
def my_orders_page():
    account_id = session.get("user_id")
    if not account_id:
        abort(403)
    with database() as connection:
        rows = connection.execute(
            """SELECT orders.id AS order_id, orders.order_number, orders.created_at,
            orders.subtotal, orders.delivery_fee, orders.discount, orders.total,
            orders.coupon_code, orders.payment_method, orders.payment_status,
            orders.order_status, order_items.id AS item_id, order_items.product_name,
            order_items.product_slug, order_items.quantity, order_items.unit_price
            FROM orders LEFT JOIN order_items ON order_items.order_id = orders.id
            WHERE orders.account_id = ?
            ORDER BY orders.created_at DESC, orders.id DESC, order_items.id""",
            (account_id,),
        ).fetchall()

    orders_by_id = {}
    status_indexes = {
        "confirmed": 0,
        "processing": 1,
        "shipped": 2,
        "delivered": 3,
    }
    for row in rows:
        order = orders_by_id.get(row["order_id"])
        if order is None:
            order = {
                "id": row["order_id"],
                "order_number": row["order_number"],
                "created_at": row["created_at"],
                "subtotal": row["subtotal"],
                "delivery_fee": row["delivery_fee"],
                "discount": row["discount"],
                "total": row["total"],
                "coupon_code": row["coupon_code"],
                "payment_method": row["payment_method"],
                "payment_status": row["payment_status"],
                "order_status": row["order_status"],
                "status_index": status_indexes.get(row["order_status"], -1),
                "items": [],
            }
            orders_by_id[row["order_id"]] = order
        if row["item_id"] is not None:
            order["items"].append({
                "name": row["product_name"],
                "slug": row["product_slug"],
                "quantity": row["quantity"],
                "unit_price": row["unit_price"],
            })

    return render_template(
        "my_orders.html",
        orders=list(orders_by_id.values()),
        active_page="my_orders",
    )


@app.template_filter("datetime")
def format_datetime(timestamp):
    return datetime.fromtimestamp(timestamp, timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


@app.before_request
def protect_post_requests():
    account_id = session.get("user_id")
    if account_id:
        with database() as connection:
            account = connection.execute(
                "SELECT role, email, full_name, is_active, is_verified FROM accounts WHERE id = ?",
                (account_id,),
            ).fetchone()
        if not account or not account["is_active"] or not account["is_verified"]:
            session.clear()
            flash("Your account is inactive or requires email verification. Please sign in again.", "error")
        else:
            session["user_role"] = account["role"]
            session["user_email"] = account["email"]
            session["user_name"] = account["full_name"]

    external_payment_callbacks = {
        "sslcommerz_success",
        "sslcommerz_fail",
        "sslcommerz_cancel",
        "sslcommerz_ipn",
    }
    if request.method == "POST" and request.endpoint not in external_payment_callbacks:
        submitted_token = request.form.get("csrf_token", "")
        session_token = session.get("csrf_token", "")
        if not submitted_token or not secrets.compare_digest(submitted_token, session_token):
            flash("Your form session expired. Please try submitting the form again.", "error")
            destinations = {
                "register": "registration_page",
                "review_admin_request": "admin_role_requests_page",
                "resend_verification": "registration_page",
                "login": "login_page",
                "request_password_reset": "forgot_password_page",
                "reset_password": "forgot_password_page",
                "logout": "home",
                "update_profile": "profile_page",
                "mark_all_notifications_read": "notifications_page",
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
    with database() as connection:
        product_inventory = {
            row["product_slug"]: row["stock"]
            for row in connection.execute("SELECT product_slug, stock FROM product_inventory")
        }
    products_by_slug = {product["slug"]: product for product in get_products()}
    featured_products = [
        products_by_slug[product["slug"]]
        for product in PRODUCT_CATALOG[:6]
        if product["slug"] in products_by_slug
    ]
    auction, _ = get_auction(DEMO_AUCTION_SLUG)
    featured_offers = get_offer_listings()[:3]
    max_offer_discount = max(
        (offer["discount_percent"] for offer in featured_offers), default=0
    )
    return render_template(
        "index.html",
        active_page="home",
        featured_auction=auction,
        featured_offers=featured_offers,
        max_offer_discount=max_offer_discount,
        product_inventory=product_inventory,
        featured_products=featured_products,
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
        products=[{**product, "stock": inventory.get(product["slug"], 0)} for product in get_products()],
        current_user_email=session.get("user_email"),
        current_user_name=session.get("user_name"),
        active_page="products",
    )


@app.get("/products/<slug>")
def product_details_page(slug):
    product = get_product(slug)
    if not product:
        abort(404)
    with database() as connection:
        inventory = connection.execute(
            "SELECT stock FROM product_inventory WHERE product_slug = ?", (slug,)
        ).fetchone()
    related_products = [
        item for item in get_products()
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


def _save_cart_item(account_id, slug, quantity, add_quantity=False):
    product = get_product(slug)
    if not product:
        return "This product is no longer available."

    with database() as connection:
        connection.execute("BEGIN IMMEDIATE")
        inventory = connection.execute(
            "SELECT stock FROM product_inventory WHERE product_slug = ?", (slug,)
        ).fetchone()
        stock = inventory["stock"] if inventory else 0
        existing = connection.execute(
            "SELECT quantity FROM cart_items WHERE account_id = ? AND product_slug = ?",
            (account_id, slug),
        ).fetchone()
        final_quantity = quantity + (existing["quantity"] if existing and add_quantity else 0)
        if stock < 1:
            return "This product is out of stock."
        if final_quantity > min(stock, 99):
            return f"Your cart can contain up to {min(stock, 99)} item(s) of this product."
        connection.execute(
            """INSERT INTO cart_items (account_id, product_slug, quantity, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(account_id, product_slug) DO UPDATE SET
                quantity = excluded.quantity, updated_at = excluded.updated_at""",
            (account_id, slug, final_quantity, int(time.time())),
        )
    return None


@app.post("/cart/add")
def add_to_cart():
    slug = request.form.get("product_slug", "").strip()
    quantity = _parse_quantity(request.form.get("quantity", "1"))
    if not get_product(slug):
        flash("This product is no longer available.", "error")
        return redirect(url_for("products_page"))
    if quantity is None:
        flash("Choose a valid quantity between 1 and 99.", "error")
        return redirect(url_for("product_details_page", slug=slug))

    account_id = session.get("user_id")
    if not account_id:
        session["pending_cart_add"] = {"slug": slug, "quantity": quantity}
        flash("Log in to save this product to your cart.", "info")
        return redirect(url_for("login_page", next=url_for("my_cart_page")))

    error = _save_cart_item(account_id, slug, quantity, add_quantity=True)
    if error:
        flash(error, "error")
    else:
        flash(f"{quantity} item(s) added to your cart.", "success")
    return redirect(url_for("my_cart_page"))


@app.get("/my-cart")
def my_cart_page():
    account_id = session.get("user_id")
    if not account_id:
        return redirect(url_for("login_page", next=url_for("my_cart_page")))

    with database() as connection:
        rows = connection.execute(
            """SELECT product_slug, quantity FROM cart_items
            WHERE account_id = ? ORDER BY updated_at DESC, product_slug""",
            (account_id,),
        ).fetchall()
    items = []
    for row in rows:
        product = get_product(row["product_slug"])
        items.append({
            "slug": row["product_slug"],
            "quantity": row["quantity"],
            "product": product,
            "stock": _checkout_stock(row["product_slug"]) if product else 0,
        })
    return render_template(
        "my_cart.html",
        items=items,
        active_page="my_cart",
    )


@app.post("/my-cart/<slug>/update")
def update_cart_item(slug):
    account_id = session.get("user_id")
    if not account_id:
        return redirect(url_for("login_page", next=url_for("my_cart_page")))
    quantity = _parse_quantity(request.form.get("quantity"))
    if quantity is None:
        flash("Choose a valid quantity between 1 and 99.", "error")
        return redirect(url_for("my_cart_page"))

    error = _save_cart_item(account_id, slug, quantity)
    if error:
        flash(error, "error")
    else:
        flash("Cart quantity updated.", "success")
    return redirect(url_for("my_cart_page"))


@app.post("/my-cart/<slug>/remove")
def remove_cart_item(slug):
    account_id = session.get("user_id")
    if not account_id:
        return redirect(url_for("login_page", next=url_for("my_cart_page")))
    with database() as connection:
        connection.execute(
            "DELETE FROM cart_items WHERE account_id = ? AND product_slug = ?",
            (account_id, slug),
        )
    flash("Product removed from your cart.", "success")
    return redirect(url_for("my_cart_page"))


def _checkout_product():
    draft = session.get("checkout_draft")
    if not isinstance(draft, dict):
        return None
    slug = draft.get("product_slug")
    return get_product(slug)


def _parse_quantity(raw_quantity):
    try:
        quantity = int(raw_quantity)
    except (TypeError, ValueError):
        return None
    return quantity if 1 <= quantity <= 99 else None


def _checkout_stock(slug):
    with database() as connection:
        release_expired_online_orders(connection, int(time.time()))
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
        "sslcommerz_ready": sslcommerz_is_configured(),
        "current_user_name": session.get("user_name"),
        "current_user_email": session.get("user_email"),
        "active_page": "products",
    }


def sslcommerz_is_configured():
    base_url = urlparse(os.getenv("APP_BASE_URL", "").strip())
    return bool(
        os.getenv("SSLCOMMERZ_STORE_ID")
        and os.getenv("SSLCOMMERZ_STORE_PASSWORD")
        and base_url.scheme == "https"
        and base_url.hostname
        and base_url.hostname not in ("localhost", "127.0.0.1")
    )


def sslcommerz_endpoint(api_name):
    sandbox = os.getenv("SSLCOMMERZ_IS_SANDBOX", "true").strip().lower() != "false"
    host = "https://sandbox.sslcommerz.com" if sandbox else "https://securepay.sslcommerz.com"
    paths = {
        "initiate": "/gwprocess/v4/api.php",
        "validate": "/validator/api/validationserverAPI.php",
    }
    return host + paths[api_name]


def sslcommerz_api_request(endpoint, payload, method="POST"):
    encoded_payload = urlencode(payload)
    target = endpoint + ("?" + encoded_payload if method == "GET" else "")
    api_request = Request(
        target,
        data=encoded_payload.encode("utf-8") if method == "POST" else None,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method=method,
    )
    with urlopen(api_request, timeout=20) as response:
        result = json.loads(response.read().decode("utf-8"))
    if not isinstance(result, dict):
        raise ValueError("SSLCommerz returned an invalid response.")
    return result


def initiate_sslcommerz_payment(order, product_name):
    base_url = os.getenv("APP_BASE_URL", "").strip().rstrip("/")
    parsed_base_url = urlparse(base_url)
    if parsed_base_url.scheme != "https" or not parsed_base_url.hostname or parsed_base_url.hostname in (
        "localhost", "127.0.0.1",
    ):
        raise ValueError("Set APP_BASE_URL to this site's public HTTPS address before enabling payments.")
    callback_base = base_url
    payload = {
        "store_id": os.environ["SSLCOMMERZ_STORE_ID"],
        "store_passwd": os.environ["SSLCOMMERZ_STORE_PASSWORD"],
        "total_amount": f"{order['total']:.2f}",
        "currency": "BDT",
        "tran_id": order["order_number"],
        "success_url": callback_base + url_for("sslcommerz_success"),
        "fail_url": callback_base + url_for("sslcommerz_fail"),
        "cancel_url": callback_base + url_for("sslcommerz_cancel"),
        "ipn_url": callback_base + url_for("sslcommerz_ipn"),
        "shipping_method": "YES",
        "num_of_item": str(order["quantity"]),
        "product_name": product_name[:200],
        "product_category": "General",
        "product_profile": "physical-goods",
        "cus_name": order["customer_name"][:50],
        "cus_email": order["customer_email"],
        "cus_add1": order["address"][:50],
        "cus_add2": order["district"][:50],
        "cus_city": order["division"],
        "cus_postcode": order["postal_code"] or "1000",
        "cus_country": "Bangladesh",
        "cus_phone": order["customer_phone"],
        "ship_name": order["customer_name"][:50],
        "ship_add1": order["address"][:50],
        "ship_add2": order["district"][:50],
        "ship_area": order["district"][:50],
        "ship_city": order["division"],
        "ship_state": order["division"],
        "ship_postcode": order["postal_code"] or "1000",
        "ship_country": "Bangladesh",
    }
    response = sslcommerz_api_request(sslcommerz_endpoint("initiate"), payload)
    gateway_url = response.get("GatewayPageURL", "")
    gateway_host = urlparse(gateway_url).hostname
    allowed_hosts = {"sandbox.sslcommerz.com", "securepay.sslcommerz.com"}
    if response.get("status") != "SUCCESS" or urlparse(gateway_url).scheme != "https" or gateway_host not in allowed_hosts:
        raise ValueError("SSLCommerz could not start the payment session.")
    return gateway_url


def validate_sslcommerz_payment(order, val_id):
    if not val_id or len(val_id) > 100:
        return False
    response = sslcommerz_api_request(
        sslcommerz_endpoint("validate"),
        {
            "val_id": val_id,
            "store_id": os.environ["SSLCOMMERZ_STORE_ID"],
            "store_passwd": os.environ["SSLCOMMERZ_STORE_PASSWORD"],
            "format": "json",
        },
        method="GET",
    )
    try:
        amount = Decimal(str(response.get("amount", "")))
    except InvalidOperation:
        return False
    return (
        str(response.get("status", "")) in ("VALID", "VALIDATED")
        and response.get("tran_id") == order["order_number"]
        and str(response.get("currency", "")).upper() == "BDT"
        and str(response.get("risk_level", "0")) == "0"
        and amount == Decimal(order["total"])
    )


def complete_sslcommerz_payment(tran_id, val_id):
    if not sslcommerz_is_configured():
        return False
    with database() as connection:
        order = connection.execute(
            "SELECT * FROM orders WHERE order_number = ? AND payment_method != 'cod'",
            (tran_id,),
        ).fetchone()
    if not order:
        return False
    try:
        if not validate_sslcommerz_payment(order, val_id):
            return False
    except (URLError, TimeoutError, ValueError, json.JSONDecodeError, OSError):
        logging.warning("SSLCommerz transaction validation could not be completed for an order.")
        return False

    with database() as connection:
        result = connection.execute(
            "UPDATE orders SET payment_status = 'paid', order_status = 'confirmed', stock_reserved = 0 "
            "WHERE id = ? AND payment_method != 'cod' AND payment_status != 'paid' "
            "AND stock_reserved = 1",
            (order["id"],),
        )
        current_state = connection.execute(
            "SELECT payment_status FROM orders WHERE id = ?", (order["id"],)
        ).fetchone()
        if result.rowcount == 1:
            message = f"Payment received for order {order['order_number']}. Your order is confirmed."
            create_notification(
                connection, order["account_id"], "Payment confirmed", message,
                url_for("my_orders_page", _anchor=f"order-{order['order_number']}"),
            )
            notify_staff(
                connection, "Order payment received",
                f"Order {order['order_number']} has been paid and confirmed.",
                url_for("admin_dashboard") + "#orders",
            )
    return result.rowcount == 1 or current_state["payment_status"] == "paid"


def release_order_stock(connection, order_id):
    order = connection.execute(
        "SELECT stock_reserved FROM orders WHERE id = ?", (order_id,)
    ).fetchone()
    if not order or not order["stock_reserved"]:
        return
    items = connection.execute(
        "SELECT product_slug, quantity FROM order_items WHERE order_id = ?", (order_id,)
    ).fetchall()
    for item in items:
        connection.execute(
            "UPDATE product_inventory SET stock = stock + ? WHERE product_slug = ?",
            (item["quantity"], item["product_slug"]),
        )
    connection.execute("UPDATE orders SET stock_reserved = 0 WHERE id = ?", (order_id,))


def release_expired_online_orders(connection, now):
    expired = connection.execute(
        "SELECT id, account_id, order_number FROM orders "
        "WHERE payment_method != 'cod' AND payment_status != 'paid' "
        "AND stock_reserved = 1 AND created_at <= ?",
        (now - 30 * 60,),
    ).fetchall()
    for order in expired:
        result = connection.execute(
            "UPDATE orders SET payment_status = 'failed' WHERE id = ? AND payment_status != 'paid'",
            (order["id"],),
        )
        if result.rowcount:
            create_notification(
                connection,
                order["account_id"],
                "Payment session expired",
                f"The payment window for order {order['order_number']} expired. Please place the order again.",
                url_for("my_orders_page", _anchor=f"order-{order['order_number']}"),
                now,
            )
            notify_staff(
                connection,
                "Order payment session expired",
                f"The payment window for order {order['order_number']} expired.",
                url_for("admin_dashboard") + "#orders",
                created_at=now,
            )
        release_order_stock(connection, order["id"])


@app.post("/payment/sslcommerz/success")
def sslcommerz_success():
    tran_id = request.form.get("tran_id", "")
    val_id = request.form.get("val_id", "")
    if complete_sslcommerz_payment(tran_id, val_id):
        return redirect(url_for("payment_result", order_number=tran_id))
    logging.warning("SSLCommerz reported a payment that failed server-side verification.")
    return redirect(url_for("payment_result", order_number=tran_id, result="verification-pending"))


@app.post("/payment/sslcommerz/ipn")
def sslcommerz_ipn():
    tran_id = request.form.get("tran_id", "")
    val_id = request.form.get("val_id", "")
    if complete_sslcommerz_payment(tran_id, val_id):
        return "OK", 200
    return "Payment not verified", 400


@app.post("/payment/sslcommerz/fail")
def sslcommerz_fail():
    tran_id = request.form.get("tran_id", "")
    with database() as connection:
        order = connection.execute(
            "SELECT id, account_id, order_number FROM orders "
            "WHERE order_number = ? AND payment_method != 'cod' AND payment_status = 'unpaid'",
            (tran_id,),
        ).fetchone()
        result = connection.execute(
            "UPDATE orders SET payment_status = 'failed' "
            "WHERE order_number = ? AND payment_method != 'cod' AND payment_status = 'unpaid'",
            (tran_id,),
        )
        if result.rowcount and order:
            create_notification(
                connection, order["account_id"], "Payment failed",
                f"Payment for order {order['order_number']} was not completed. You can try checkout again.",
                url_for("my_orders_page", _anchor=f"order-{order['order_number']}"),
            )
            notify_staff(
                connection, "Order payment failed",
                f"Payment for order {order['order_number']} was not completed.",
                url_for("admin_dashboard") + "#orders",
            )
    return redirect(url_for("payment_result", order_number=tran_id))


@app.post("/payment/sslcommerz/cancel")
def sslcommerz_cancel():
    return sslcommerz_fail()


@app.get("/payment/result/<order_number>")
def payment_result(order_number):
    with database() as connection:
        order = connection.execute(
            "SELECT order_number, total, payment_status, order_status FROM orders WHERE order_number = ?",
            (order_number,),
        ).fetchone()
    if not order:
        abort(404)
    return render_template(
        "payment_result.html",
        order=order,
        verification_pending=request.args.get("result") == "verification-pending",
        current_user_name=session.get("user_name"),
        current_user_email=session.get("user_email"),
    )


@app.post("/checkout/start")
def start_checkout():
    slug = request.form.get("product_slug", "")
    product = get_product(slug)
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
    if not session.get("user_id"):
        flash("Log in or create a verified account before checkout.", "error")
        return redirect(url_for("login_page", next=url_for("checkout_page")))
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
    if not session.get("user_id"):
        flash("Log in or create a verified account before checkout.", "error")
        return redirect(url_for("login_page", next=url_for("checkout_page")))
    context = _checkout_context()
    if not context:
        flash("Choose a product before starting checkout.", "error")
        return redirect(url_for("products_page"))
    return render_template("checkout.html", **context)


@app.post("/checkout/apply-coupon")
def apply_checkout_coupon():
    if not session.get("user_id"):
        return jsonify(error="Log in or create a verified account before checkout."), 401
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
    if not session.get("user_id"):
        flash("Log in or create a verified account before placing an order.", "error")
        return redirect(url_for("login_page", next=url_for("checkout_page")))
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
    if payment_method not in ("cod", "card"):
        errors["payment_method"] = "Choose a supported payment method."
    elif payment_method != "cod":
        if not sslcommerz_is_configured():
            errors["payment_method"] = "Online payment is not configured yet. Choose Cash on Delivery or ask the store administrator to configure SSLCommerz."
        elif not email:
            errors["customer_email"] = "Enter an email address for the payment receipt."
        elif len(email) > 50:
            errors["customer_email"] = "SSLCommerz requires an email address of 50 characters or fewer."
        elif quantity is not None:
            payable = _checkout_totals(product, quantity, division, coupon_code)["total"]
            if not 10 <= payable <= 500000:
                errors["payment_method"] = "SSLCommerz supports online payments from ৳10 to ৳500,000."
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
    order_number = f"BM-{secrets.token_hex(12).upper()}"
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
                total, coupon_code, payment_method, order_status, payment_status, stock_reserved, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                order_number, checkout_key, hashlib.sha256(tracking_token.encode()).hexdigest(),
                account_id, name, email or None, phone, division, district, address,
                postal_code or None, delivery_note or None, totals["subtotal"],
                totals["delivery_fee"], totals["discount"], totals["total"],
                coupon_code or None, payment_method, order_status, payment_status, 1, now,
            ),
        )
        order_id = connection.execute("SELECT last_insert_rowid()").fetchone()[0]
        connection.execute(
            """INSERT INTO order_items
            (order_id, product_slug, product_name, quantity, unit_price, variant_id)
            VALUES (?, ?, ?, ?, ?, NULL)""",
            (order_id, product["slug"], product["name"], quantity, product["price"]),
        )
        create_notification(
            connection,
            account_id,
            "Order placed",
            f"Order {order_number} was placed. "
            + ("It is confirmed and awaiting payment on delivery."
               if payment_method == "cod" else "Complete payment to confirm your order."),
            url_for("my_orders_page", _anchor=f"order-{order_number}"),
            now,
        )
        notify_staff(
            connection,
            "New order received",
            f"{name} placed order {order_number} for {product['name']} × {quantity}.",
            url_for("admin_dashboard") + "#orders",
            exclude_account_id=account_id,
            created_at=now,
        )

    if payment_method != "cod":
        order = {
            "order_number": order_number,
            "total": totals["total"],
            "customer_name": name,
            "customer_email": email,
            "customer_phone": phone,
            "quantity": quantity,
            "address": address,
            "district": district,
            "division": division,
            "postal_code": postal_code,
        }
        try:
            gateway_url = initiate_sslcommerz_payment(order, product["name"])
        except (URLError, TimeoutError, ValueError, json.JSONDecodeError, OSError):
            logging.warning("SSLCommerz payment session could not be created.")
            with database() as connection:
                connection.execute(
                    "UPDATE orders SET payment_status = 'failed' WHERE order_number = ? AND payment_status = 'unpaid'",
                    (order_number,),
                )
                release_order_stock(connection, order_id)
            draft["checkout_key"] = secrets.token_urlsafe(24)
            session["checkout_draft"] = draft
            flash(
                "SSLCommerz could not start the payment. No payment was taken; please try again or choose Cash on Delivery.",
                "error",
            )
            return redirect(url_for("checkout_page"))
        draft["order_number"] = order_number
        draft["tracking_token"] = tracking_token
        session["checkout_draft"] = draft
        return redirect(gateway_url)

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
    listings = [
        {**listing, "is_ended": listing["ends_at"] <= now}
        for listing in get_auction_listings()
    ]
    return render_template(
        "auctions.html",
        auctions=listings,
        now=now,
        current_user_email=session.get("user_email"),
        current_user_name=session.get("user_name"),
        active_page="auctions",
    )


@app.get("/offers")
def offers_page():
    offers = get_offer_listings()
    with database() as connection:
        inventory = {
            row["product_slug"]: row["stock"]
            for row in connection.execute("SELECT product_slug, stock FROM product_inventory")
        }
    return render_template(
        "offers.html",
        offers=[{**offer, "stock": inventory.get(offer["product_slug"], 0)} for offer in offers],
        current_user_email=session.get("user_email"),
        current_user_name=session.get("user_name"),
        active_page="offers",
    )


def get_auction(slug):
    with database() as connection:
        auction = connection.execute(
            "SELECT a.id, a.slug, a.current_bid, a.ends_at, a.minimum_increment, "
            "p.name, p.category, p.description, p.image, p.icon, p.price AS original_price "
            "FROM auctions AS a JOIN catalog_products AS p ON p.slug = a.slug "
            "WHERE a.slug = ? AND a.is_active = 1 AND p.is_active = 1",
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
    return dict(auction), recent_bids


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
    listing = get_auction_listings()
    listing = next((item for item in listing if item["slug"] == slug), None)
    if not listing:
        abort(404)
    auction_url = url_for("auction_details", slug=slug)
    if not session.get("user_id"):
        flash("Log in to your verified account before placing a bid.", "error")
        return redirect(url_for("login_page", next=auction_url))
    with database() as connection:
        bidder = connection.execute(
            "SELECT is_active, is_verified FROM accounts WHERE id = ?", (session["user_id"],)
        ).fetchone()
    if not bidder or not bidder["is_active"] or not bidder["is_verified"]:
        session.clear()
        flash("Sign in to an active, verified account before placing a bid.", "error")
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

        previous_leader = connection.execute(
            "SELECT account_id, amount FROM auction_bids "
            "WHERE auction_id = ? ORDER BY amount DESC, created_at DESC, id DESC LIMIT 1",
            (auction["id"],),
        ).fetchone()
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
        create_notification(
            connection,
            session["user_id"],
            "Your bid was placed",
            f"Your bid of ৳ {amount:,} on {listing['name']} was placed successfully.",
            auction_url,
            now,
        )
        if previous_leader and previous_leader["account_id"] != session["user_id"]:
            create_notification(
                connection,
                previous_leader["account_id"],
                "You have been outbid",
                f"A higher bid was placed on {listing['name']}. The current bid is ৳ {amount:,}.",
                auction_url,
                now,
            )
        notify_staff(
            connection,
            "New auction bid",
            f"A user bid ৳ {amount:,} on {listing['name']}.",
            auction_url,
            exclude_account_id=session["user_id"],
            created_at=now,
        )

    flash(f"Your bid of ৳ {amount:,} was placed successfully.", "success")
    return redirect(auction_url)


@app.get("/style.css")
def stylesheet():
    return send_from_directory(ROOT, "style.css", mimetype="text/css")


def valid_login_next_url(candidate):
    allowed_destinations = {url_for("checkout_page"), url_for("my_cart_page")}
    allowed_destinations.update(
        url_for("auction_details", slug=listing["slug"])
        for listing in get_auction_listings()
    )
    return candidate if candidate in allowed_destinations else ""


@app.get("/register.html")
def registration_page():
    registration_request = None
    account_id = session.get("pending_role_request_account_id")
    if account_id:
        with database() as connection:
            registration_request = connection.execute(
                "SELECT a.full_name, a.email, a.is_verified, a.verification_token_hash, "
                "r.requested_role, r.status "
                "FROM accounts AS a JOIN admin_role_requests AS r ON r.account_id = a.id "
                "WHERE a.id = ?",
                (account_id,),
            ).fetchone()
        if not registration_request:
            session.pop("pending_role_request_account_id", None)
    next_url = valid_login_next_url(request.args.get("next", ""))
    if not next_url:
        next_url = valid_login_next_url(session.get("login_next_url", ""))
    return render_template(
        "register.html",
        registration_request=registration_request,
        next_url=next_url,
    )


def create_initial_superadmin(full_name, email, password):
    full_name = full_name.strip()
    email = email.strip().casefold()
    if not full_name or "@" not in email or len(password) < 8:
        raise ValueError("Enter a valid name and email, and a password of at least 8 characters.")

    with database() as connection:
        if connection.execute(
            "SELECT 1 FROM accounts WHERE role = 'superadmin' LIMIT 1"
        ).fetchone():
            raise ValueError("A Superadmin already exists. Use the approval page to add elevated accounts.")
        account = connection.execute(
            "SELECT id, role, is_verified, password_hash FROM accounts WHERE email = ?",
            (email,),
        ).fetchone()
        if account:
            if account["role"] != "user":
                raise ValueError("Only an existing User account can be upgraded during initial setup.")
            if not account["is_verified"]:
                raise ValueError("Verify this account's email before upgrading it to Superadmin.")
            if not check_password_hash(account["password_hash"], password):
                raise ValueError("The password does not match the existing account.")
            connection.execute(
                "UPDATE accounts SET role = 'superadmin' WHERE id = ? AND role = 'user'",
                (account["id"],),
            )
            connection.execute(
                "UPDATE admin_role_requests SET status = 'approved', requested_role = 'superadmin', "
                "reviewed_at = ?, reviewed_by = ? WHERE account_id = ? AND status = 'pending'",
                (int(time.time()), account["id"], account["id"]),
            )
            return "upgraded"

        connection.execute(
            "INSERT INTO accounts (full_name, email, phone, password_hash, role, is_verified, created_at) "
            "VALUES (?, ?, '', ?, 'superadmin', 1, ?)",
            (full_name, email, generate_password_hash(password), int(time.time())),
        )
        return "created"


def require_superadmin():
    account_id = session.get("user_id")
    if not account_id:
        abort(403)
    with database() as connection:
        account = connection.execute(
            "SELECT role, is_active FROM accounts WHERE id = ?", (account_id,)
        ).fetchone()
    if not account or not account["is_active"] or account["role"] != "superadmin":
        abort(403)
    return account_id


def require_staff():
    account_id = session.get("user_id")
    if not account_id:
        abort(403)
    with database() as connection:
        account = connection.execute(
            "SELECT role, is_active FROM accounts WHERE id = ?", (account_id,)
        ).fetchone()
    if not account or not account["is_active"] or account["role"] not in ("admin", "superadmin"):
        abort(403)
    return account_id


@app.get("/profile")
def profile_page():
    account_id = session.get("user_id")
    if not account_id:
        abort(403)
    with database() as connection:
        account = connection.execute(
            "SELECT full_name, email, phone, role FROM accounts "
            "WHERE id = ? AND is_active = 1 AND is_verified = 1",
            (account_id,),
        ).fetchone()
    if not account:
        abort(403)
    return render_template("profile.html", account=account, active_page="profile")


@app.post("/profile/update")
def update_profile():
    account_id = session.get("user_id")
    if not account_id:
        abort(403)

    full_name = request.form.get("full_name", "").strip()
    email = request.form.get("email", "").strip().casefold()
    phone = request.form.get("phone", "").strip()
    current_password = request.form.get("current_password", "")
    new_password = request.form.get("new_password", "")
    confirm_password = request.form.get("confirm_password", "")

    with database() as connection:
        account = connection.execute(
            "SELECT full_name, email, phone, password_hash, role, is_active, is_verified "
            "FROM accounts WHERE id = ?",
            (account_id,),
        ).fetchone()
    if not account or not account["is_active"] or not account["is_verified"]:
        abort(403)

    email_changed = email != account["email"].casefold()
    if not full_name or len(full_name) > 120:
        flash("Enter your name using no more than 120 characters.", "error")
        return redirect(url_for("profile_page"))
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        flash("Enter a valid email address.", "error")
        return redirect(url_for("profile_page"))
    if len(phone) > 32:
        flash("Phone number must be 32 characters or fewer.", "error")
        return redirect(url_for("profile_page"))
    if new_password or confirm_password:
        if len(new_password) < 8:
            flash("A new password must be at least 8 characters.", "error")
            return redirect(url_for("profile_page"))
        if new_password != confirm_password:
            flash("The new password and confirmation do not match.", "error")
            return redirect(url_for("profile_page"))
    if email_changed or new_password:
        if not current_password or not check_password_hash(account["password_hash"], current_password):
            flash("Enter your current password to change your email or password.", "error")
            return redirect(url_for("profile_page"))
    if email_changed and not all(
        os.getenv(setting) for setting in ("SMTP_USERNAME", "SMTP_PASSWORD", "SMTP_FROM")
    ):
        flash(
            "Email changes require verification. Configure email delivery before changing your email address.",
            "error",
        )
        return redirect(url_for("profile_page"))

    password_hash = generate_password_hash(new_password) if new_password else account["password_hash"]
    try:
        with database() as connection:
            connection.execute(
                "UPDATE accounts SET full_name = ?, email = ?, phone = ?, password_hash = ?, "
                "is_verified = ?, verification_token_hash = NULL, verification_expires_at = NULL "
                "WHERE id = ?",
                (
                    full_name,
                    email,
                    phone,
                    password_hash,
                    0 if email_changed else 1,
                    account_id,
                ),
            )
            if account["role"] == "user":
                notify_staff(
                    connection,
                    "Customer profile updated",
                    "A customer updated their account profile.",
                    url_for("admin_dashboard") + "#orders",
                    exclude_account_id=account_id,
                )
            elif account["role"] == "admin":
                notify_superadmins(
                    connection,
                    "Admin profile updated",
                    "An Admin updated their profile details.",
                    url_for("admin_dashboard") + "#accounts",
                    exclude_account_id=account_id,
                )
            elif account["role"] == "superadmin":
                notify_superadmins(
                    connection,
                    "Superadmin profile updated",
                    "A Superadmin updated their profile details.",
                    url_for("admin_dashboard"),
                    exclude_account_id=account_id,
                )
            if new_password:
                create_notification(
                    connection,
                    account_id,
                    "Password changed",
                    "Your BidMart password was changed successfully.",
                    url_for("profile_page"),
                )
            if email_changed:
                create_notification(
                    connection,
                    account_id,
                    "Email change needs verification",
                    "Verify your new email address before signing in again.",
                    url_for("registration_page"),
                )
    except sqlite3.IntegrityError:
        flash("That email address is already associated with another account.", "error")
        return redirect(url_for("profile_page"))

    session["user_name"] = full_name
    if email_changed:
        session.pop("user_id", None)
        session.pop("user_email", None)
        session.pop("user_name", None)
        session.pop("user_role", None)
        try:
            issue_verification(email)
        except (RuntimeError, OSError, smtplib.SMTPException):
            logging.exception("Profile email verification could not be sent")
            flash(
                "Your email was changed, but the verification message could not be sent. "
                "Use the resend verification form with your new email address.",
                "error",
            )
            return redirect(url_for("registration_page"))
        flash("Your email was changed. Verify the new address before logging in again.", "success")
        return redirect(url_for("login_page"))

    flash("Your profile has been updated.", "success")
    return redirect(url_for("profile_page"))


def get_products(include_inactive=False):
    query = "SELECT * FROM catalog_products WHERE show_in_catalog = 1"
    if not include_inactive:
        query += " AND is_active = 1"
    query += " ORDER BY name COLLATE NOCASE"
    with database() as connection:
        rows = connection.execute(query).fetchall()
    products = []
    for row in rows:
        product = dict(row)
        product["features"] = json.loads(product.pop("features_json"))
        product.pop("updated_at")
        product.pop("is_active")
        products.append(product)
    return products


def get_product(slug, include_inactive=False):
    with database() as connection:
        query = (
            "SELECT * FROM catalog_products WHERE slug = ? AND "
            "(show_in_catalog = 1 OR EXISTS (SELECT 1 FROM offers "
            "WHERE offers.product_slug = catalog_products.slug AND offers.is_active = 1 "
            "AND offers.ends_at > ?))"
        )
        if not include_inactive:
            query += " AND is_active = 1"
        row = connection.execute(query, (slug, int(time.time()))).fetchone()
    if not row:
        return None
    product = dict(row)
    product["features"] = json.loads(product.pop("features_json"))
    product.pop("updated_at")
    product.pop("is_active")
    return product


def get_auction_listings(include_inactive=False):
    query = (
        "SELECT a.slug, a.current_bid, a.ends_at, a.starting_bid, a.minimum_increment, "
        "a.is_active, p.name, p.category, p.description, p.image, p.icon, p.price AS original_price, "
        "p.old_price, p.features_json, p.show_in_catalog, i.stock "
        "FROM auctions AS a JOIN catalog_products AS p ON p.slug = a.slug"
        " LEFT JOIN product_inventory AS i ON i.product_slug = p.slug"
    )
    if not include_inactive:
        query += " WHERE a.is_active = 1 AND p.is_active = 1"
    query += " ORDER BY a.ends_at"
    with database() as connection:
        rows = connection.execute(query).fetchall()
    listings = []
    for row in rows:
        listing = dict(row)
        listing["features_text"] = ", ".join(json.loads(listing.pop("features_json")))
        listings.append(listing)
    return listings


def get_offer_listings(include_inactive=False):
    query = (
        "SELECT o.id, o.product_slug, o.title, o.description, o.ends_at, o.is_active, "
        "p.name, p.category, p.description AS product_description, p.image, p.icon, "
        "p.price, p.old_price, p.features_json, i.stock "
        "FROM offers AS o JOIN catalog_products AS p ON p.slug = o.product_slug"
        " LEFT JOIN product_inventory AS i ON i.product_slug = p.slug"
    )
    parameters = ()
    if not include_inactive:
        query += " WHERE o.is_active = 1 AND o.ends_at > ? AND p.is_active = 1"
        parameters = (int(time.time()),)
    query += " ORDER BY o.ends_at, p.name COLLATE NOCASE"
    with database() as connection:
        rows = connection.execute(query, parameters).fetchall()
    offers = []
    for row in rows:
        offer = dict(row)
        old_price = offer["old_price"]
        offer["discount_percent"] = (
            round((old_price - offer["price"]) / old_price * 100)
            if old_price and old_price > offer["price"] else 0
        )
        offer["features"] = json.loads(offer.pop("features_json"))
        offer["features_text"] = ", ".join(offer["features"])
        offer["ends_at_input"] = datetime.fromtimestamp(
            offer["ends_at"], timezone.utc
        ).strftime("%Y-%m-%dT%H:%M")
        offers.append(offer)
    return offers


@app.get("/superadmin/admin-requests")
def admin_role_requests_page():
    require_superadmin()
    with database() as connection:
        requests = connection.execute(
            "SELECT r.account_id, r.requested_role, r.requested_at, a.full_name, a.email, a.is_verified "
            "FROM admin_role_requests AS r "
            "JOIN accounts AS a ON a.id = r.account_id "
            "WHERE r.status = 'pending' ORDER BY r.requested_at"
        ).fetchall()
    return render_template("admin_role_requests.html", requests=requests)


@app.get("/admin/dashboard")
def admin_dashboard():
    staff_id = require_staff()
    with database() as connection:
        products = connection.execute(
            "SELECT p.*, i.stock FROM catalog_products AS p "
            "LEFT JOIN product_inventory AS i ON i.product_slug = p.slug "
            "ORDER BY p.is_active DESC, p.name COLLATE NOCASE"
        ).fetchall()
        orders = connection.execute(
            "SELECT id, order_number, customer_name, customer_email, customer_phone, total, "
            "division, district, address, postal_code, delivery_note, payment_method, payment_status, "
            "order_status, created_at, stock_reserved, "
            "(SELECT GROUP_CONCAT(product_name || ' × ' || quantity, ', ') "
            "FROM order_items WHERE order_id = orders.id) AS item_summary "
            "FROM orders ORDER BY created_at DESC LIMIT 100"
        ).fetchall()
        stats = {
            "products": connection.execute(
                "SELECT COUNT(*) FROM catalog_products WHERE is_active = 1"
            ).fetchone()[0],
            "orders": connection.execute("SELECT COUNT(*) FROM orders").fetchone()[0],
            "paid_revenue": connection.execute(
                "SELECT COALESCE(SUM(total), 0) FROM orders WHERE payment_status = 'paid'"
            ).fetchone()[0],
            "pending_orders": connection.execute(
                "SELECT COUNT(*) FROM orders WHERE order_status = 'pending' OR payment_status = 'unpaid'"
            ).fetchone()[0],
        }
        role_row = connection.execute(
            "SELECT role FROM accounts WHERE id = ?", (staff_id,)
        ).fetchone()
        accounts = []
        if role_row["role"] == "superadmin":
            accounts = connection.execute(
                "SELECT id, full_name, email, role, is_active, is_verified "
                "FROM accounts WHERE id != ? ORDER BY role, full_name COLLATE NOCASE",
                (staff_id,),
            ).fetchall()
    product_rows = []
    for row in products:
        product = dict(row)
        product["features_text"] = ", ".join(json.loads(product.pop("features_json")))
        product_rows.append(product)
    offers = get_offer_listings(include_inactive=True)
    return render_template(
        "admin_dashboard.html",
        products=product_rows,
        orders=orders,
        stats=stats,
        auctions=get_auction_listings(include_inactive=True),
        offers=offers,
        offer_product_slugs={offer["product_slug"] for offer in offers},
        accounts=accounts,
        is_superadmin=bool(accounts) or role_row["role"] == "superadmin",
        current_user_email=session.get("user_email"),
        current_user_name=session.get("user_name"),
    )


def _admin_product_values(form, image_file, existing_image=None, existing_icon=None):
    name = form.get("name", "").strip()
    slug = form.get("slug", "").strip().lower()
    category = form.get("category", "").strip()
    description = form.get("description", "").strip()
    features = [part.strip() for part in form.get("features", "").split(",") if part.strip()]
    try:
        price = int(form.get("price", ""))
        stock = int(form.get("stock", ""))
        old_price = int(form["old_price"]) if form.get("old_price", "").strip() else None
    except ValueError:
        return None, "Price, previous price, and stock must be whole numbers."
    if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", slug) or len(slug) > 100:
        return None, "Use a product slug containing lowercase letters, numbers, and hyphens only."
    if not name or len(name) > 120 or not category or len(category) > 80:
        return None, "Enter a product name (up to 120 characters) and category (up to 80 characters)."
    if not description or len(description) > 1000:
        return None, "Enter a product description of up to 1,000 characters."
    if price < 1 or stock < 0 or stock > 1_000_000:
        return None, "Price must be positive and stock must be between 0 and 1,000,000."
    if old_price is not None and old_price < price:
        return None, "Previous price must be greater than or equal to the current price."
    if len(features) > 8 or any(len(feature) > 120 for feature in features):
        return None, "Add at most 8 product features, each up to 120 characters."
    image_extension = None
    if image_file and image_file.filename:
        if not secure_filename(image_file.filename):
            return None, "Choose a valid product image file."
        image_header = image_file.stream.read(12)
        image_file.stream.seek(0)
        if image_header.startswith(b"\x89PNG\r\n\x1a\n"):
            image_extension = "png"
        elif image_header.startswith(b"\xff\xd8\xff"):
            image_extension = "jpg"
        elif image_header.startswith(b"RIFF") and image_header[8:12] == b"WEBP":
            image_extension = "webp"
        else:
            return None, "Upload a valid PNG, JPEG, or WebP product image."
    elif not existing_image and not existing_icon:
        return None, "Upload a product image (PNG, JPEG, or WebP)."
    return {
        "slug": slug,
        "name": name,
        "category": category,
        "description": description,
        "image_extension": image_extension,
        "icon": None if image_extension else existing_icon,
        "price": price,
        "old_price": old_price,
        "stock": stock,
        "show_in_catalog": 1 if form.get("show_in_catalog", "1") == "1" else 0,
        "features_json": json.dumps(features),
    }, None


def _save_admin_product_image(slug, image_file, extension):
    if not image_file or not extension:
        return None
    upload_directory = ROOT / "static" / "uploads" / "products"
    upload_directory.mkdir(parents=True, exist_ok=True)
    filename = f"{slug}-{secrets.token_hex(8)}.{extension}"
    image_file.save(upload_directory / filename)
    return f"uploads/products/{filename}"


@app.post("/admin/products/create")
def admin_create_product():
    require_staff()
    image_file = request.files.get("image")
    values, error = _admin_product_values(request.form, image_file)
    if error:
        flash(error, "error")
        return redirect(url_for("admin_dashboard") + "#products")
    image_path = _save_admin_product_image(
        values["slug"], image_file, values["image_extension"]
    )
    now = int(time.time())
    try:
        with database() as connection:
            connection.execute(
                """INSERT INTO catalog_products
                (slug, name, category, description, image, icon, price, old_price, features_json, show_in_catalog, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (values["slug"], values["name"], values["category"], values["description"],
                 image_path, values["icon"], values["price"], values["old_price"],
                 values["features_json"], values["show_in_catalog"], now),
            )
            connection.execute(
                "INSERT INTO product_inventory (product_slug, stock) VALUES (?, ?)",
                (values["slug"], values["stock"]),
            )
    except sqlite3.IntegrityError:
        if image_path:
            (ROOT / "static" / image_path).unlink(missing_ok=True)
        flash("A product with that slug already exists.", "error")
        return redirect(url_for("admin_dashboard") + "#products")
    flash("Product created and published.", "success")
    with database() as connection:
        notify_superadmins(
            connection,
            "Product created",
            f"An Admin added product {values['name']}.",
            url_for("admin_dashboard") + "#products",
            exclude_account_id=session.get("user_id"),
        )
    return redirect(url_for("admin_dashboard") + "#products")


@app.post("/admin/products/<slug>/update")
def admin_update_product(slug):
    require_staff()
    with database() as connection:
        existing = connection.execute(
            "SELECT image, icon FROM catalog_products WHERE slug = ?", (slug,)
        ).fetchone()
    if not existing:
        abort(404)
    image_file = request.files.get("image")
    values, error = _admin_product_values(
        request.form, image_file,
        existing_image=existing["image"],
        existing_icon=existing["icon"],
    )
    if error:
        flash(error, "error")
        return redirect(url_for("admin_dashboard") + "#products")
    if values["slug"] != slug:
        flash("Product slugs cannot be changed after creation.", "error")
        return redirect(url_for("admin_dashboard") + "#products")
    image_path = _save_admin_product_image(
        values["slug"], image_file, values["image_extension"]
    )
    with database() as connection:
        result = connection.execute(
            """UPDATE catalog_products SET name = ?, category = ?, description = ?,
            image = COALESCE(?, image), icon = ?,
            price = ?, old_price = ?, features_json = ?, show_in_catalog = ?, updated_at = ? WHERE slug = ?""",
            (values["name"], values["category"], values["description"], image_path,
             values["icon"], values["price"], values["old_price"], values["features_json"],
             values["show_in_catalog"], int(time.time()), slug),
        )
        if result.rowcount:
            connection.execute(
                "UPDATE product_inventory SET stock = ? WHERE product_slug = ?",
                (values["stock"], slug),
            )
    if not result.rowcount:
        abort(404)
    flash("Product details and stock updated.", "success")
    with database() as connection:
        notify_superadmins(
            connection,
            "Product updated",
            f"An Admin updated product {values['name']}.",
            url_for("admin_dashboard") + "#products",
            exclude_account_id=session.get("user_id"),
        )
        notify_auction_bidders(
            connection,
            slug,
            "Auction product updated",
            f"The product details for auction {slug} changed. Review the current listing.",
            url_for("auction_details", slug=slug),
        )
    return redirect(url_for("admin_dashboard") + "#products")


@app.post("/admin/products/<slug>/<action>")
def admin_set_product_status(slug, action):
    require_staff()
    if action not in ("archive", "restore"):
        abort(404)
    with database() as connection:
        result = connection.execute(
            "UPDATE catalog_products SET is_active = ?, updated_at = ? WHERE slug = ?",
            (0 if action == "archive" else 1, int(time.time()), slug),
        )
    if not result.rowcount:
        abort(404)
    flash("Product archived." if action == "archive" else "Product restored.", "success")
    with database() as connection:
        notify_superadmins(
            connection,
            "Product availability changed",
            f"An Admin {action}d product {slug}.",
            url_for("admin_dashboard") + "#products",
            exclude_account_id=session.get("user_id"),
        )
        notify_auction_bidders(
            connection,
            slug,
            "Auction product availability changed",
            f"The product status for auction {slug} changed. Check whether the auction is still available.",
            url_for("auctions_page"),
        )
    return redirect(url_for("admin_dashboard") + "#products")


@app.post("/admin/auctions/create")
def admin_create_auction():
    require_staff()
    existing_slug = request.form.get("product_slug", "").strip()
    if existing_slug and not request.form.get("slug"):
        try:
            starting_bid = int(request.form.get("starting_bid", ""))
            increment = int(request.form.get("minimum_increment", ""))
            duration = int(request.form.get("duration_days", ""))
        except ValueError:
            flash("Starting bid, bid increment, and duration must be whole numbers.", "error")
            return redirect(url_for("admin_dashboard") + "#auctions")
        if starting_bid < 1 or increment < 1 or not 1 <= duration <= 90:
            flash("Enter positive bid amounts and an auction duration from 1 to 90 days.", "error")
            return redirect(url_for("admin_dashboard") + "#auctions")
        if not get_product(existing_slug):
            flash("Choose an active product to auction.", "error")
            return redirect(url_for("admin_dashboard") + "#auctions")
        with database() as connection:
            try:
                connection.execute(
                    """INSERT INTO auctions
                    (slug, current_bid, ends_at, starting_bid, minimum_increment, is_active)
                    VALUES (?, ?, ?, ?, ?, 1)""",
                    (existing_slug, starting_bid, int(time.time()) + duration * 86400,
                     starting_bid, increment),
                )
            except sqlite3.IntegrityError:
                flash("This product already has an auction listing.", "error")
                return redirect(url_for("admin_dashboard") + "#auctions")
        flash("Auction published.", "success")
        with database() as connection:
            notify_superadmins(
                connection,
                "Auction created",
                f"An Admin created an auction for {existing_slug}.",
                url_for("admin_dashboard") + "#auctions",
                exclude_account_id=session.get("user_id"),
            )
        return redirect(url_for("admin_dashboard") + "#auctions")
    try:
        starting_bid = int(request.form.get("starting_bid", ""))
        increment = int(request.form.get("minimum_increment", ""))
        duration = int(request.form.get("duration_days", ""))
    except ValueError:
        flash("Starting bid, bid increment, and duration must be whole numbers.", "error")
        return redirect(url_for("admin_dashboard") + "#auctions")
    if starting_bid < 1 or increment < 1 or not 1 <= duration <= 90:
        flash("Enter positive bid amounts and an auction duration from 1 to 90 days.", "error")
        return redirect(url_for("admin_dashboard") + "#auctions")
    image_file = request.files.get("image")
    values, error = _admin_product_values(request.form, image_file)
    if error:
        flash(error, "error")
        return redirect(url_for("admin_dashboard") + "#auctions")
    image_path = _save_admin_product_image(
        values["slug"], image_file, values["image_extension"]
    )
    now = int(time.time())
    try:
        with database() as connection:
            connection.execute(
                """INSERT INTO catalog_products
                (slug, name, category, description, image, icon, price, old_price,
                 features_json, show_in_catalog, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (values["slug"], values["name"], values["category"], values["description"],
                 image_path, values["icon"], values["price"], values["old_price"],
                 values["features_json"], values["show_in_catalog"], now),
            )
            connection.execute(
                "INSERT INTO product_inventory (product_slug, stock) VALUES (?, ?)",
                (values["slug"], values["stock"]),
            )
            connection.execute(
                """INSERT INTO auctions
                (slug, current_bid, ends_at, starting_bid, minimum_increment, is_active)
                VALUES (?, ?, ?, ?, ?, 1)""",
                (values["slug"], starting_bid, now + duration * 86400, starting_bid, increment),
            )
    except sqlite3.IntegrityError:
        if image_path:
            (ROOT / "static" / image_path).unlink(missing_ok=True)
        flash("A product or auction with that slug already exists.", "error")
        return redirect(url_for("admin_dashboard") + "#auctions")
    flash("Auction published.", "success")
    with database() as connection:
        notify_superadmins(
            connection,
            "Auction created",
            f"An Admin created an auction for {values['name']}.",
            url_for("admin_dashboard") + "#auctions",
            exclude_account_id=session.get("user_id"),
        )
    return redirect(url_for("admin_dashboard") + "#auctions")


def _update_auction_product(slug):
    if not request.form.get("name"):
        return {}, None
    with database() as connection:
        existing = connection.execute(
            "SELECT image, icon FROM catalog_products WHERE slug = ?", (slug,)
        ).fetchone()
    if not existing:
        abort(404)
    image_file = request.files.get("image")
    values, error = _admin_product_values(
        request.form, image_file,
        existing_image=existing["image"],
        existing_icon=existing["icon"],
    )
    if error:
        flash(error, "error")
        return None
    if values["slug"] != slug:
        flash("Product slugs cannot be changed after creation.", "error")
        return None
    image_path = _save_admin_product_image(
        slug, image_file, values["image_extension"]
    )
    return values, image_path


def _save_auction_product_update(connection, slug, values, image_path):
    connection.execute(
        """UPDATE catalog_products SET name = ?, category = ?, description = ?,
        image = COALESCE(?, image), icon = ?, price = ?, old_price = ?,
        features_json = ?, show_in_catalog = ?, updated_at = ? WHERE slug = ?""",
        (values["name"], values["category"], values["description"], image_path,
         values["icon"], values["price"], values["old_price"], values["features_json"],
         values["show_in_catalog"], int(time.time()), slug),
    )
    connection.execute(
        "UPDATE product_inventory SET stock = ? WHERE product_slug = ?",
        (values["stock"], slug),
    )


@app.post("/admin/auctions/<slug>/close")
def admin_close_auction(slug):
    require_staff()
    with database() as connection:
        result = connection.execute(
            "UPDATE auctions SET is_active = 0 WHERE slug = ? AND is_active = 1",
            (slug,),
        )
    if not result.rowcount:
        flash("That auction is already closed or was not found.", "error")
    else:
        flash("Auction closed; its bid history has been preserved.", "success")
        with database() as connection:
            notify_superadmins(
                connection,
                "Auction closed",
                f"An Admin closed the auction for {slug}.",
                url_for("admin_dashboard") + "#auctions",
                exclude_account_id=session.get("user_id"),
            )
            notify_auction_bidders(
                connection,
                slug,
                "Auction closed",
                f"The auction for {slug} has been closed by the Admin.",
                url_for("auction_details", slug=slug),
            )
    return redirect(url_for("admin_dashboard") + "#auctions")


@app.post("/admin/auctions/<slug>/update")
def admin_update_auction(slug):
    require_staff()
    try:
        increment = int(request.form.get("minimum_increment", ""))
        duration = int(request.form.get("duration_days", ""))
    except ValueError:
        flash("Bid increment and duration must be whole numbers.", "error")
        return redirect(url_for("admin_dashboard") + "#auctions")
    if increment < 1 or not 1 <= duration <= 90:
        flash("Enter a positive bid increment and an auction duration from 1 to 90 days.", "error")
        return redirect(url_for("admin_dashboard") + "#auctions")
    product_update = _update_auction_product(slug)
    if product_update is None:
        return redirect(url_for("admin_dashboard") + "#auctions")
    values, image_path = product_update
    with database() as connection:
        result = connection.execute(
            "UPDATE auctions SET minimum_increment = ?, ends_at = ? WHERE slug = ? AND is_active = 1",
            (increment, int(time.time()) + duration * 86400, slug),
        )
        if result.rowcount and values:
            _save_auction_product_update(connection, slug, values, image_path)
    if not result.rowcount:
        if image_path:
            (ROOT / "static" / image_path).unlink(missing_ok=True)
        abort(404)
    flash(
        "Auction and product details updated." if values else "Auction details updated.",
        "success",
    )
    with database() as connection:
        notify_superadmins(
            connection,
            "Auction updated",
            f"An Admin updated the auction for {slug}.",
            url_for("admin_dashboard") + "#auctions",
            exclude_account_id=session.get("user_id"),
        )
        notify_auction_bidders(
            connection,
            slug,
            "Auction details changed",
            f"The auction details for {slug} have changed. Review the latest terms before bidding.",
            url_for("auction_details", slug=slug),
        )
    return redirect(url_for("admin_dashboard") + "#auctions")


@app.post("/admin/auctions/<slug>/reopen")
def admin_reopen_auction(slug):
    require_staff()
    try:
        duration = int(request.form.get("duration_days", ""))
    except ValueError:
        flash("Auction duration must be a whole number.", "error")
        return redirect(url_for("admin_dashboard") + "#auctions")
    if not 1 <= duration <= 90:
        flash("Enter an auction duration from 1 to 90 days.", "error")
        return redirect(url_for("admin_dashboard") + "#auctions")
    product_update = _update_auction_product(slug)
    if product_update is None:
        return redirect(url_for("admin_dashboard") + "#auctions")
    values, image_path = product_update
    with database() as connection:
        result = connection.execute(
            "UPDATE auctions SET is_active = 1, ends_at = ? WHERE slug = ? AND is_active = 0",
            (int(time.time()) + duration * 86400, slug),
        )
        if result.rowcount and values:
            _save_auction_product_update(connection, slug, values, image_path)
    if not result.rowcount:
        if image_path:
            (ROOT / "static" / image_path).unlink(missing_ok=True)
        flash("That auction is already active or was not found.", "error")
    else:
        flash(
            "Auction reopened and product details updated." if values
            else "Auction reopened with its bid history preserved.",
            "success",
        )
        with database() as connection:
            notify_superadmins(
                connection,
                "Auction reopened",
                f"An Admin reopened the auction for {slug}.",
                url_for("admin_dashboard") + "#auctions",
                exclude_account_id=session.get("user_id"),
            )
            notify_auction_bidders(
                connection,
                slug,
                "Auction reopened",
                f"The auction for {slug} has reopened and is accepting bids again.",
                url_for("auction_details", slug=slug),
            )
    return redirect(url_for("admin_dashboard") + "#auctions")


def _admin_offer_values(form, image_file, existing_image=None):
    name = form.get("name", "").strip()
    slug = form.get("slug", "").strip().lower()
    category = form.get("category", "").strip()
    product_description = form.get("product_description", "").strip()
    title = form.get("title", "").strip()
    description = form.get("description", "").strip()
    features = [part.strip() for part in form.get("features", "").split(",") if part.strip()]
    try:
        main_price = int(form.get("main_price", ""))
        offer_price = int(form.get("offer_price", ""))
        stock = int(form.get("stock", ""))
        ends_at = int(datetime.strptime(
            form.get("ends_at", "").strip(), "%Y-%m-%dT%H:%M"
        ).replace(tzinfo=timezone.utc).timestamp())
    except (TypeError, ValueError):
        return None, "Enter valid prices, stock, and an offer end date and time (UTC)."
    now = int(time.time())
    if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", slug) or len(slug) > 100:
        return None, "Use a product slug containing lowercase letters, numbers, and hyphens only."
    if not name or len(name) > 120 or not category or len(category) > 80:
        return None, "Enter a product name (up to 120 characters) and category (up to 80 characters)."
    if not product_description or len(product_description) > 1000:
        return None, "Enter a product description of up to 1,000 characters."
    if not title or len(title) > 120:
        return None, "Enter an offer title of up to 120 characters."
    if not description or len(description) > 500:
        return None, "Enter an offer description of up to 500 characters."
    if main_price < 2 or offer_price < 1 or offer_price >= main_price:
        return None, "The offer price must be positive and lower than the main price."
    if stock < 0 or stock > 1_000_000:
        return None, "Stock must be between 0 and 1,000,000."
    if len(features) > 8 or any(len(feature) > 120 for feature in features):
        return None, "Add at most 8 product features, each up to 120 characters."
    if not now < ends_at <= now + 365 * 86400:
        return None, "Offer end time must be in the next 365 days."
    if form.get("is_active", "1") not in ("0", "1"):
        return None, "Choose whether this offer is active or paused."
    image_extension = None
    if image_file and image_file.filename:
        safe_name = secure_filename(image_file.filename)
        if not safe_name:
            return None, "Choose a valid product image file."
        image_header = image_file.stream.read(12)
        image_file.stream.seek(0)
        if image_header.startswith(b"\x89PNG\r\n\x1a\n"):
            image_extension = "png"
        elif image_header.startswith(b"\xff\xd8\xff"):
            image_extension = "jpg"
        elif image_header.startswith(b"RIFF") and image_header[8:12] == b"WEBP":
            image_extension = "webp"
        else:
            return None, "Upload a valid PNG, JPEG, or WebP product image."
    elif not existing_image:
        return None, "Upload a product image (PNG, JPEG, or WebP)."
    with database() as connection:
        existing_product = connection.execute(
            "SELECT slug FROM catalog_products WHERE slug = ?", (slug,)
        ).fetchone()
    if existing_product and slug != form.get("existing_slug", ""):
        return None, "That product slug is already in use. Choose a different slug."
    return {
        "slug": slug,
        "name": name,
        "category": category,
        "product_description": product_description,
        "title": title,
        "description": description,
        "ends_at": ends_at,
        "is_active": int(form.get("is_active", "1")),
        "main_price": main_price,
        "offer_price": offer_price,
        "stock": stock,
        "features_json": json.dumps(features),
        "image_extension": image_extension,
    }, None


def _save_offer_image(slug, image_file, extension):
    if not image_file or not extension:
        return None
    upload_directory = ROOT / "static" / "uploads" / "offers"
    upload_directory.mkdir(parents=True, exist_ok=True)
    filename = f"{slug}-{secrets.token_hex(8)}.{extension}"
    image_file.save(upload_directory / filename)
    return f"uploads/offers/{filename}"


@app.post("/admin/offers/create")
def admin_create_offer():
    require_staff()
    image_file = request.files.get("image")
    values, error = _admin_offer_values(request.form, image_file)
    if error:
        flash(error, "error")
        return redirect(url_for("admin_dashboard") + "#offers")
    image_path = _save_offer_image(values["slug"], image_file, values["image_extension"])
    try:
        with database() as connection:
            connection.execute(
                """INSERT INTO catalog_products
                (slug, name, category, description, image, price, old_price, features_json,
                 is_active, show_in_catalog, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, 0, ?)""",
                (values["slug"], values["name"], values["category"], values["product_description"],
                 image_path, values["offer_price"], values["main_price"], values["features_json"],
                 int(time.time())),
            )
            connection.execute(
                "INSERT INTO product_inventory (product_slug, stock) VALUES (?, ?)",
                (values["slug"], values["stock"]),
            )
            connection.execute(
                "INSERT INTO offers (product_slug, title, description, ends_at, is_active) "
                "VALUES (?, ?, ?, ?, ?)",
                (values["slug"], values["title"], values["description"],
                 values["ends_at"], values["is_active"]),
            )
    except sqlite3.IntegrityError:
        if image_path:
            (ROOT / "static" / image_path).unlink(missing_ok=True)
        flash("That product slug is already in use. Choose a different slug.", "error")
        return redirect(url_for("admin_dashboard") + "#offers")
    flash("Offer product published.", "success")
    with database() as connection:
        notify_superadmins(
            connection,
            "Offer published",
            f"An Admin published the offer {values['title']}.",
            url_for("admin_dashboard") + "#offers",
            exclude_account_id=session.get("user_id"),
        )
    return redirect(url_for("admin_dashboard") + "#offers")


@app.post("/admin/offers/<int:offer_id>/update")
def admin_update_offer(offer_id):
    require_staff()
    with database() as connection:
        existing = connection.execute(
            "SELECT o.product_slug, p.image FROM offers AS o "
            "JOIN catalog_products AS p ON p.slug = o.product_slug WHERE o.id = ?",
            (offer_id,),
        ).fetchone()
    if not existing:
        abort(404)
    if request.form.get("slug", "").strip().lower() != existing["product_slug"]:
        flash("Product slugs cannot be changed after creation.", "error")
        return redirect(url_for("admin_dashboard") + "#offers")
    image_file = request.files.get("image")
    values, error = _admin_offer_values(
        request.form, image_file, existing_image=existing["image"]
    )
    if error:
        flash(error, "error")
        return redirect(url_for("admin_dashboard") + "#offers")
    image_path = _save_offer_image(values["slug"], image_file, values["image_extension"])
    with database() as connection:
        connection.execute(
            "UPDATE offers SET title = ?, description = ?, ends_at = ?, is_active = ? "
            "WHERE id = ?",
            (values["title"], values["description"], values["ends_at"],
             values["is_active"], offer_id),
        )
        connection.execute(
            """UPDATE catalog_products SET name = ?, category = ?, description = ?,
            image = COALESCE(?, image), price = ?, old_price = ?, features_json = ?,
            updated_at = ? WHERE slug = ?""",
            (values["name"], values["category"], values["product_description"], image_path,
             values["offer_price"], values["main_price"], values["features_json"],
             int(time.time()), values["slug"]),
        )
        connection.execute(
            "UPDATE product_inventory SET stock = ? WHERE product_slug = ?",
            (values["stock"], values["slug"]),
        )
    flash("Offer product updated.", "success")
    with database() as connection:
        notify_superadmins(
            connection,
            "Offer updated",
            f"An Admin updated the offer {values['title']}.",
            url_for("admin_dashboard") + "#offers",
            exclude_account_id=session.get("user_id"),
        )
    return redirect(url_for("admin_dashboard") + "#offers")


@app.post("/admin/offers/<slug>/delete")
def admin_delete_offer(slug):
    require_staff()
    with database() as connection:
        result = connection.execute(
            "UPDATE catalog_products SET is_active = 0, updated_at = ? WHERE slug = ? "
            "AND EXISTS (SELECT 1 FROM offers WHERE product_slug = ?)",
            (int(time.time()), slug, slug),
        )
        if result.rowcount:
            connection.execute("DELETE FROM offers WHERE product_slug = ?", (slug,))
    if not result.rowcount:
        abort(404)
    flash("Offer product archived; its order history was preserved.", "success")
    with database() as connection:
        notify_superadmins(
            connection,
            "Offer archived",
            f"An Admin archived the offer {slug}.",
            url_for("admin_dashboard") + "#offers",
            exclude_account_id=session.get("user_id"),
        )
    return redirect(url_for("admin_dashboard") + "#offers")


@app.post("/admin/orders/<int:order_id>/status")
def admin_update_order_status(order_id):
    require_staff()
    requested_status = request.form.get("order_status", "")
    transitions = {
        "confirmed": "processing",
        "processing": "shipped",
        "shipped": "delivered",
    }
    with database() as connection:
        order = connection.execute(
            "SELECT order_number, account_id, order_status, payment_method, payment_status "
            "FROM orders WHERE id = ?",
            (order_id,),
        ).fetchone()
        if not order:
            abort(404)
        allowed = transitions.get(order["order_status"])
        if not allowed or requested_status != allowed:
            flash("Orders must move one step at a time through the delivery workflow.", "error")
        elif order["payment_method"] != "cod" and order["payment_status"] != "paid":
            flash("An online order must be paid before fulfilment.", "error")
        else:
            connection.execute(
                "UPDATE orders SET order_status = ? WHERE id = ? AND order_status = ?",
                (requested_status, order_id, order["order_status"]),
            )
            create_notification(
                connection,
                order["account_id"],
                "Order status updated",
                f"Order {order['order_number']} is now {requested_status}.",
                url_for("my_orders_page", _anchor=f"order-{order['order_number']}"),
            )
            notify_superadmins(
                connection,
                "Order status updated",
                f"An Admin moved order {order['order_number']} to {requested_status}.",
                url_for("admin_dashboard") + "#orders",
                exclude_account_id=session.get("user_id"),
            )
            flash(f"Order moved to {requested_status}.", "success")
    return redirect(url_for("admin_dashboard") + "#orders")


@app.post("/superadmin/accounts/<int:account_id>/update")
def superadmin_update_account(account_id):
    superadmin_id = require_superadmin()
    if account_id == superadmin_id:
        flash("You cannot change your own Superadmin account here.", "error")
        return redirect(url_for("admin_dashboard") + "#accounts")
    action = request.form.get("action", "")
    if action not in ("make_admin", "make_user", "activate", "deactivate"):
        abort(400)
    with database() as connection:
        account = connection.execute(
            "SELECT role, is_active FROM accounts WHERE id = ?", (account_id,)
        ).fetchone()
        if not account:
            abort(404)
        if account["role"] == "superadmin":
            flash("Superadmin accounts cannot be changed from this screen.", "error")
        elif action == "make_admin":
            connection.execute("UPDATE accounts SET role = 'admin' WHERE id = ?", (account_id,))
            create_notification(
                connection,
                account_id,
                "Account role updated",
                "A Superadmin changed your account role to Admin.",
                url_for("profile_page"),
            )
            flash("Account role changed to Admin.", "success")
        elif action == "make_user":
            connection.execute("UPDATE accounts SET role = 'user' WHERE id = ?", (account_id,))
            create_notification(
                connection,
                account_id,
                "Account role updated",
                "A Superadmin changed your account role to User.",
                url_for("profile_page"),
            )
            flash("Account role changed to User.", "success")
        elif action == "activate":
            connection.execute("UPDATE accounts SET is_active = 1 WHERE id = ?", (account_id,))
            create_notification(
                connection,
                account_id,
                "Account activated",
                "A Superadmin reactivated your BidMart account.",
                url_for("profile_page"),
            )
            flash("Account activated.", "success")
        else:
            connection.execute("UPDATE accounts SET is_active = 0 WHERE id = ?", (account_id,))
            create_notification(
                connection,
                account_id,
                "Account deactivated",
                "A Superadmin deactivated your BidMart account. Contact support if you believe this is a mistake.",
                url_for("login_page"),
            )
            flash("Account deactivated.", "success")
        if account["role"] != "superadmin":
            notify_superadmins(
                connection,
                "Account access updated",
                f"A Superadmin applied the {action.replace('_', ' ')} action to account {account_id}.",
                url_for("admin_dashboard") + "#accounts",
                exclude_account_id=superadmin_id,
            )
    return redirect(url_for("admin_dashboard") + "#accounts")


@app.post("/superadmin/admin-requests/<int:account_id>/<action>")
def review_admin_request(account_id, action):
    superadmin_id = require_superadmin()
    if action not in ("approve", "reject"):
        abort(404)

    with database() as connection:
        request_row = connection.execute(
            "SELECT r.status, r.requested_role, a.role, a.is_verified FROM admin_role_requests AS r "
            "JOIN accounts AS a ON a.id = r.account_id WHERE r.account_id = ?",
            (account_id,),
        ).fetchone()
        if not request_row or request_row["status"] != "pending":
            flash("This Admin request is no longer pending.", "error")
        elif action == "approve" and request_row["role"] != "user":
            flash("Only a regular user account can be approved for an elevated role.", "error")
        else:
            status = "approved" if action == "approve" else "rejected"
            connection.execute(
                "UPDATE admin_role_requests SET status = ?, reviewed_at = ?, reviewed_by = ? "
                "WHERE account_id = ? AND status = 'pending'",
                (status, int(time.time()), superadmin_id, account_id),
            )
            if action == "approve":
                connection.execute(
                    "UPDATE accounts SET is_verified = 0, verification_token_hash = NULL, "
                    "verification_expires_at = NULL WHERE id = ? AND role = 'user'",
                    (account_id,),
                )
                flash(
                    "Request approved. The applicant can now request the email verification link "
                    "from their registration page.",
                    "success",
                )
                create_notification(
                    connection,
                    account_id,
                    "Access request approved",
                    "Your Admin access request was approved. Complete email verification to activate your role.",
                    url_for("registration_page"),
                )
            else:
                flash("Request rejected.", "success")
                create_notification(
                    connection,
                    account_id,
                    "Access request update",
                    "Your elevated access request was not approved. Contact BidMart support if you need help.",
                    url_for("registration_page"),
                )
            notify_superadmins(
                connection,
                "Elevated access request reviewed",
                f"A Superadmin {status} an elevated access request.",
                url_for("admin_role_requests_page"),
                exclude_account_id=superadmin_id,
            )
    return redirect(url_for("admin_role_requests_page"))


@app.post("/registration/send-verification")
def send_approved_role_verification():
    account_id = session.get("pending_role_request_account_id")
    if not account_id:
        flash("Submit an Admin or Superadmin registration request first.", "error")
        return redirect(url_for("registration_page"))

    with database() as connection:
        applicant = connection.execute(
            "SELECT a.email, a.is_verified, r.status "
            "FROM accounts AS a JOIN admin_role_requests AS r ON r.account_id = a.id "
            "WHERE a.id = ?",
            (account_id,),
        ).fetchone()
    if not applicant:
        session.pop("pending_role_request_account_id", None)
        flash("Registration request was not found. Please register again.", "error")
        return redirect(url_for("registration_page"))
    if applicant["status"] != "approved":
        flash("A Superadmin must approve your request before email verification.", "error")
        return redirect(url_for("registration_page"))
    if applicant["is_verified"]:
        flash("This email is already verified. You can log in.", "success")
        return redirect(url_for("registration_page"))

    try:
        issue_verification(applicant["email"])
    except Exception:
        logging.exception("Approved elevated-role verification email could not be sent")
        flash(
            "Verification email could not be sent. Check the SMTP settings and try again.",
            "error",
        )
    else:
        flash("Verification link sent. Check your email and open the link to activate your requested role.", "success")
    return redirect(url_for("registration_page"))


@app.post("/register")
def register():
    full_name = request.form.get("full_name", "").strip()
    email = request.form.get("email", "").strip().casefold()
    phone = request.form.get("phone", "").strip()
    role = request.form.get("role", "user")
    next_url = valid_login_next_url(request.form.get("next", ""))
    if not next_url:
        next_url = valid_login_next_url(session.get("login_next_url", ""))
    password = request.form.get("password", "")
    confirm_password = request.form.get("confirm_password", "")

    if role not in ("user", "admin"):
        flash("Public registration supports User accounts and Admin access requests only.", "error")
        return redirect(url_for("registration_page"))
    if not full_name or "@" not in email or len(password) < 8:
        flash("Enter a valid name and email, and a password of at least 8 characters.", "error")
        return redirect(url_for("registration_page"))
    if password != confirm_password:
        flash("Passwords do not match.", "error")
        return redirect(url_for("registration_page"))

    try:
        with database() as connection:
            result = connection.execute(
                "INSERT INTO accounts (full_name, email, phone, password_hash, role, created_at) "
                "VALUES (?, ?, ?, ?, 'user', ?)",
                (full_name, email, phone, generate_password_hash(password), int(time.time())),
            )
            if role in ("admin", "superadmin"):
                connection.execute(
                    "INSERT INTO admin_role_requests (account_id, requested_role, status, requested_at) "
                    "VALUES (?, ?, 'pending', ?)",
                    (result.lastrowid, role, int(time.time())),
                )
                notify_superadmins(
                    connection,
                    "Elevated access request",
                    f"A user submitted a request for {role.title()} access.",
                    url_for("admin_role_requests_page"),
                    created_at=int(time.time()),
                )
            else:
                notify_staff(
                    connection,
                    "New customer account",
                    "A new customer account was created and is awaiting email verification.",
                    url_for("admin_dashboard") + "#orders",
                    exclude_account_id=result.lastrowid,
                    created_at=int(time.time()),
                )
        if role in ("admin", "superadmin"):
            session["pending_role_request_account_id"] = result.lastrowid
        if role == "user":
            if next_url:
                session["login_next_url"] = next_url
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

    if role in ("admin", "superadmin"):
        flash(
            f"Your {role.title()} request was submitted. A Superadmin must approve it before "
            "you can request the email verification link.",
            "success",
        )
        return redirect(url_for("registration_page"))
    else:
        flash("Account created. Check your inbox for the verification link; it expires in 30 minutes.", "success")
    return redirect(url_for("login_page", next=next_url) if next_url else url_for("login_page"))


@app.post("/resend-verification")
def resend_verification():
    email = request.form.get("email", "").strip().casefold()
    smtp_settings = ("SMTP_USERNAME", "SMTP_PASSWORD", "SMTP_FROM")
    if not all(os.getenv(setting) for setting in smtp_settings):
        flash("Verification email is unavailable. Configure SMTP in .env, restart BidMart, then try again.", "error")
        return redirect(url_for("registration_page"))

    with database() as connection:
        account = connection.execute(
            "SELECT a.is_verified, r.status AS request_status "
            "FROM accounts AS a LEFT JOIN admin_role_requests AS r ON r.account_id = a.id "
            "WHERE a.email = ?",
            (email,),
        ).fetchone()
    if account and not account["is_verified"] and account["request_status"] in (None, "approved"):
        try:
            issue_verification(email)
        except Exception:
            logging.exception("Verification email resend failed")
    flash(
        "If that address has an eligible unverified BidMart account, check your inbox and spam folder for a "
        "verification link. Elevated-role requests must be approved before verification can be sent.",
        "success",
    )
    return redirect(url_for("registration_page"))


@app.get("/verify/<token>")
def verify_email(token):
    token_hash = hash_token(token)
    with database() as connection:
        account = connection.execute(
            "SELECT a.id, r.requested_role, r.status AS request_status "
            "FROM accounts AS a LEFT JOIN admin_role_requests AS r ON r.account_id = a.id "
            "WHERE a.verification_token_hash = ? AND a.verification_expires_at > ? "
            "AND a.is_verified = 0",
            (token_hash, int(time.time())),
        ).fetchone()
        if account and account["request_status"] == "pending":
            flash("A Superadmin must approve this elevated-role request before email verification.", "error")
            return redirect(url_for("login_page"))
        if account and account["request_status"] == "rejected":
            flash("This elevated-role request was rejected. Contact BidMart support for help.", "error")
            return redirect(url_for("login_page"))
        if account:
            connection.execute(
                "UPDATE accounts SET is_verified = 1, role = COALESCE(?, role), "
                "verification_token_hash = NULL, verification_expires_at = NULL "
                "WHERE id = ? AND is_verified = 0",
                (account["requested_role"], account["id"]),
            )
    if account:
        flash("Email verified. You can now log in.", "success")
    else:
        flash("That verification link is invalid, expired, or already used.", "error")
    next_url = valid_login_next_url(session.get("login_next_url", ""))
    return redirect(url_for("login_page", next=next_url) if next_url else url_for("login_page"))


@app.get("/login.html")
def login_page():
    next_url = valid_login_next_url(request.args.get("next", ""))
    if not next_url:
        next_url = valid_login_next_url(session.get("login_next_url", ""))
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
    next_url = valid_login_next_url(request.form.get("next", ""))
    if not next_url:
        next_url = valid_login_next_url(session.get("login_next_url", ""))
    with database() as connection:
        account = connection.execute(
            "SELECT id, email, full_name, password_hash, is_verified, role, is_active FROM accounts WHERE email = ?",
            (email,),
        ).fetchone()

    if (not account or not account["is_active"] or not account["is_verified"]
            or not check_password_hash(account["password_hash"], password)):
        flash("Login failed. Check your details and verify your email before signing in.", "error")
        return redirect(url_for("login_page", next=next_url) if next_url else url_for("login_page"))

    checkout_draft = session.get("checkout_draft")
    pending_cart_add = session.get("pending_cart_add")
    session.clear()
    session["user_id"] = account["id"]
    session["user_email"] = account["email"]
    session["user_name"] = account["full_name"]
    session["user_role"] = account["role"]
    if checkout_draft:
        session["checkout_draft"] = checkout_draft
    if pending_cart_add:
        session["pending_cart_add"] = pending_cart_add
        error = _save_cart_item(
            account["id"],
            pending_cart_add.get("slug", ""),
            pending_cart_add.get("quantity", 1),
            add_quantity=True,
        )
        session.pop("pending_cart_add", None)
        if error:
            flash(error, "error")
        else:
            flash("Product added to your cart.", "success")
    flash("You are logged in.", "success")
    return redirect(next_url or url_for("home"))


@app.post("/logout")
def logout():
    session.clear()
    flash("You have logged out.", "success")
    return redirect(url_for("home"))


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=int(os.getenv("PORT", "5000")), debug=False)
