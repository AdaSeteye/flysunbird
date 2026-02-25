# Stripe production – what you need to provide

The code and Render blueprint are set up for Stripe. You only need to add **three values** in the right places.

---

## 1. Stripe Secret Key

- Go to [dashboard.stripe.com](https://dashboard.stripe.com).
- For **live** payments: turn **Test mode** OFF → **Developers** → **API keys** → copy **Secret key** (`sk_live_...`).
- For **testing on production** (same as local): leave **Test mode** ON → copy **Secret key** (`sk_test_...`).
- In **Render** → **flysunbird-api** → **Environment** → set:
  - **Key:** `STRIPE_SECRET_KEY`
  - **Value:** the key you copied (e.g. `sk_live_...` or `sk_test_...`)

---

## 2. Your Render web service URL

You need this for the webhook in step 3. It is the URL of your **flysunbird-api** service, e.g.:

- `https://flysunbird-api.onrender.com`

Find it in Render Dashboard → **flysunbird-api** → top of the page (e.g. “https://flysunbird-api.onrender.com”). No trailing slash.

---

## 3. Stripe webhook signing secret

- In Stripe Dashboard → **Developers** → **Webhooks** → **Add endpoint**.
- **Endpoint URL:**  
  `https://<your-render-url>/api/v1/webhooks/stripe`  
  Example: `https://flysunbird-api.onrender.com/api/v1/webhooks/stripe`
- **Events:** click **Select events** → choose **checkout.session.completed** → **Add endpoint**.
- Open the new endpoint → **Reveal** under “Signing secret” → copy the value (`whsec_...`).
- In **Render** → **flysunbird-api** → **Environment** → set:
  - **Key:** `STRIPE_WEBHOOK_SECRET`
  - **Value:** the signing secret you copied (`whsec_...`)

---

## Already set by you or the blueprint

- **CLIENT_BASE_URL** – You set this when deploying (e.g. `https://flysunbird-api.onrender.com`). Stripe uses it to redirect customers back to your app after payment. If you already set it for the main deployment, no change needed.
- **STRIPE_SECRET_KEY** and **STRIPE_WEBHOOK_SECRET** – You add these in Render as above; the blueprint only reserves the keys.

---

## Checklist

| What | Where to get it | Where to set it |
|------|-----------------|-----------------|
| Stripe Secret Key | Stripe Dashboard → Developers → API keys | Render → flysunbird-api → Environment → `STRIPE_SECRET_KEY` |
| Webhook URL | Your Render API URL + `/api/v1/webhooks/stripe` | Stripe Dashboard → Webhooks → Add endpoint |
| Webhook Signing secret | Stripe Dashboard → Webhooks → (your endpoint) → Reveal signing secret | Render → flysunbird-api → Environment → `STRIPE_WEBHOOK_SECRET` |

After saving the env vars in Render, the service will redeploy. Then “Pay with Card (Stripe)” on the live site will create a Checkout session, and completed payments will mark the booking as paid via the webhook.
