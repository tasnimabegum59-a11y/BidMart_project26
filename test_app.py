import re
import os
import tempfile
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
        return re.search(rb'name="csrf_token" value="([^"]+)"', response.data).group(1).decode()

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
        csrf = self.csrf_from(response)
        response = self.client.post("/login", data={
            "csrf_token": csrf,
            "email": self.email,
            "password": "secure-test-password",
            "role": "user",
        })
        self.assertEqual(response.status_code, 302)
        home = self.client.get("/")
        self.assertIn(self.email.encode(), home.data)

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
            "role": "user",
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
            "role": "admin",
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
            "role": "user",
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


if __name__ == "__main__":
    unittest.main()
