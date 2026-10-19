# BidMart email verification setup

## Security first

A Gmail App Password was exposed in chat. Treat it as compromised: revoke it in Google Account > Security > 2-Step Verification > App passwords before configuring email. Do not reuse it. Do not share the replacement password in chat or commit it.

## Configure locally

1. Install the project dependencies:

   ```powershell
   C:/Users/DESKTOP/AppData/Local/Programs/Python/Python312/python.exe -m pip install -r requirements.txt
   ```

2. Copy `.env.example` to `.env` and set a long random `FLASK_SECRET_KEY`. In PowerShell, generate one with:

   ```powershell
   C:/Users/DESKTOP/AppData/Local/Programs/Python/Python312/python.exe -c "import secrets; print(secrets.token_urlsafe(48))"
   ```

3. Set `SMTP_USERNAME` and `SMTP_FROM` to the sender mailbox, and `SMTP_PASSWORD` to a newly generated Gmail App Password. Keep `.env` private; `.gitignore` excludes it.

4. Start the app:

   ```powershell
   C:/Users/DESKTOP/AppData/Local/Programs/Python/Python312/python.exe app.py
   ```

5. Open http://127.0.0.1:5000. Register with an inbox you can access, click the emailed verification link, then sign in. Verification links expire after 30 minutes and can only be used once. The registration page can resend a link.

Use **Forgot your password?** on the login page to request a password reset email. Reset links expire after 30 minutes and can only be used once. SMTP must be configured for verification and password reset emails to arrive.

## Tests

Run the test suite without sending email:

```powershell
C:/Users/DESKTOP/AppData/Local/Programs/Python/Python312/python.exe -m unittest -v
```

Tests use a temporary SQLite database and mock the SMTP send operation. Only regular user sign-up is enabled; admin and superadmin creation remains rejected through public registration and must be provisioned by an authorized owner.

Before deployment, use HTTPS, set `APP_BASE_URL` to the HTTPS site, set `COOKIE_SECURE=true`, use a production WSGI server, and configure rate limits for registration and verification resend endpoints.

## Product checkout

Buy Now on the home page, product catalog, or product detail page starts a single-product checkout. Guests can place orders without an account; signed-in buyers have their saved name, email, and mobile prefilled. Current catalog products use a standard (non-configurable) variant and start with 10 demo stock units. The server validates product, quantity, shipping details, inventory, coupon, and price before saving an order.

Delivery is ৳60 for Dhaka and ৳120 for the other listed divisions. The demo coupon `SAVE50` deducts ৳50 from orders of at least ৳500. COD orders are confirmed with payment status `unpaid`; online selections create pending, unpaid order records. No bKash, Nagad, or card gateway is configured, so online selections do not charge the buyer or mark an order paid. Configure and verify a real payment provider callback before enabling actual online payments.
