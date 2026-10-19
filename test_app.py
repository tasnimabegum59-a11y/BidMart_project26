import re
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch
from werkzeug.security import generate_password_hash

os.environ.setdefault("FLASK_SECRET_KEY", "test-only-secret-not-for-deployment")

import app as bidmart


class AuthenticationFlowTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database_path = Path(self.temp_dir.name) / "test.sqlite3"
        self.original_database = bidmart.DATABASE
        bidmart.DATABASE = self.database_path
        bidmart.initialize_database()
        bidmart.app.config.update(TESTING=True, SECRET_KEY="test-secret")
        self.client = bidmart.app.test_client()
        self.email = "flow-test@example.invalid"

    def tearDown(self):
        bidmart.DATABASE = self.original_database
        self.temp_dir.cleanup()

    def csrf_from(self, response):
        with self.client.session_transaction() as session:
            return session["csrf_token"]

    def start_checkout(self, slug="casual-sneakers", quantity="1"):
        products = self.client.get("/products")
        return self.client.post("/checkout/start", data={
            "csrf_token": self.csrf_from(products),
            "product_slug": slug,
            "quantity": quantity,
        })

    def checkout_form(self, csrf_token, **overrides):
        data = {
            "csrf_token": csrf_token,
            "customer_name": "Guest Buyer",
            "customer_email": "guest@example.invalid",
            "customer_phone": "01712345678",
            "division": "Dhaka",
            "district": "Dhanmondi",
            "address": "House 1, Road 2",
            "postal_code": "1205",
            "delivery_note": "",
            "coupon_code": "",
            "payment_method": "cod",
            "quantity": "1",
        }
        data.update(overrides)
        return data

    def test_registration_verification_and_login(self):
        with patch.object(bidmart, "send_verification_email") as send_email:
            response = self.client.get("/register.html")
            self.assertEqual(response.status_code, 200)
            csrf = self.csrf_from(response)
            response = self.client.post("/register", data={
                "csrf_token": csrf,
                "full_name": "Test Account",
                "email": self.email,
                "phone": "5550100",
                "role": "user",
                "password": "secure-test-password",
                "confirm_password": "secure-test-password",
            })
            self.assertEqual(response.status_code, 302)
            send_email.assert_called_once()
            token = send_email.call_args.args[1]

        with bidmart.database() as connection:
            account = connection.execute(
                "SELECT is_verified, verification_token_hash, password_hash FROM accounts WHERE email = ?",
                (self.email,),
            ).fetchone()
        self.assertEqual(account["is_verified"], 0)
        self.assertNotEqual(account["verification_token_hash"], token)
        self.assertNotEqual(account["password_hash"], "secure-test-password")

        response = self.client.get(f"/verify/{token}")
        self.assertEqual(response.status_code, 302)
        with bidmart.database() as connection:
            account = connection.execute(
                "SELECT is_verified, verification_token_hash FROM accounts WHERE email = ?",
                (self.email,),
            ).fetchone()
        self.assertEqual(account["is_verified"], 1)
        self.assertIsNone(account["verification_token_hash"])
        self.assertEqual(self.client.get(f"/verify/{token}").status_code, 302)

        response = self.client.get("/login.html")
        self.assertNotIn(b'name="role"', response.data)
        csrf = self.csrf_from(response)
        response = self.client.post("/login", data={
            "csrf_token": csrf,
            "email": self.email,
            "password": "secure-test-password",
        })
        self.assertEqual(response.status_code, 302)
        home = self.client.get("/")
        self.assertIn(b"Test Account", home.data)
        self.assertIn(b'/static/bidmart-logo.png', home.data)
        self.assertIn(b'/static/bidmart-favicon.png', home.data)
        self.assertIn(b'/static/hero-sale.png', home.data)
        self.assertIn(b'id="homeAuctionCountdown"', home.data)
        self.assertIn(b'data-ends-at=', home.data)
        self.assertIn(b'class="promo-auction-button" href="/auction/iphone-14-pro-max"', home.data)
        self.assertIn(b'class="promo-bid-prices"', home.data)
        self.assertIn(b'Up to', home.data)
        self.assertIn(b'40% OFF', home.data)
        self.assertIn(b'href="#products">Shop Now', home.data)
        self.assertEqual(home.data.count(b'class="promo-deal-product"'), 3)
        self.assertNotIn(b'src="/static/live-auction-card.png"', home.data)
        self.assertNotIn(b'src="/static/summer-savings-card.png"', home.data)
        self.assertIn(b'href="/auction/iphone-14-pro-max"', home.data)
        with bidmart.database() as connection:
            featured_auction = connection.execute(
                "SELECT current_bid, ends_at FROM auctions WHERE slug = ?",
                (bidmart.DEMO_AUCTION_SLUG,),
            ).fetchone()
        self.assertIn(f'data-ends-at="{featured_auction["ends_at"]}"'.encode(), home.data)
        self.assertIn(f'৳ {featured_auction["current_bid"]:,}'.encode(), home.data)
        self.assertLess(home.data.index(b'class="hero"'), home.data.index(b'class="promotional-cards"'))
        self.assertLess(home.data.index(b'class="promotional-cards"'), home.data.index(b'id="products"'))
        self.assertIn(b'class="container promotional-grid"', home.data)
        self.assertEqual(home.data.count(b'class="promotional-card '), 2)
        self.assertEqual(home.data.count(b'class="product-card"'), 6)
        self.assertEqual(home.data.count(b'data-buy-now'), 6)
        self.assertEqual(home.data.count(b'action="/checkout/start"'), 6)
        self.assertEqual(home.data.count(b'class="product-btn product-details-btn"'), 6)
        for product in bidmart.PRODUCT_CATALOG[:6]:
            self.assertIn(
                f'href="/products/{product["slug"]}" class="product-btn product-details-btn"'.encode(),
                home.data,
            )
        for product_name in (
            b"iPhone 14 Pro Max",
            b"Smart Watch",
            b"JBL Wireless Headphones",
            b"Casual Sneakers",
            b"Wireless Earbuds",
            b"Compact Digital Camera",
        ):
            self.assertIn(product_name, home.data)
        product_images = (
            "iphone-14-pro.png",
            "smart-watch.png",
            "jbl-headphones.png",
            "casual-sneakers.svg",
            "wireless-earbuds.svg",
            "digital-camera.svg",
        )
        for product_image in product_images:
            self.assertIn(f"/static/products/{product_image}".encode(), home.data)
            with self.client.get(f"/static/products/{product_image}") as image_response:
                self.assertEqual(image_response.status_code, 200, product_image)
        logo = self.client.get("/static/bidmart-logo.png")
        favicon = self.client.get("/static/bidmart-favicon.png")
        hero_image = self.client.get("/static/hero-sale.png")
        self.assertEqual(logo.status_code, 200)
        self.assertEqual(logo.mimetype, "image/png")
        self.assertEqual(favicon.status_code, 200)
        self.assertEqual(favicon.mimetype, "image/png")
        self.assertEqual(hero_image.status_code, 200)
        self.assertEqual(hero_image.mimetype, "image/png")
        logo.close()
        favicon.close()
        hero_image.close()
        self.assertIn(b'id="profileTrigger"', home.data)
        self.assertIn(b'aria-label="Open dashboard for Test Account"', home.data)
        self.assertLess(home.data.index(b'class="logo"'), home.data.index(b'class="profile-trigger"'))
        self.assertLess(home.data.index(b'class="profile-trigger"'), home.data.index(b'<nav class="nav-links" aria-label="Main navigation">'))
        self.assertLess(home.data.index(b'href="index.html" class="active" aria-current="page">Home'), home.data.index(b'href="/products">Products'))
        self.assertLess(home.data.index(b'href="/products">Products'), home.data.index(b'href="/auctions">Auctions'))
        self.assertLess(home.data.index(b'href="/auctions">Auctions'), home.data.index(b'href="#about">About'))
        self.assertIn(b"Personal Dashboard", home.data)
        self.assertIn(b"Logout", home.data)
        self.assertIn(b"Coming soon", home.data)
        self.assertIn(b'class="dashboard-logout-form"', home.data)
        self.assertNotIn(b'class="logout-form"', home.data)
        logout_response = self.client.post("/logout", data={
            "csrf_token": self.csrf_from(home),
        })
        self.assertEqual(logout_response.status_code, 302)
        self.assertNotIn(b'id="profileTrigger"', self.client.get("/").data)

    def test_products_page_shows_discounted_and_regular_price_items(self):
        response = self.client.get("/products")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"<h1>All Products</h1>", response.data)
        self.assertEqual(response.data.count(b'class="product-card"'), len(bidmart.PRODUCT_CATALOG))
        self.assertIn(b"26% OFF", response.data)
        self.assertEqual(response.data.count(b"REGULAR PRICE"), 3)
        self.assertEqual(
            response.data.count(b'class="product-btn product-details-btn"'),
            len(bidmart.PRODUCT_CATALOG),
        )
        self.assertEqual(response.data.count(b'data-buy-now'), len(bidmart.PRODUCT_CATALOG))
        self.assertEqual(response.data.count(b'name="product_slug"'), len(bidmart.PRODUCT_CATALOG))
        self.assertIn(b"IdeaPad Slim 3 Laptop", response.data)
        self.assertIn(b'aria-current="page">Products</a>', response.data)
        self.assertIn(b'href="/products">Products</a>', self.client.get("/").data)

    def test_product_details_pages_show_complete_demo_listing_information(self):
        for product in bidmart.PRODUCT_CATALOG:
            with self.subTest(slug=product["slug"]):
                response = self.client.get(f"/products/{product['slug']}")
                self.assertEqual(response.status_code, 200)
                self.assertIn(product["name"].encode(), response.data)
                self.assertIn(b"Product description", response.data)
                self.assertIn(b"Seller information", response.data)
                self.assertIn(b"Sample rating overview", response.data)
                self.assertIn(b"Related Products", response.data)
                self.assertIn(b"10 in stock", response.data)
                self.assertEqual(response.data.count(b'class="related-product-card"'), 4)

    def test_guest_cod_checkout_applies_server_coupon_and_confirms_order_once(self):
        start = self.start_checkout(quantity="2")
        self.assertEqual(start.status_code, 302)
        checkout = self.client.get("/checkout")
        self.assertEqual(checkout.status_code, 200)
        self.assertIn(b"continue as guest", checkout.data)
        self.assertIn(b"Standard variant", checkout.data)

        csrf = self.csrf_from(checkout)
        coupon = self.client.post("/checkout/apply-coupon", data={
            "csrf_token": csrf,
            "coupon_code": "SAVE50",
            "division": "Chattogram",
            "quantity": "2",
        })
        self.assertEqual(coupon.status_code, 200)
        self.assertEqual(coupon.json["discount"], 50)
        self.assertEqual(coupon.json["total"], 4070)

        response = self.client.post(
            "/checkout",
            data=self.checkout_form(
                csrf,
                quantity="2",
                coupon_code="SAVE50",
                division="Chattogram",
                price="1",
                total="1",
                delivery_fee="0",
                discount="999999",
            ),
        )
        self.assertEqual(response.status_code, 302)
        confirmation = self.client.get(response.headers["Location"])
        self.assertEqual(confirmation.status_code, 200)
        self.assertIn(b"Your order is confirmed", confirmation.data)
        self.assertIn(b"Payment status", confirmation.data)
        self.assertIn(b"Track order", confirmation.data)
        self.assertIn(b"Continue shopping", confirmation.data)
        self.assertIn(b"House 1, Road 2", confirmation.data)
        self.assertIn(b"Chattogram", confirmation.data)
        track_path = re.search(rb'href="(/orders/[^"]+/track/[^"]+)"', confirmation.data).group(1).decode()
        self.assertIn(b"ORDER TRACKING", self.client.get(track_path).data)

        with bidmart.database() as connection:
            order = connection.execute(
                "SELECT order_number, order_status, payment_status, subtotal, delivery_fee, discount, total "
                "FROM orders"
            ).fetchone()
            item = connection.execute("SELECT quantity, unit_price FROM order_items").fetchone()
            stock = connection.execute(
                "SELECT stock FROM product_inventory WHERE product_slug = 'casual-sneakers'"
            ).fetchone()["stock"]
        self.assertEqual(order["order_status"], "confirmed")
        self.assertEqual(order["payment_status"], "unpaid")
        self.assertEqual((order["subtotal"], order["delivery_fee"], order["discount"], order["total"]), (4000, 120, 50, 4070))
        self.assertEqual((item["quantity"], item["unit_price"]), (2, 2000))
        self.assertEqual(stock, 8)

        duplicate = self.client.post(
            "/checkout",
            data=self.checkout_form(csrf, quantity="2", coupon_code="SAVE50"),
        )
        self.assertEqual(duplicate.status_code, 302)
        with bidmart.database() as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM orders").fetchone()[0], 1)
            stock = connection.execute(
                "SELECT stock FROM product_inventory WHERE product_slug = 'casual-sneakers'"
            ).fetchone()["stock"]
        self.assertEqual(stock, 8)

    def test_online_checkout_is_pending_unpaid_and_never_claims_payment(self):
        self.start_checkout()
        checkout = self.client.get("/checkout")
        response = self.client.post(
            "/checkout",
            data=self.checkout_form(self.csrf_from(checkout), payment_method="bkash"),
        )
        self.assertEqual(response.status_code, 302)
        confirmation = self.client.get(response.headers["Location"])
        self.assertEqual(confirmation.status_code, 200)
        self.assertIn(b"gateway is not configured", confirmation.data)
        self.assertIn(b"Pending / Unpaid", confirmation.data)

        with bidmart.database() as connection:
            order = connection.execute(
                "SELECT order_status, payment_status, payment_method FROM orders"
            ).fetchone()
            stock = connection.execute(
                "SELECT stock FROM product_inventory WHERE product_slug = 'casual-sneakers'"
            ).fetchone()["stock"]
        self.assertEqual(tuple(order), ("pending", "unpaid", "bkash"))
        self.assertEqual(stock, 10)

    def test_checkout_rejects_invalid_shipping_quantity_and_coupon_without_order(self):
        self.start_checkout()
        checkout = self.client.get("/checkout")
        csrf = self.csrf_from(checkout)

        invalid_shipping = self.client.post(
            "/checkout",
            data=self.checkout_form(csrf, customer_phone="123", address=""),
        )
        self.assertEqual(invalid_shipping.status_code, 400)
        self.assertIn(b"Enter a valid Bangladesh mobile number", invalid_shipping.data)
        self.assertIn(b"Enter your full delivery address", invalid_shipping.data)

        invalid_quantity = self.client.post(
            "/checkout",
            data=self.checkout_form(csrf, quantity="0"),
        )
        self.assertEqual(invalid_quantity.status_code, 400)
        self.assertIn(b"Choose a quantity between 1 and 99", invalid_quantity.data)

        invalid_coupon = self.client.post("/checkout/apply-coupon", data={
            "csrf_token": csrf,
            "coupon_code": "NOTREAL",
            "division": "Dhaka",
            "quantity": "1",
        })
        self.assertEqual(invalid_coupon.status_code, 400)
        with bidmart.database() as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM orders").fetchone()[0], 0)

    def test_checkout_rejects_out_of_stock_product_and_unknown_order_tokens(self):
        with bidmart.database() as connection:
            connection.execute(
                "UPDATE product_inventory SET stock = 0 WHERE product_slug = 'casual-sneakers'"
            )
        products = self.client.get("/products")
        response = self.client.post("/checkout/start", data={
            "csrf_token": self.csrf_from(products),
            "product_slug": "casual-sneakers",
            "quantity": "1",
        })
        self.assertEqual(response.status_code, 302)
        product_page = self.client.get(response.headers["Location"])
        self.assertIn(b"Currently out of stock", product_page.data)
        self.assertEqual(self.client.get("/orders/BM-UNKNOWN/confirmation/not-a-token").status_code, 404)

    def test_login_preserves_checkout_and_prefills_saved_contact_details(self):
        with bidmart.database() as connection:
            connection.execute(
                "INSERT INTO accounts (full_name, email, phone, password_hash, role, is_verified, created_at) "
                "VALUES (?, ?, ?, ?, 'user', 1, ?)",
                ("Saved Buyer", self.email, "01712345678", generate_password_hash("secure-password"), 1),
            )
        self.start_checkout()
        login_page = self.client.get("/login.html?next=/checkout")
        self.assertIn(b'name="next" value="/checkout"', login_page.data)
        response = self.client.post("/login", data={
            "csrf_token": self.csrf_from(login_page),
            "next": "/checkout",
            "email": self.email,
            "password": "secure-password",
        })
        self.assertEqual(response.headers["Location"], "/checkout")
        checkout = self.client.get("/checkout")
        self.assertIn(b'value="Saved Buyer"', checkout.data)
        self.assertIn(b'value="flow-test@example.invalid"', checkout.data)
        self.assertIn(b'value="01712345678"', checkout.data)

    def test_unknown_product_detail_returns_not_found(self):
        response = self.client.get("/products/not-a-product")

        self.assertEqual(response.status_code, 404)

    def test_logged_in_navigation_header_is_shared_across_main_pages(self):
        with bidmart.database() as connection:
            cursor = connection.execute(
                "INSERT INTO accounts (full_name, email, phone, password_hash, role, is_verified, created_at) "
                "VALUES (?, ?, ?, ?, 'user', 1, ?)",
                ("Test Account", self.email, "", generate_password_hash("secure-password"), 1),
            )
        with self.client.session_transaction() as session:
            session["user_email"] = self.email
            session["user_name"] = "Test Account"
            session["user_id"] = cursor.lastrowid

        for path, active_link in (
            ("/", b'href="index.html" class="active" aria-current="page">Home</a>'),
            ("/products", b'href="/products" class="active" aria-current="page">Products</a>'),
            ("/auctions", b'href="/auctions" class="active" aria-current="page">Auctions</a>'),
            ("/auction/iphone-14-pro-max", b'href="/auctions" class="active" aria-current="page">Auctions</a>'),
        ):
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 200)
                self.assertIn(b'class="container navbar"', response.data)
                self.assertIn(b'id="profileTrigger"', response.data)
                self.assertIn(b'aria-label="Open dashboard for Test Account"', response.data)
                self.assertIn(active_link, response.data)
                self.assertIn(b'class="dashboard-overlay" id="dashboardDrawer"', response.data)

    def test_account_pages_use_the_shared_navigation(self):
        for path in ("/login.html", "/register.html", "/forgot-password"):
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 200)
                self.assertIn(b'class="container navbar"', response.data)
                self.assertIn(b'<nav class="nav-links" aria-label="Main navigation">', response.data)
                self.assertIn(b'href="/auctions">Auctions</a>', response.data)

    def test_unverified_account_cannot_login(self):
        with patch.object(bidmart, "send_verification_email"):
            response = self.client.get("/register.html")
            self.client.post("/register", data={
                "csrf_token": self.csrf_from(response),
                "full_name": "Unverified Account",
                "email": self.email,
                "phone": "5550100",
                "role": "user",
                "password": "secure-test-password",
                "confirm_password": "secure-test-password",
            })

        response = self.client.get("/login.html")
        login_response = self.client.post("/login", data={
            "csrf_token": self.csrf_from(response),
            "email": self.email,
            "password": "secure-test-password",
        })
        self.assertEqual(login_response.status_code, 302)
        with self.client.session_transaction() as session:
            self.assertNotIn("user_id", session)

    def test_privileged_registration_is_rejected(self):
        response = self.client.get("/register.html")
        post_response = self.client.post("/register", data={
            "csrf_token": self.csrf_from(response),
            "full_name": "Admin Applicant",
            "email": self.email,
            "phone": "5550100",
            "role": "admin",
            "password": "secure-test-password",
            "confirm_password": "secure-test-password",
        })
        self.assertEqual(post_response.status_code, 302)
        with bidmart.database() as connection:
            account_count = connection.execute("SELECT COUNT(*) FROM accounts").fetchone()[0]
        self.assertEqual(account_count, 0)

    def test_provisioned_admin_can_log_in_with_privileged_role(self):
        with bidmart.database() as connection:
            connection.execute(
                "INSERT INTO accounts (full_name, email, phone, password_hash, role, is_verified, created_at) "
                "VALUES (?, ?, ?, ?, 'admin', 1, ?)",
                ("Admin Account", self.email, "", generate_password_hash("secure-admin-password"), 1),
            )

        login_page = self.client.get("/login.html")
        login_response = self.client.post("/login", data={
            "csrf_token": self.csrf_from(login_page),
            "email": self.email,
            "password": "secure-admin-password",
        })
        self.assertIn(login_response.headers["Location"], ("/", "/index.html"))
        with self.client.session_transaction() as session:
            self.assertEqual(session["user_email"], self.email)

    def test_registration_does_not_require_phone_number(self):
        with patch.object(bidmart, "send_verification_email") as send_email:
            response = self.client.get("/register.html")
            post_response = self.client.post("/register", data={
                "csrf_token": self.csrf_from(response),
                "full_name": "No Phone Account",
                "email": self.email,
                "role": "user",
                "password": "secure-test-password",
                "confirm_password": "secure-test-password",
            })

        self.assertEqual(post_response.status_code, 302)
        send_email.assert_called_once()
        with bidmart.database() as connection:
            account = connection.execute(
                "SELECT phone FROM accounts WHERE email = ?", (self.email,)
            ).fetchone()
        self.assertEqual(account["phone"], "")

    def test_expired_csrf_token_redirects_to_registration_form(self):
        response = self.client.post("/register", data={"csrf_token": "stale-token"})
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.headers["Location"].endswith("/register.html"))
        page = self.client.get(response.headers["Location"])
        self.assertIn(b"Your form session expired", page.data)

    def test_failed_resend_does_not_claim_verification_link_was_sent(self):
        with bidmart.database() as connection:
            connection.execute(
                "INSERT INTO accounts (full_name, email, phone, password_hash, role, created_at) "
                "VALUES (?, ?, ?, ?, 'user', ?)",
                ("Unverified Account", self.email, "", "test-hash", 1),
            )

        response = self.client.get("/register.html")
        with patch.dict(os.environ, {
            "SMTP_USERNAME": "sender@example.invalid",
            "SMTP_PASSWORD": "test-password",
            "SMTP_FROM": "sender@example.invalid",
        }), patch.object(bidmart, "issue_verification", side_effect=RuntimeError("SMTP login failed")):
            post_response = self.client.post("/resend-verification", data={
                "csrf_token": self.csrf_from(response),
                "email": self.email,
            })

        page = self.client.get(post_response.headers["Location"])
        self.assertIn(b"check your inbox and spam folder", page.data)
        self.assertIn(b"check the SMTP settings and the app&#39;s server log", page.data)
        self.assertNotIn(b"a new link has been sent", page.data)

    def test_password_reset_email_changes_password_and_consumes_token(self):
        with bidmart.database() as connection:
            connection.execute(
                "INSERT INTO accounts (full_name, email, phone, password_hash, role, is_verified, created_at) "
                "VALUES (?, ?, ?, ?, 'user', 1, ?)",
                ("Reset Account", self.email, "", generate_password_hash("old-password"), 1),
            )

        with patch.object(bidmart, "send_password_reset_email") as send_email:
            response = self.client.get("/forgot-password")
            self.assertEqual(response.status_code, 200)
            post_response = self.client.post("/forgot-password", data={
                "csrf_token": self.csrf_from(response),
                "email": self.email,
            })
            send_email.assert_called_once()
            token = send_email.call_args.args[1]
        self.assertEqual(post_response.status_code, 302)

        reset_page = self.client.get(f"/reset-password/{token}")
        self.assertEqual(reset_page.status_code, 200)
        self.assertIn(b'href="/style.css"', reset_page.data)
        stylesheet = self.client.get("/style.css")
        self.assertEqual(stylesheet.status_code, 200)
        self.assertEqual(stylesheet.mimetype, "text/css")
        stylesheet.close()
        reset_response = self.client.post(f"/reset-password/{token}", data={
            "csrf_token": self.csrf_from(reset_page),
            "password": "new-secure-password",
            "confirm_password": "new-secure-password",
        })
        self.assertTrue(reset_response.headers["Location"].endswith("/login.html"))
        self.assertEqual(self.client.get(f"/reset-password/{token}").headers["Location"], "/forgot-password")

        login_page = self.client.get("/login.html")
        login_response = self.client.post("/login", data={
            "csrf_token": self.csrf_from(login_page),
            "email": self.email,
            "password": "new-secure-password",
        })
        self.assertIn(login_response.headers["Location"], ("/", "/index.html"))
        with self.client.session_transaction() as session:
            self.assertEqual(session["user_email"], self.email)

    def test_password_reset_does_not_disclose_unknown_email(self):
        with patch.object(bidmart, "send_password_reset_email") as send_email:
            response = self.client.get("/forgot-password")
            post_response = self.client.post("/forgot-password", data={
                "csrf_token": self.csrf_from(response),
                "email": self.email,
            })
        send_email.assert_not_called()
        page = self.client.get(post_response.headers["Location"])
        self.assertIn(b"If an account exists for that email", page.data)


class AuctionFlowTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.original_database = bidmart.DATABASE
        bidmart.DATABASE = Path(self.temp_dir.name) / "auction-test.sqlite3"
        bidmart.initialize_database()
        bidmart.app.config.update(TESTING=True, SECRET_KEY="auction-test-secret")
        self.client = bidmart.app.test_client()
        self.auction_url = "/auction/iphone-14-pro-max"

    def tearDown(self):
        bidmart.DATABASE = self.original_database
        self.temp_dir.cleanup()

    def csrf_from(self, response):
        with self.client.session_transaction() as session:
            return session["csrf_token"]

    def add_logged_in_bidder(self):
        with bidmart.database() as connection:
            cursor = connection.execute(
                "INSERT INTO accounts (full_name, email, phone, password_hash, role, is_verified, created_at) "
                "VALUES (?, ?, ?, ?, 'user', 1, ?)",
                ("Bidding Buyer", "buyer@example.invalid", "", generate_password_hash("secure-password"), 1),
            )
        with self.client.session_transaction() as session:
            session["user_id"] = cursor.lastrowid
            session["user_email"] = "buyer@example.invalid"
            session["user_name"] = "Bidding Buyer"

    def test_auction_details_show_buyer_information_and_homepage_link(self):
        homepage = self.client.get("/")
        self.assertIn(b'href="/auction/iphone-14-pro-max"', homepage.data)

        response = self.client.get(self.auction_url)
        self.assertEqual(response.status_code, 200)
        for detail in (
            b"iPhone 14 Pro Max (256GB)",
            b"Current highest bid",
            b"Next minimum bid",
            b"Condition",
            b"Seller",
            b"Delivery and returns",
            b"Know before you bid",
            b"Recent bid history",
            b"Demo auction",
        ):
            self.assertIn(detail, response.data)
        self.assertIn(b"Login to Bid", response.data)
        self.assertNotIn(b'name="bid_amount"', response.data)

    def test_auctions_page_shows_product_details_prices_timers_and_bid_links(self):
        response = self.client.get("/auctions")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data.count(b'class="auction-list-card'), len(bidmart.AUCTION_LISTINGS))
        self.assertEqual(response.data.count(b'class="auction-card-bid"'), len(bidmart.AUCTION_LISTINGS))
        self.assertIn(b"Original price", response.data)
        self.assertIn(b"Current bid", response.data)
        self.assertIn(b"Time left:", response.data)
        self.assertIn(b"Wireless Earbuds", response.data)
        self.assertIn(b"DEMO AUCTION", response.data)
        self.assertIn(b'href="/auctions" class="active" aria-current="page">Auctions</a>', response.data)

    def test_non_featured_auction_can_open_details_and_accept_a_bid(self):
        self.add_logged_in_bidder()
        slug = "smart-watch-bluetooth"
        detail_url = f"/auction/{slug}"

        details = self.client.get(detail_url)
        self.assertEqual(details.status_code, 200)
        self.assertIn(b"Smart Watch (Bluetooth Calling)", details.data)
        self.assertIn("৳ 4,000".encode(), details.data)

        response = self.client.post(f"{detail_url}/bid", data={
            "csrf_token": self.csrf_from(details),
            "bid_amount": "2300",
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.headers["Location"], detail_url)
        self.assertIn(
            "Your bid of ৳ 2,300 was placed successfully.".encode(),
            self.client.get(detail_url).data,
        )

    def test_guest_is_sent_to_login_before_bidding(self):
        with bidmart.database() as connection:
            connection.execute(
                "INSERT INTO accounts (full_name, email, phone, password_hash, role, is_verified, created_at) "
                "VALUES (?, ?, ?, ?, 'user', 1, ?)",
                ("Verified Buyer", "verified@example.invalid", "", generate_password_hash("secure-password"), 1),
            )
        details = self.client.get(self.auction_url)
        response = self.client.post(f"{self.auction_url}/bid", data={
            "csrf_token": self.csrf_from(details),
            "bid_amount": "93000",
        })
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.headers["Location"].startswith("/login.html?next="))

        login_page = self.client.get(response.headers["Location"])
        self.assertIn(b'name="next" value="/auction/iphone-14-pro-max"', login_page.data)
        login_response = self.client.post("/login", data={
            "csrf_token": self.csrf_from(login_page),
            "next": "/auction/iphone-14-pro-max",
            "email": "verified@example.invalid",
            "password": "secure-password",
        })
        self.assertEqual(login_response.headers["Location"], self.auction_url)
        self.assertIn(b'name="bid_amount"', self.client.get(self.auction_url).data)

    def test_logged_in_user_can_place_a_valid_bid(self):
        self.add_logged_in_bidder()
        details = self.client.get(self.auction_url)
        response = self.client.post(f"{self.auction_url}/bid", data={
            "csrf_token": self.csrf_from(details),
            "bid_amount": "93000",
        })
        self.assertEqual(response.headers["Location"], self.auction_url)

        updated = self.client.get(self.auction_url)
        self.assertIn("Your bid of ৳ 93,000 was placed successfully.".encode(), updated.data)
        self.assertIn("৳ 93,000".encode(), updated.data)
        self.assertIn(b"B*** B***", updated.data)
        with bidmart.database() as connection:
            bid_count = connection.execute("SELECT COUNT(*) FROM auction_bids").fetchone()[0]
        self.assertEqual(bid_count, 1)

    def test_bid_below_minimum_is_rejected_without_changing_current_bid(self):
        self.add_logged_in_bidder()
        details = self.client.get(self.auction_url)
        response = self.client.post(f"{self.auction_url}/bid", data={
            "csrf_token": self.csrf_from(details),
            "bid_amount": "92999",
        })
        self.assertEqual(response.headers["Location"], self.auction_url)
        page = self.client.get(self.auction_url)
        self.assertIn(b"Your bid must be at least", page.data)
        self.assertIn("৳ 92,500".encode(), page.data)
        with bidmart.database() as connection:
            bid_count = connection.execute("SELECT COUNT(*) FROM auction_bids").fetchone()[0]
        self.assertEqual(bid_count, 0)

    def test_ended_auction_rejects_a_bid(self):
        self.add_logged_in_bidder()
        with bidmart.database() as connection:
            connection.execute(
                "UPDATE auctions SET ends_at = ? WHERE slug = ?",
                (int(time.time()) - 1, bidmart.DEMO_AUCTION_SLUG),
            )
        details = self.client.get(self.auction_url)
        self.assertIn(b"This auction has ended", details.data)
        response = self.client.post(f"{self.auction_url}/bid", data={
            "csrf_token": self.csrf_from(details),
            "bid_amount": "93000",
        })
        self.assertEqual(response.headers["Location"], self.auction_url)
        self.assertIn(b"no longer accepting bids", self.client.get(self.auction_url).data)


if __name__ == "__main__":
    unittest.main()
