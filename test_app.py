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

    def test_initial_superadmin_can_only_be_bootstrapped_once(self):
        bidmart.create_initial_superadmin(" First Admin ", "ROOT@example.invalid", "secure-root-password")

        with bidmart.database() as connection:
            account = connection.execute(
                "SELECT full_name, email, role, is_verified, password_hash FROM accounts"
            ).fetchone()
        self.assertEqual(account["full_name"], "First Admin")
        self.assertEqual(account["email"], "root@example.invalid")
        self.assertEqual(account["role"], "superadmin")
        self.assertEqual(account["is_verified"], 1)
        self.assertNotEqual(account["password_hash"], "secure-root-password")
        with self.assertRaisesRegex(ValueError, "A Superadmin already exists"):
            bidmart.create_initial_superadmin(
                "Second Admin", "second-root@example.invalid", "secure-root-password"
            )

    def test_initial_superadmin_bootstrap_upgrades_existing_verified_user(self):
        with bidmart.database() as connection:
            connection.execute(
                "INSERT INTO accounts (full_name, email, phone, password_hash, role, is_verified, created_at) "
                "VALUES (?, ?, '', ?, 'user', 1, ?)",
                ("Existing User", self.email, generate_password_hash("current-user-password"), 1),
            )

        with self.assertRaisesRegex(ValueError, "password does not match"):
            bidmart.create_initial_superadmin(
                "Existing User", self.email, "incorrect-current-password"
            )
        with bidmart.database() as connection:
            role = connection.execute(
                "SELECT role FROM accounts WHERE email = ?", (self.email,)
            ).fetchone()["role"]
        self.assertEqual(role, "user")

        result = bidmart.create_initial_superadmin(
            "Existing User", self.email, "current-user-password"
        )
        self.assertEqual(result, "upgraded")
        with bidmart.database() as connection:
            account = connection.execute(
                "SELECT role, password_hash FROM accounts WHERE email = ?", (self.email,)
            ).fetchone()
        self.assertEqual(account["role"], "superadmin")
        self.assertTrue(bidmart.check_password_hash(account["password_hash"], "current-user-password"))

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
        self.assertEqual(self.client.get("/superadmin/admin-requests").status_code, 403)
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
        self.assertIn(b'href="/offers">Shop Offers', home.data)
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
        self.assertNotIn(b"Manage products", response.data)
        self.assertNotIn(b"Manage this product", response.data)

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

    def test_online_checkout_is_blocked_until_sslcommerz_is_configured(self):
        self.start_checkout()
        checkout = self.client.get("/checkout")
        response = self.client.post(
            "/checkout",
            data=self.checkout_form(self.csrf_from(checkout), payment_method="card"),
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn(b"Online payment is not configured yet", response.data)

        with bidmart.database() as connection:
            order_count = connection.execute("SELECT COUNT(*) FROM orders").fetchone()[0]
            stock = connection.execute(
                "SELECT stock FROM product_inventory WHERE product_slug = 'casual-sneakers'"
            ).fetchone()["stock"]
        self.assertEqual(order_count, 0)
        self.assertEqual(stock, 10)

    def test_sslcommerz_checkout_verifies_callback_before_marking_paid(self):
        self.start_checkout()
        checkout = self.client.get("/checkout")
        csrf = self.csrf_from(checkout)
        with patch.dict(os.environ, {
            "APP_BASE_URL": "https://shop.example.invalid",
            "SSLCOMMERZ_STORE_ID": "test-store",
            "SSLCOMMERZ_STORE_PASSWORD": "test-password",
            "SSLCOMMERZ_IS_SANDBOX": "true",
        }), patch.object(
            bidmart, "initiate_sslcommerz_payment", return_value="https://sandbox.sslcommerz.com/gwprocess/test"
        ) as initiate_payment:
            response = self.client.post(
                "/checkout",
                data=self.checkout_form(csrf, payment_method="card"),
            )
            self.assertEqual(response.status_code, 302)
            self.assertEqual(
                response.headers["Location"],
                "https://sandbox.sslcommerz.com/gwprocess/test",
            )
            initiate_payment.assert_called_once()
            with bidmart.database() as connection:
                order = connection.execute(
                    "SELECT id, order_number, order_status, payment_status, stock_reserved FROM orders"
                ).fetchone()
                stock = connection.execute(
                    "SELECT stock FROM product_inventory WHERE product_slug = 'casual-sneakers'"
                ).fetchone()["stock"]
            self.assertEqual(tuple(order)[2:], ("pending", "unpaid", 1))
            self.assertEqual(stock, 9)

            with patch.object(bidmart, "validate_sslcommerz_payment", return_value=True):
                callback = self.client.post(
                    "/payment/sslcommerz/success",
                    data={"tran_id": order["order_number"], "val_id": "validated-test-token"},
                )
            self.assertEqual(callback.status_code, 302)
            result = self.client.get(callback.headers["Location"])
            self.assertIn(b"Payment verified", result.data)

        with bidmart.database() as connection:
            order = connection.execute(
                "SELECT order_status, payment_status, stock_reserved FROM orders"
            ).fetchone()
        self.assertEqual(tuple(order), ("confirmed", "paid", 0))

    def test_sslcommerz_validation_checks_transaction_amount_currency_and_risk(self):
        order = {"order_number": "BM-0123456789ABCDEF", "total": 2170}
        valid_response = {
            "status": "VALID",
            "tran_id": order["order_number"],
            "amount": "2170.00",
            "currency": "BDT",
            "risk_level": "0",
        }
        with patch.dict(os.environ, {
            "APP_BASE_URL": "https://shop.example.invalid",
            "SSLCOMMERZ_STORE_ID": "test-store",
            "SSLCOMMERZ_STORE_PASSWORD": "test-password",
        }), patch.object(bidmart, "sslcommerz_api_request", return_value=valid_response) as api_request:
            self.assertTrue(bidmart.validate_sslcommerz_payment(order, "test-validation-id"))
            self.assertEqual(api_request.call_args.kwargs["method"], "GET")
            api_request.return_value = {**valid_response, "amount": "1.00"}
            self.assertFalse(bidmart.validate_sslcommerz_payment(order, "wrong-amount"))
            api_request.return_value = {**valid_response, "risk_level": "1"}
            self.assertFalse(bidmart.validate_sslcommerz_payment(order, "risky-payment"))

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
                self.assertIn(b'class="profile-trigger-role">User</span>', response.data)
                self.assertNotIn(b'class="superadmin-notifications"', response.data)
                self.assertIn(b'aria-label="Open dashboard for Test Account"', response.data)
                self.assertIn(active_link, response.data)
                self.assertIn(b'class="dashboard-overlay" id="dashboardDrawer"', response.data)

    def test_superadmin_header_shows_pending_access_request_notification(self):
        with bidmart.database() as connection:
            superadmin = connection.execute(
                "INSERT INTO accounts (full_name, email, phone, password_hash, role, is_verified, created_at) "
                "VALUES (?, ?, '', ?, 'superadmin', 1, ?)",
                ("Root Account", self.email, generate_password_hash("secure-password"), 1),
            )
            for index, requested_role in enumerate(("admin", "superadmin")):
                applicant = connection.execute(
                    "INSERT INTO accounts (full_name, email, phone, password_hash, role, is_verified, created_at) "
                    "VALUES (?, ?, '', ?, 'user', 1, ?)",
                    (f"Applicant {index}", f"applicant{index}@example.invalid",
                     generate_password_hash("secure-password"), 1),
                )
                connection.execute(
                    "INSERT INTO admin_role_requests (account_id, requested_role, status, requested_at) "
                    "VALUES (?, ?, 'pending', ?)",
                    (applicant.lastrowid, requested_role, 1),
                )
        with self.client.session_transaction() as session:
            session["user_id"] = superadmin.lastrowid
            session["user_email"] = self.email
            session["user_name"] = "Root Account"

        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'class="profile-trigger-role">Superadmin</span>', response.data)
        self.assertIn(b'aria-label="2 pending access requests"', response.data)
        self.assertIn(b'class="notification-count" aria-hidden="true">2</span>', response.data)
        self.assertIn(b'Superadmin Dashboard', response.data)
        self.assertIn(b'Access requests', response.data)
        self.assertIn(b'2 pending', response.data)

    def test_account_pages_use_the_shared_navigation(self):
        for path in ("/login.html", "/register.html", "/forgot-password"):
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 200)
                self.assertIn(b'class="container navbar"', response.data)
                self.assertIn(b'<nav class="nav-links" aria-label="Main navigation">', response.data)
                self.assertIn(b'href="/auctions">Auctions</a>', response.data)

    def test_admin_dashboard_manages_products_inventory_and_auctions(self):
        with bidmart.database() as connection:
            admin = connection.execute(
                "INSERT INTO accounts (full_name, email, phone, password_hash, role, is_verified, created_at) "
                "VALUES (?, ?, '', ?, 'admin', 1, ?)",
                ("Store Admin", self.email, generate_password_hash("secure-password"), 1),
            )
        with self.client.session_transaction() as session:
            session["user_id"] = admin.lastrowid
            session["user_email"] = self.email
            session["user_name"] = "Store Admin"

        dashboard = self.client.get("/admin/dashboard")
        self.assertEqual(dashboard.status_code, 200)
        self.assertIn(b"Products & inventory", dashboard.data)
        self.assertNotIn(b'id="accounts"', dashboard.data)
        self.assertNotIn(b"My Products", dashboard.data)
        self.assertNotIn(b"My Orders", dashboard.data)
        product_catalog = self.client.get("/products")
        self.assertIn(b"Manage products", product_catalog.data)
        self.assertIn(b"Manage this product", product_catalog.data)
        self.assertIn(b"#product-casual-sneakers", product_catalog.data)
        auction_catalog = self.client.get("/auctions")
        self.assertIn(b"Manage auctions", auction_catalog.data)
        self.assertIn(b"Close auction", auction_catalog.data)
        offers_page = self.client.get("/offers")
        self.assertEqual(offers_page.status_code, 200)
        self.assertIn(b"Special Offers", offers_page.data)
        self.assertIn(b"JBL Headphones", offers_page.data)
        self.assertIn(b'href="/offers"', self.client.get("/").data)
        csrf = self.csrf_from(dashboard)
        product_values = {
            "csrf_token": csrf,
            "name": "Test Desk Light",
            "slug": "test-desk-light",
            "category": "Home",
            "description": "A test product for dashboard management.",
            "image": "products/digital-camera.svg",
            "icon": "",
            "price": "1500",
            "old_price": "1800",
            "stock": "5",
            "features": "Compact, Bright",
        }
        created = self.client.post("/admin/products/create", data=product_values)
        self.assertEqual(created.status_code, 302)
        self.assertIn(b"Test Desk Light", self.client.get("/products").data)

        update_values = {**product_values, "price": "1400", "stock": "4"}
        updated = self.client.post("/admin/products/test-desk-light/update", data=update_values)
        self.assertEqual(updated.status_code, 302)
        self.assertEqual(bidmart.get_product("test-desk-light")["price"], 1400)
        with bidmart.database() as connection:
            stock = connection.execute(
                "SELECT stock FROM product_inventory WHERE product_slug = 'test-desk-light'"
            ).fetchone()["stock"]
        self.assertEqual(stock, 4)

        offer_end = time.strftime("%Y-%m-%dT%H:%M", time.gmtime(time.time() + 86400))
        created_offer = self.client.post("/admin/offers/create", data={
            "csrf_token": csrf,
            "product_slug": "test-desk-light",
            "title": "Desk light launch deal",
            "description": "A limited-time test offer.",
            "ends_at": offer_end,
            "is_active": "1",
        })
        self.assertEqual(created_offer.status_code, 302)
        self.assertIn(b"Desk light launch deal", self.client.get("/offers").data)
        with bidmart.database() as connection:
            offer_id = connection.execute(
                "SELECT id FROM offers WHERE product_slug = 'test-desk-light'"
            ).fetchone()["id"]
        updated_offer = self.client.post(
            f"/admin/offers/{offer_id}/update",
            data={
                "csrf_token": csrf,
                "product_slug": "test-desk-light",
                "title": "Updated desk light deal",
                "description": "Updated offer description.",
                "ends_at": offer_end,
                "is_active": "0",
            },
        )
        self.assertEqual(updated_offer.status_code, 302)
        self.assertNotIn(b"Updated desk light deal", self.client.get("/offers").data)
        deleted_offer = self.client.post(
            f"/admin/offers/{offer_id}/delete", data={"csrf_token": csrf}
        )
        self.assertEqual(deleted_offer.status_code, 302)
        self.assertIsNotNone(bidmart.get_product("test-desk-light"))

        created_auction = self.client.post("/admin/auctions/create", data={
            "csrf_token": csrf,
            "product_slug": "test-desk-light",
            "starting_bid": "1000",
            "minimum_increment": "100",
            "duration_days": "3",
        })
        self.assertEqual(created_auction.status_code, 302)
        self.assertIn(b"Test Desk Light", self.client.get("/auctions").data)
        closed_auction = self.client.post(
            "/admin/auctions/test-desk-light/close", data={"csrf_token": csrf}
        )
        self.assertEqual(closed_auction.status_code, 302)
        self.assertEqual(self.client.get("/auction/test-desk-light").status_code, 404)
        reopened_auction = self.client.post(
            "/admin/auctions/test-desk-light/reopen",
            data={"csrf_token": csrf, "duration_days": "2"},
        )
        self.assertEqual(reopened_auction.status_code, 302)
        self.assertEqual(self.client.get("/auction/test-desk-light").status_code, 200)
        with bidmart.database() as connection:
            auction_id = connection.execute(
                "SELECT id FROM auctions WHERE slug = 'test-desk-light'"
            ).fetchone()["id"]
        updated_auction = self.client.post(
            "/admin/auctions/test-desk-light/update",
            data={"csrf_token": csrf, "minimum_increment": "250", "duration_days": "5"},
        )
        self.assertEqual(updated_auction.status_code, 302)
        with bidmart.database() as connection:
            auction = connection.execute(
                "SELECT minimum_increment, ends_at FROM auctions WHERE id = ?", (auction_id,)
            ).fetchone()
        self.assertEqual(auction["minimum_increment"], 250)
        self.assertGreater(auction["ends_at"], int(time.time()) + 4 * 86400)
        self.client.post(
            "/admin/auctions/test-desk-light/close", data={"csrf_token": csrf}
        )

        archived = self.client.post(
            "/admin/products/test-desk-light/archive", data={"csrf_token": csrf}
        )
        self.assertEqual(archived.status_code, 302)
        self.assertNotIn(b"Test Desk Light", self.client.get("/products").data)
        self.assertEqual(self.client.get("/products/test-desk-light").status_code, 404)
        restored = self.client.post(
            "/admin/products/test-desk-light/restore", data={"csrf_token": csrf}
        )
        self.assertEqual(restored.status_code, 302)
        self.assertIn(b"Test Desk Light", self.client.get("/products").data)

    def test_superadmin_dashboard_highlights_access_governance(self):
        with bidmart.database() as connection:
            superadmin = connection.execute(
                "INSERT INTO accounts (full_name, email, phone, password_hash, role, is_verified, created_at) "
                "VALUES (?, ?, '', ?, 'superadmin', 1, ?)",
                ("Root Account", self.email, generate_password_hash("secure-password"), 1),
            )
            connection.execute(
                "INSERT INTO accounts (full_name, email, phone, password_hash, role, is_verified, created_at) "
                "VALUES (?, ?, '', ?, 'admin', 1, ?)",
                ("Managed Admin", "managed-admin@example.invalid",
                 generate_password_hash("secure-password"), 1),
            )
            connection.execute(
                "INSERT INTO admin_role_requests (account_id, requested_role, status, requested_at) "
                "VALUES (?, 'admin', 'pending', ?)",
                (superadmin.lastrowid, 1),
            )
        with self.client.session_transaction() as session:
            session["user_id"] = superadmin.lastrowid
            session["user_email"] = self.email
            session["user_name"] = "Root Account"

        dashboard = self.client.get("/admin/dashboard")

        self.assertEqual(dashboard.status_code, 200)
        self.assertIn(b"Superadmin control center", dashboard.data)
        self.assertIn(b"Access governance", dashboard.data)
        self.assertIn(b"Pending access requests", dashboard.data)
        self.assertIn(b"Promote, demote, activate, or deactivate", dashboard.data)
        self.assertIn(b'href="#accounts"', dashboard.data)
        self.assertIn(b"Superadmin only", dashboard.data)

    def test_admin_fulfilment_requires_sequential_status_updates(self):
        self.start_checkout()
        checkout = self.client.get("/checkout")
        order_response = self.client.post(
            "/checkout", data=self.checkout_form(self.csrf_from(checkout), payment_method="cod")
        )
        confirmation = self.client.get(order_response.headers["Location"])
        with bidmart.database() as connection:
            order_id = connection.execute("SELECT id FROM orders").fetchone()["id"]
            admin = connection.execute(
                "INSERT INTO accounts (full_name, email, phone, password_hash, role, is_verified, created_at) "
                "VALUES (?, ?, '', ?, 'admin', 1, ?)",
                ("Store Admin", "admin@example.invalid",
                 generate_password_hash("secure-password"), 1),
            )
        with self.client.session_transaction() as session:
            session["user_id"] = admin.lastrowid
            session["user_email"] = "admin@example.invalid"
            session["user_name"] = "Store Admin"
        dashboard = self.client.get("/admin/dashboard")
        csrf = self.csrf_from(dashboard)
        invalid_jump = self.client.post(
            f"/admin/orders/{order_id}/status",
            data={"csrf_token": csrf, "order_status": "shipped"},
        )
        self.assertEqual(invalid_jump.status_code, 302)
        with bidmart.database() as connection:
            status = connection.execute(
                "SELECT order_status FROM orders WHERE id = ?", (order_id,)
            ).fetchone()["order_status"]
        self.assertEqual(status, "confirmed")

        for status in ("processing", "shipped", "delivered"):
            response = self.client.post(
                f"/admin/orders/{order_id}/status",
                data={"csrf_token": csrf, "order_status": status},
            )
            self.assertEqual(response.status_code, 302)
        with bidmart.database() as connection:
            status = connection.execute(
                "SELECT order_status FROM orders WHERE id = ?", (order_id,)
            ).fetchone()["order_status"]
        self.assertEqual(status, "delivered")

    def test_regular_user_cannot_access_admin_dashboard(self):
        with bidmart.database() as connection:
            user = connection.execute(
                "INSERT INTO accounts (full_name, email, phone, password_hash, role, is_verified, created_at) "
                "VALUES (?, ?, '', ?, 'user', 1, ?)",
                ("Regular User", self.email, generate_password_hash("secure-password"), 1),
            )
        with self.client.session_transaction() as session:
            session["user_id"] = user.lastrowid
            session["user_email"] = self.email
            session["user_name"] = "Regular User"
        self.assertEqual(self.client.get("/admin/dashboard").status_code, 403)

    def test_superadmin_can_change_staff_access_and_deactivation_revokes_session(self):
        with bidmart.database() as connection:
            superadmin = connection.execute(
                "INSERT INTO accounts (full_name, email, phone, password_hash, role, is_verified, created_at) "
                "VALUES (?, ?, '', ?, 'superadmin', 1, ?)",
                ("Root Account", "root@example.invalid",
                 generate_password_hash("secure-root-password"), 1),
            )
            account = connection.execute(
                "INSERT INTO accounts (full_name, email, phone, password_hash, role, is_verified, created_at) "
                "VALUES (?, ?, '', ?, 'user', 1, ?)",
                ("Managed Account", self.email, generate_password_hash("secure-password"), 1),
            )
        with self.client.session_transaction() as session:
            session["user_id"] = superadmin.lastrowid
            session["user_email"] = "root@example.invalid"
            session["user_name"] = "Root Account"

        dashboard = self.client.get("/admin/dashboard")
        self.assertEqual(dashboard.status_code, 200)
        self.assertIn(b'id="accounts"', dashboard.data)
        csrf = self.csrf_from(dashboard)
        promoted = self.client.post(
            f"/superadmin/accounts/{account.lastrowid}/update",
            data={"csrf_token": csrf, "action": "make_admin"},
        )
        self.assertEqual(promoted.status_code, 302)
        with bidmart.database() as connection:
            role = connection.execute(
                "SELECT role FROM accounts WHERE id = ?", (account.lastrowid,)
            ).fetchone()["role"]
        self.assertEqual(role, "admin")

        deactivated = self.client.post(
            f"/superadmin/accounts/{account.lastrowid}/update",
            data={"csrf_token": csrf, "action": "deactivate"},
        )
        self.assertEqual(deactivated.status_code, 302)
        with self.client.session_transaction() as session:
            session["user_id"] = account.lastrowid
            session["user_email"] = self.email
            session["user_name"] = "Managed Account"
        self.assertEqual(self.client.get("/admin/dashboard").status_code, 403)
        with self.client.session_transaction() as session:
            self.assertNotIn("user_id", session)

    def test_unverified_account_cannot_login(self):
        with patch.object(bidmart, "send_verification_email") as send_email:
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
            verification_token = send_email.call_args.args[1]

        response = self.client.get("/login.html")
        login_response = self.client.post("/login", data={
            "csrf_token": self.csrf_from(response),
            "email": self.email,
            "password": "secure-test-password",
        })
        self.assertEqual(login_response.status_code, 302)
        with self.client.session_transaction() as session:
            self.assertNotIn("user_id", session)

    def test_admin_registration_requires_verified_email_and_superadmin_approval(self):
        with patch.object(bidmart, "send_verification_email") as send_email:
            response = self.client.get("/register.html")
            self.assertIn(b'value="admin"', response.data)
            self.assertIn(b'value="user"', response.data)
            self.assertNotIn(b'value="superadmin"', response.data)
            self.assertIn(b'id="registerSubmitButton"', response.data)
            self.assertIn(b"Request ${roleName} approval", response.data)
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
        send_email.assert_not_called()
        self.assertTrue(post_response.headers["Location"].endswith("/register.html"))
        applicant_page = self.client.get("/register.html")
        self.assertIn(b"Your request is waiting for Superadmin approval", applicant_page.data)
        self.assertIn(self.email.encode(), applicant_page.data)
        self.assertIn(b'<meta http-equiv="refresh" content="5">', applicant_page.data)
        self.assertNotIn(b"Already requested Admin or Superadmin access?", applicant_page.data)
        with bidmart.database() as connection:
            applicant = connection.execute(
                "SELECT id, role, is_verified, verification_token_hash FROM accounts WHERE email = ?",
                (self.email,),
            ).fetchone()
            request_row = connection.execute(
                "SELECT status FROM admin_role_requests WHERE account_id = ?", (applicant["id"],)
            ).fetchone()
            connection.execute(
                "INSERT INTO accounts (full_name, email, phone, password_hash, role, is_verified, created_at) "
                "VALUES (?, ?, ?, ?, 'superadmin', 1, ?)",
                ("Superadmin", "root@example.invalid", "", generate_password_hash("secure-root-password"), 1),
            )
            superadmin_id = connection.execute(
                "SELECT id FROM accounts WHERE email = 'root@example.invalid'"
            ).fetchone()["id"]
        self.assertEqual(applicant["role"], "user")
        self.assertEqual(applicant["is_verified"], 0)
        self.assertIsNone(applicant["verification_token_hash"])
        self.assertEqual(request_row["status"], "pending")
        self.assertEqual(self.client.get("/superadmin/admin-requests").status_code, 403)

        early_token = "must-wait-for-approval"
        with bidmart.database() as connection:
            connection.execute(
                "UPDATE accounts SET verification_token_hash = ?, verification_expires_at = ? WHERE id = ?",
                (bidmart.hash_token(early_token), int(time.time()) + 1800, applicant["id"]),
            )
        self.client.get(f"/verify/{early_token}")
        with bidmart.database() as connection:
            account = connection.execute(
                "SELECT is_verified, verification_token_hash FROM accounts WHERE id = ?",
                (applicant["id"],),
            ).fetchone()
        self.assertEqual(account["is_verified"], 0)
        self.assertEqual(account["verification_token_hash"], bidmart.hash_token(early_token))
        with patch.dict(os.environ, {
            "SMTP_USERNAME": "sender@example.invalid",
            "SMTP_PASSWORD": "test-password",
            "SMTP_FROM": "sender@example.invalid",
        }), patch.object(bidmart, "issue_verification") as resend_verification:
            self.client.post("/resend-verification", data={
                "csrf_token": self.csrf_from(response),
                "email": self.email,
            })
        resend_verification.assert_not_called()

        superadmin_client = bidmart.app.test_client()
        with superadmin_client.session_transaction() as session:
            session["user_id"] = superadmin_id
            session["user_role"] = "superadmin"
        requests_page = superadmin_client.get("/superadmin/admin-requests")
        self.assertEqual(requests_page.status_code, 200)
        self.assertIn(self.email.encode(), requests_page.data)
        self.assertIn(b'aria-label="Open dashboard for Superadmin"', requests_page.data)
        self.assertNotIn(b'class="login-btn"', requests_page.data)
        self.assertNotIn(b'class="register-btn"', requests_page.data)
        self.assertIn(b'role-requests-page', requests_page.data)
        self.assertIn(b'class="role-request-card"', requests_page.data)
        self.assertIn(b'Approve Admin', requests_page.data)

        with patch.object(bidmart, "send_verification_email") as send_email:
            with superadmin_client.session_transaction() as session:
                csrf_token = session["csrf_token"]
            response = superadmin_client.post(
                f"/superadmin/admin-requests/{applicant['id']}/approve",
                data={"csrf_token": csrf_token},
            )
            send_email.assert_not_called()
        self.assertEqual(response.status_code, 302)
        with bidmart.database() as connection:
            account = connection.execute(
                "SELECT role, is_verified FROM accounts WHERE id = ?", (applicant["id"],)
            ).fetchone()
            request_row = connection.execute(
                "SELECT status, reviewed_by FROM admin_role_requests WHERE account_id = ?",
                (applicant["id"],),
            ).fetchone()
        self.assertEqual(account["role"], "user")
        self.assertEqual(account["is_verified"], 0)
        self.assertEqual(request_row["status"], "approved")
        self.assertEqual(request_row["reviewed_by"], superadmin_id)
        approved_page = self.client.get("/register.html")
        self.assertIn(b"Your request was approved", approved_page.data)
        self.assertIn(b"Create Account", approved_page.data)
        self.assertNotIn(b'<meta http-equiv="refresh" content="5">', approved_page.data)

        with patch.object(bidmart, "send_verification_email") as send_email:
            verification_page = self.client.post(
                "/registration/send-verification",
                data={"csrf_token": self.csrf_from(approved_page)},
            )
            send_email.assert_called_once()
            verification_token = send_email.call_args.args[1]
        self.assertTrue(verification_page.headers["Location"].endswith("/register.html"))
        verification_sent_page = self.client.get("/register.html")
        self.assertIn(b"Resend verification link", verification_sent_page.data)
        self.client.get(f"/verify/{verification_token}")
        with bidmart.database() as connection:
            account = connection.execute(
                "SELECT role, is_verified FROM accounts WHERE id = ?", (applicant["id"],)
            ).fetchone()
        self.assertEqual(account["role"], "admin")
        self.assertEqual(account["is_verified"], 1)

        with self.client.session_transaction() as session:
            session.clear()
        login_page = self.client.get("/login.html")
        login_response = self.client.post("/login", data={
            "csrf_token": self.csrf_from(login_page),
            "email": self.email,
            "password": "secure-test-password",
        })
        self.assertEqual(login_response.status_code, 302)
        with self.client.session_transaction() as session:
            self.assertEqual(session["user_role"], "admin")

    def test_public_registration_rejects_superadmin_role(self):
        with patch.object(bidmart, "send_verification_email") as send_email:
            response = self.client.get("/register.html")
            post_response = self.client.post("/register", data={
                "csrf_token": self.csrf_from(response),
                "full_name": "Superadmin Applicant",
                "email": self.email,
                "role": "superadmin",
                "password": "secure-test-password",
                "confirm_password": "secure-test-password",
            })
            send_email.assert_not_called()
        self.assertEqual(post_response.status_code, 302)
        with bidmart.database() as connection:
            applicant = connection.execute(
                "SELECT id FROM accounts WHERE email = ?", (self.email,)
            ).fetchone()
            request_count = connection.execute(
                "SELECT COUNT(*) FROM admin_role_requests WHERE account_id = ?",
                (applicant["id"],),
            ).fetchone()[0] if applicant else 0
        self.assertIsNone(applicant)
        self.assertEqual(request_count, 0)

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
        self.assertIn(b"Elevated-role requests must be approved before verification can be sent", page.data)
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
        self.assertNotIn(b"Manage auctions", response.data)
        self.assertNotIn(b"Close auction", response.data)

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
