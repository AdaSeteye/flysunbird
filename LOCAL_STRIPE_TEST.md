# Test Stripe Checkout locally

Follow these steps to run and test the Stripe “Pay with Card” flow on your machine.

---

## What you need to provide

1. **Stripe Secret Key (required)**  
   - Sign in at [dashboard.stripe.com](https://dashboard.stripe.com).  
   - Turn **Test mode** ON (top right).  
   - Go to **Developers → API keys**.  
   - Copy the **Secret key** (starts with `sk_test_...`).  
   - You will paste this into `.env` as `STRIPE_SECRET_KEY`.

2. **Stripe webhook signing secret (required for “booking marked paid” after payment)**  
   - Stripe cannot call `localhost`, so we use the Stripe CLI to forward webhooks.  
   - After you run `stripe listen` (below), the CLI will print a **Signing secret** (starts with `whsec_...`).  
   - You will paste that into `.env` as `STRIPE_WEBHOOK_SECRET`.

---

## Step 1: Add your Stripe Secret Key to `.env`

1. Open the project’s **`.env`** file.
2. Set your test secret key:

   ```env
   STRIPE_SECRET_KEY=<paste your key from Stripe Dashboard>
   ```

   (Get the Secret key from Developers → API keys; it starts with `sk_test_`.)

3. Save the file.

`CLIENT_BASE_URL` and `API_PUBLIC_URL` are already set to `http://localhost:8000` so that after payment Stripe redirects back to your API, which serves the fly UI at `/fly/`.

---

## Step 2: Start the backend

From the project root:

```bash
docker compose up --build
```

Wait until the API is up (you should see “Uvicorn running” and migrations/seeding in the logs). Then:

- **API + fly UI:** http://localhost:8000  
- **Booking page:** http://localhost:8000/fly/booking.html  
- **Swagger:** http://localhost:8000/docs  

---

## Step 3: Forward Stripe webhooks to your machine

Stripe needs to send `checkout.session.completed` to your API. On your machine, Stripe can’t reach `localhost`, so we use the Stripe CLI to forward events.

1. **Install Stripe CLI** (if needed):  
   [https://stripe.com/docs/stripe-cli#install](https://stripe.com/docs/stripe-cli#install)

2. **Log in** (one-time):

   ```bash
   stripe login
   ```

3. **Forward webhooks** to your API (keep this terminal open):

   ```bash
   stripe listen --forward-to localhost:8000/api/v1/webhooks/stripe
   ```

4. The CLI will print something like:

   ```text
   Ready! Your webhook signing secret is whsec_xxxxxxxxxxxxxxxxxxxxxxxx
   ```

5. **Copy that `whsec_...` value**, open `.env`, and set:

   ```env
   STRIPE_WEBHOOK_SECRET=<paste the whsec_... value from CLI>
   ```

6. **Restart the API** so it loads the new env (e.g. stop `docker compose` with Ctrl+C and run `docker compose up` again).  
   Leave `stripe listen` running in the other terminal.

---

## Step 4: Create slots and a booking (if you don’t have one)

1. Open http://localhost:8000/docs  
2. Log in: `POST /api/v1/auth/login` with e.g. `{"email":"ops@flysunbird.co.tz","password":"<from app/seed.py>"}` → copy `access_token`.  
3. Authorize in Swagger with `Bearer <access_token>`.  
4. `GET /api/v1/ops/slot-rules` → copy a slot rule `id`.  
5. `POST /api/v1/ops/slot-rules/{id}/run-now` to generate slots.  
6. `GET /api/v1/public/routes` → copy a route `id`.  
7. `GET /api/v1/public/ops-link?route_id=<id>&dateStr=2026-03-15&currency=USD` → copy `opsParam`.  
8. Open:  
   **http://localhost:8000/fly/booking.html?ops=<opsParam>**  
9. Pick a slot, fill passengers, continue to the **Payment** page.

---

## Step 5: Pay with Stripe (test card)

1. On the Payment page, leave **“Pay with Card (Stripe)”** selected.  
2. Click **Pay now**.  
3. You should be redirected to Stripe Checkout.  
4. Use Stripe’s test card: **4242 4242 4242 4242**, any future expiry (e.g. 12/34), any CVC, any billing details.  
5. Complete payment.  
6. You should be redirected back to the confirmation page and the booking should show as paid.  
7. In the terminal where `stripe listen` is running, you should see a `checkout.session.completed` event.

---

## Troubleshooting

| Issue | What to check |
|-------|----------------|
| “Stripe is not configured” (503) | `STRIPE_SECRET_KEY` is set in `.env` and the API was restarted. |
| Redirect to Stripe works but booking never becomes “paid” | `STRIPE_WEBHOOK_SECRET` is set (from `stripe listen`) and the API was restarted; keep `stripe listen` running. |
| Success/cancel URLs open 404 | You must use the fly UI under the API: open **http://localhost:8000/fly/booking.html** (not a separate server on 8080 unless you set `CLIENT_BASE_URL` and serve the app with a `/fly/` path). |
| CORS errors | The fly UI should be opened from `http://localhost:8000/fly/...`; CORS is already allowed for localhost. |

---

## Summary

- **You provide:** `STRIPE_SECRET_KEY` (from Dashboard) and `STRIPE_WEBHOOK_SECRET` (from `stripe listen`).  
- **Already set in `.env`:** `CLIENT_BASE_URL=http://localhost:8000` so redirects hit the API’s `/fly/` pages.  
- **Run:** `docker compose up`, then `stripe listen --forward-to localhost:8000/api/v1/webhooks/stripe`, then open http://localhost:8000/fly/booking.html and complete a booking and payment with card 4242 4242 4242 4242.
