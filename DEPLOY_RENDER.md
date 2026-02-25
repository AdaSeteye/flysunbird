# Deploy FlySunbird to Render

This guide walks through deploying the FlySunbird API, frontend, and Celery worker to Render using the Blueprint (optional) or manual setup.

## What you get

- **One URL** for both the API and the ops console (login, admin, fly booking). The API is at `https://<your-service>.onrender.com/api/v1`, and the same URL serves the frontend (e.g. `/login.html`, `/fly/booking.html`).
- **PostgreSQL** (Render free tier, 90 days) for the app database.
- **Redis** via [Upstash](https://upstash.com/) (free tier) for Celery broker/backend.
- **Celery** worker + beat in one process for slots, holds, and email queue.

---

## Option A: Deploy with Blueprint (recommended)

1. **Push the repo to GitHub**  
   Ensure the repo (e.g. `AdaSeteye/flysunbird`) contains this project at the repo root (the folder with `render.yaml`, `Dockerfile`, `app/`, `ops_console/`).

2. **Create a free Redis (Upstash)**  
   - Go to [Upstash Console](https://console.upstash.com/) → Create Database → Redis, region close to your Render region.  
   - Copy the **Redis URL** (e.g. `rediss://default:xxx@xxx.upstash.io:6379`).

3. **In Render**  
   - [Dashboard](https://dashboard.render.com/) → **New** → **Blueprint**.  
   - Connect your GitHub account and select the repo; use the branch that has `render.yaml`.  
   - Render will create:
     - A **PostgreSQL** database (`flysunbird-db`).
     - A **Web Service** (`flysunbird-api`) from the Dockerfile.
     - A **Background Worker** (`flysunbird-celery`) running Celery worker + beat.

4. **Set environment variables** (for both **flysunbird-api** and **flysunbird-celery**):  
   In each service → **Environment** tab, add or confirm:

   | Key | Where | Notes |
   |-----|--------|------|
   | `REDIS_URL` | You set | Upstash Redis URL from step 2. |
   | `CLIENT_BASE_URL` | You set | Same as your Render web URL, e.g. `https://flysunbird-api.onrender.com`. |
   | `API_PUBLIC_URL` | You set | Same, e.g. `https://flysunbird-api.onrender.com`. |
   | `CORS_ORIGINS` | Optional | Same URL if you need CORS (e.g. `https://flysunbird-api.onrender.com`). |
   | `STRIPE_SECRET_KEY` | You set | For Pay with Card (Stripe). See [Stripe production](#stripe-pay-with-card--production) below. |
   | `STRIPE_WEBHOOK_SECRET` | You set | From Stripe webhook signing secret. See [Stripe production](#stripe-pay-with-card--production) below. |
   | `SECRET_KEY` | Blueprint | Auto-generated for web; worker gets it from web service. |
   | `DATABASE_URL` | Blueprint | Set from `flysunbird-db` automatically. |

   **If the app fails to connect to Postgres**, Render may give a `postgres://` URL. You can override `DATABASE_URL` with the **Internal Database URL** from the database’s **Info** tab, and change the scheme to `postgresql+psycopg2://` (replace `postgres://` with `postgresql+psycopg2://`).

5. **Stripe (Pay with Card) – production**  
   To accept card payments via Stripe Checkout on Render:

   - **Stripe Secret Key**  
     - [Stripe Dashboard](https://dashboard.stripe.com) → **Developers** → **API keys**.  
     - For production use the **Live** key (`sk_live_...`); for testing in production use the **Test** key (`sk_test_...`).  
     - In Render → **flysunbird-api** → **Environment** → set `STRIPE_SECRET_KEY` to that value.

   - **Stripe webhook** (so bookings are marked paid after payment):  
     - Stripe Dashboard → **Developers** → **Webhooks** → **Add endpoint**.  
     - **Endpoint URL:** `https://<your-render-web-service-url>/api/v1/webhooks/stripe`  
       (e.g. `https://flysunbird-api.onrender.com/api/v1/webhooks/stripe`).  
     - **Events to send:** click **Select events** → choose **checkout.session.completed** → **Add endpoint**.  
     - Open the new endpoint → **Reveal** the **Signing secret** (`whsec_...`).  
     - In Render → **flysunbird-api** → **Environment** → set `STRIPE_WEBHOOK_SECRET` to that value.

   - **CLIENT_BASE_URL** must be set (step 4) to your public app URL (e.g. `https://flysunbird-api.onrender.com`) so Stripe can redirect customers back to the confirmation page after payment.

   For a short checklist of only what you need to paste in, see **[PRODUCTION_STRIPE.md](PRODUCTION_STRIPE.md)**.

6. **Optional (other production settings)**  
   Add in the Dashboard for the web service (and worker if needed):  
   - Email: `SMTP_*` or `SENDGRID_API_KEY` + `SENDGRID_FROM_EMAIL`.  
   - Tickets: `TICKET_LOCAL_DIR` (e.g. `./data/tickets`); for GCS, `GCS_BUCKET_NAME` and `GOOGLE_APPLICATION_CREDENTIALS`.

7. **Deploy**  
   Save env vars and let Render build and deploy. The first deploy runs migrations and seed via the Docker `entrypoint.sh`.

8. **Use the app**  
   - Open `https://<your-web-service-name>.onrender.com` → redirects to `/login.html`.  
   - Log in with a seeded user (emails and default passwords are in `app/seed.py`; change them in production).  
   - The frontend uses the same origin as the API, so no extra API URL configuration is needed.

---

## Option B: Manual setup (no Blueprint)

1. **Create a PostgreSQL database**  
   Render Dashboard → **New** → **PostgreSQL**. Create and copy the **Internal Database URL**.

2. **Create a Web Service**  
   - **New** → **Web Service**; connect the repo.  
   - **Root Directory**: leave blank if the app is at repo root.  
   - **Environment**: Docker.  
   - **Build**: Render uses the repo’s `Dockerfile`.  
   - **Start**: leave default (Dockerfile `CMD`).  
   - **Health Check Path**: `/health`.

3. **Environment variables** (Web Service)  
   Add at least:  
   `DATABASE_URL`, `REDIS_URL` (Upstash), `SECRET_KEY` (generate a long random string), `CLIENT_BASE_URL`, `API_PUBLIC_URL`, `ENV=production`. Optionally `CORS_ORIGINS`.

4. **Create a Background Worker**  
   - **New** → **Background Worker**; same repo.  
   - **Environment**: Docker.  
   - **Build**: same Dockerfile.  
   - **Start Command**:  
     `celery -A app.tasks.celery_app worker --beat -l info`  
   - Set the same `DATABASE_URL`, `REDIS_URL`, `SECRET_KEY`, `ENV=production` as the web service.

5. **Deploy**  
   Deploy the web service first so the DB is reachable; then deploy the worker.

---

## Frontend and API on the same URL

The FastAPI app serves:

- **API**: `/api/v1/*` and `/health`.
- **Frontend**: static files from `ops_console/` (e.g. `/login.html`, `/fly/booking.html`).  
  `/` redirects to `/login.html`.

The frontend uses `window.location.origin + "/api/v1"` when no custom API base is set, so once deployed to Render no extra configuration is needed for the same-origin case.

---

## Free tier notes

- **Web Service**: Render free tier spins down after inactivity; first request may be slow.  
- **PostgreSQL**: Free plan expires after 90 days; export data or upgrade before then.  
- **Background Worker**: Free tier may not include workers; you may need a paid plan for the Celery worker. If you skip the worker, scheduled tasks (slots, holds, email queue) will not run.

---

## Troubleshooting

- **502 / service won’t start**: Check **Logs** for the web service. Common causes: `DATABASE_URL` wrong or not set, `REDIS_URL` missing, or migrations failing (see next).  
- **Migrations fail**: Ensure `DATABASE_URL` is the **Internal** URL (same private network as the service). If you see `postgres://` and get driver errors, try overriding `DATABASE_URL` with the same URL but scheme `postgresql+psycopg2://`.  
- **Celery not processing**: Ensure the worker service has the same `REDIS_URL` and `DATABASE_URL` as the web service and that the worker is running (Logs).
