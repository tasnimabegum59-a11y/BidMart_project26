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

## Creating the first Superadmin

Public registration never grants an elevated role immediately. To bootstrap the first Superadmin, stop the app and run this command once from the project folder:

```powershell
C:/Users/DESKTOP/AppData/Local/Programs/Python/Python312/python.exe create_superadmin.py
```

This local-only command prompts for a name, email, and password. If the email belongs to an existing verified User, enter that account's current password to upgrade it; a wrong password will not change the account. If the email is new, the command creates the first Superadmin. It refuses to run if a Superadmin already exists. Start the app again and sign in with those credentials. After that, people can request Admin access from registration; the existing Superadmin reviews requests at `/superadmin/admin-requests`.

## Tests

Run the test suite without sending email:

```powershell
C:/Users/DESKTOP/AppData/Local/Programs/Python/Python312/python.exe -m unittest -v
```

Tests use a temporary SQLite database and mock the SMTP send operation. Public registration offers User signup or an Admin access request; Superadmin accounts are provisioned separately and are not offered as a public registration role. Admin applicants receive no verification email until an existing Superadmin approves the request at `/superadmin/admin-requests`. The pending request page refreshes automatically; after approval, the applicant can select **Create Account** to receive the email verification link. They then verify their email; only then is the Admin role activated.

Before deployment, use HTTPS, set `APP_BASE_URL` to the HTTPS site, set `COOKIE_SECURE=true`, use a production WSGI server, and configure rate limits for registration and verification resend endpoints.

## Product checkout

Buy Now on the home page, product catalog, or product detail page requires a signed-in, email-verified BidMart account. Guests are sent to login first and can continue through account registration and email verification; the selected product remains in checkout after they sign in. The checkout and order endpoints also reject requests without an authenticated account. Auction details are public, but bidding requires login or account creation and is enforced on the server. Current catalog products use a standard (non-configurable) variant and start with 10 demo stock units. The server validates product, quantity, shipping details, inventory, coupon, and price before saving an order.

Delivery is ৳60 for Dhaka and ৳120 for the other listed divisions. The demo coupon `SAVE50` deducts ৳50 from orders of at least ৳500. COD orders are confirmed with payment status `unpaid`.

### SSLCOMMERZ setup

Online checkout uses the SSLCOMMERZ hosted payment page. Add these values to the private `.env` file; never commit or share the store password:

```dotenv
APP_BASE_URL=https://your-public-https-domain/
SSLCOMMERZ_STORE_ID=your-store-id
SSLCOMMERZ_STORE_PASSWORD=your-store-password
SSLCOMMERZ_IS_SANDBOX=true
```

Use sandbox credentials and keep sandbox mode enabled while testing. The callback/IPN URLs must be reachable by SSLCOMMERZ, so localhost alone cannot receive payment callbacks; use a public HTTPS deployment or a secure development tunnel. After successful testing and merchant approval, set `SSLCOMMERZ_IS_SANDBOX=false` and use live credentials. The server verifies successful transactions with the SSLCOMMERZ validation API and checks transaction ID, amount, currency, risk status, and payment state before marking an order paid. Failed sessions retain stock reservations until the 30-minute payment expiry, when abandoned inventory is released.

### Admin operations

Admin and Superadmin accounts can manage products directly from the product catalog, including opening the matching editor in **Store dashboard**; they can create, edit, archive, and restore products and adjust stock. Archiving removes a product from active listings while preserving its order history. The **Offers** page lists active product offers separately from the product catalog; staff can create, edit, pause, and remove offers from **Store dashboard** without deleting the product. Offers reuse the product's catalog price and previous price, and automatically stop appearing after their end time. Staff can create, edit, close, and reopen auctions in **Store dashboard** and close them from auction listings. They can also review orders and advance eligible orders through processing, shipped, and delivered. Staff account menus omit the unused **My Products** and **My Orders** entries. The Superadmin also reviews elevated-role requests and can promote/demote or activate/deactivate non-Superadmin accounts. Superadmin accounts cannot be changed from that screen.
