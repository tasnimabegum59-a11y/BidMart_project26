import hashlib
import logging
import os
import secrets
import smtplib
import sqlite3
import time
from contextlib import contextmanager
from email.message import EmailMessage
from pathlib import Path
from urllib.parse import urljoin

from dotenv import load_dotenv
from flask import Flask, abort, flash, redirect, render_template, request, send_from_directory, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash


ROOT = Path(__file__).resolve().parent
INSTANCE = ROOT / "instance"
DATABASE = INSTANCE / "bidmart.sqlite3"
DEVELOPMENT_SECRET_FILE = INSTANCE / "flask-secret.key"
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


initialize_database()


@app.context_processor
def csrf_context():
    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_urlsafe(32)
    return {"csrf_token": session["csrf_token"]}


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
    return render_template("index.html", current_user_email=session.get("user_email"))


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
    return render_template("login.html")


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
    role = request.form.get("role", "user")
    with database() as connection:
        account = connection.execute(
            "SELECT id, email, password_hash, role, is_verified FROM accounts WHERE email = ?",
            (email,),
        ).fetchone()

    if (not account or role != account["role"] or not account["is_verified"]
            or not check_password_hash(account["password_hash"], password)):
        flash("Login failed. Check your details and verify your email before signing in.", "error")
        return redirect(url_for("login_page"))

    session.clear()
    session["user_id"] = account["id"]
    session["user_email"] = account["email"]
    flash("You are logged in.", "success")
    return redirect(url_for("home"))


@app.post("/logout")
def logout():
    session.clear()
    flash("You have logged out.", "success")
    return redirect(url_for("home"))


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=int(os.getenv("PORT", "5000")), debug=False)
