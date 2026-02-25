# How to run end-to-end (backend + frontend, Swagger + console)

Follow these steps to run the backend, try the API in Swagger, and use the booking UI with the ops console — as in the README.

---

## How the whole system works (overview)

### What it is

**FlySunbird** is a flight booking system (e.g. Dar es Salaam ↔ Zanzibar). It has:

- A **backend API** (FastAPI) at http://localhost:8000 — routes, slots, bookings, payments, ops.
- A **booking UI** (static HTML/JS) — you serve it (e.g. on port 8080) and it calls the API.
- An **ops console** (static HTML) — admin dashboard, bookings, routes, slot rules, OPS payload; you serve it (e.g. on 8090).
- **Background jobs** (Celery + Redis) — expire unpaid holds every minute, generate time slots every 6 hours.

So: **one backend**, **one DB**, **one Redis**, **one Celery worker + beat**; the UIs are separate static sites that talk to the API.

### Main concepts

| Concept | Meaning |
|--------|--------|
| **Route** | A leg (e.g. "Dar es Salaam Airport" → "Zanzibar Airport"). Seed creates one by default. |
| **Slot rule** | Defines when flights exist: days of week, times (e.g. 09:00, 11:00), price, capacity. Seed creates one. |
| **Time entry (slot)** | A concrete flight on a date: route + date + time + seats left. Created by the **generate_slots** Celery task (every 6h or via "run-now" in Swagger). |
| **OPS payload** | JSON for the UI: route labels, date, currency, list of slots (start, end, price, seats, flightNo). The UI gets it via `?ops=<base64url>` or from the API. |
| **Booking** | Created by `POST /api/v1/public/bookings` (timeEntryId, pax, passengers, booker). Gets a `bookingRef`. Hold expires after a few minutes if not paid. |
| **Payment** | Cybersource (card) via `/public/payments/cybersource/charge`, or **mark paid** by OPS/Admin (no card). |

### Data flow (booking journey)

1. **Slots exist**  
   - Celery runs `generate_slots` (every 6h or manually via Swagger `POST .../slot-rules/{id}/run-now`).  
   - This creates **time_entries** for the route+date from the **slot_rule** (times, capacity, price).

2. **User gets the OPS link**  
   - Someone (or the ops console) calls `GET /api/v1/public/ops-link?route_id=...&dateStr=...&currency=USD`.  
   - API returns `{ "opsParam": "<base64>" }`. That base64 decodes to the OPS payload (from, to, dateStr, slots with `id` = time entry id).

3. **User opens the UI**  
   - Opens `http://localhost:8080/booking.html?ops=<opsParam>`.  
   - UI decodes `opsParam` and shows route, date, and slots.  
   - UI must have `FLYSUNBIRD_API_BASE` set to `http://localhost:8000/api/v1` (e.g. in `localStorage`).

4. **User picks a slot and passengers**  
   - UI sends `POST /api/v1/public/bookings` with `timeEntryId` (from the slot’s `id`), pax, passengers, booker.  
   - API creates the booking, returns `bookingRef`.  
   - UI redirects to the payment page with that `bookingRef`.

5. **Payment**  
   - **Option A:** User pays by card → UI calls `POST /api/v1/public/payments/cybersource/charge` with the Cybersource payload.  
   - **Option B:** OPS/Admin marks the booking paid in Swagger or ops console: `POST /api/v1/ops/bookings/{booking_ref}/mark-paid?pilot_email=...`.

6. **After payment**  
   - User can open the confirmation/ticket page (with `bookingRef`).  
   - API returns booking details and ticket PDF from `GET /api/v1/public/bookings/{booking_ref}` and `.../ticket`.  
   - **Ticket QR code:** The ticket (web page and PDF) shows a QR code. Scanning it opens the ticket PDF URL. Set `API_PUBLIC_URL` in `.env` (e.g. `http://localhost:8000`) so the QR encodes the correct URL.

### Background jobs (Celery)

- **expire_holds** (every minute): finds bookings in `PENDING_PAYMENT` with `hold_expires_at` in the past and updates them (e.g. release hold).  
- **generate_slots** (every 6 hours): for each active slot rule, creates/updates **time_entries** for future dates within the rule’s horizon (days of week, times, capacity, price).

### Where things live

- **Backend:** `flysunbird_ops_plus_backend_CONNECTED_ALL/` — FastAPI app, Alembic migrations, seed, Celery tasks, `ops_console/` static files.  
- **Booking UI:** `ops_console/fly/` — booking, passengers, payment, confirmation; calls the same API.  
- **API base:** The booking UI always uses the API for calendar availability and slots (no demo/offline mode). It defaults to same-origin `/api/v1` when deployed with the backend. If the UI is on another host (e.g. port 8080), set `FLYSUNBIRD_API_BASE = "http://localhost:8000/api/v1"` (e.g. in `localStorage`).

The sections below are the **step-by-step instructions** to run everything and test (backend, slots, OPS link, UI, Swagger, ops console).

---

## 1. Backend: env and start

From the **backend** folder (`flysunbird_ops_plus_backend_CONNECTED_ALL`):

```bash
cd flysunbird_ops_plus_backend_CONNECTED_ALL
```

Ensure you have a `.env` file (copy from `.env.example` if needed). Defaults work for local Docker:

```bash
# If .env is missing:
copy .env.example .env   # Windows
# cp .env.example .env   # Mac/Linux
```

Start the stack (API, DB, Redis, MailHog, Celery worker, Celery beat):

```bash
docker compose up --build
```

Wait until you see the API listening. Then:

- **API:** http://localhost:8000  
- **Swagger docs:** http://localhost:8000/docs  
- **MailHog (dev mail):** http://localhost:8025  

**If you get "relation \"routes\" (or \"users\" / \"bookings\") does not exist":** the database has no tables. The API container uses an **entrypoint** that runs migrations before uvicorn. You must see these lines in the **api** logs when the container starts:

- `[entrypoint] Waiting for database...`
- `[entrypoint] Running migrations...`
- Alembic lines like `INFO  [alembic.runtime.migration] Running upgrade  -> 0001_initial`
- `[entrypoint] Seeding...`
- `[entrypoint] Starting application...`

If you **don’t** see them, the image is probably old. Do a **no-cache rebuild** and optionally a **fresh DB**:

```bash
docker compose down
docker compose build --no-cache api
docker compose up
```

Watch the **api** logs from the start; the lines above must appear before "Uvicorn running". If the DB was created before migrations existed, remove the volume and start clean:

```bash
docker compose down -v
docker compose up --build
```

To run migrations by hand (same effect as the entrypoint):

```bash
docker compose exec api python -m alembic upgrade head
```

---

## 2. Create slots (so the UI has flights)

The seed creates one **route** and one **slot rule**, but **time slots** are created by a Celery task that runs every 6 hours. To have slots right away:

**Option A – Using Swagger**

1. Open http://localhost:8000/docs  
2. **Login:** `POST /api/v1/auth/login`  
   - Body (e.g.): `{"email":"ops@flysunbird.co.tz","password":"ops12345"}`  
   - Copy the `access_token` from the response.  
3. Click **Authorize**, paste: `Bearer <access_token>`, then Authorize.  
4. **List slot rules:** `GET /api/v1/ops/slot-rules`  
   - Copy one `id` (e.g. the first rule).  
5. **Generate slots now:** `POST /api/v1/ops/slot-rules/{rule_id}/run-now`  
   - Set `rule_id` to the id from step 4.  
   - Execute. You should get `{"ok": true}`.

**Option B – Wait**

- Do nothing; the first slot generation runs after 6 hours.

---

## 3. Get `route_id` and OPS link (as in README)

**In Swagger (no auth needed for public endpoints):**

1. **List routes:** `GET /api/v1/public/routes`  
   - Response is a list; take the `id` of the route (e.g. Dar es Salaam → Zanzibar).  
2. **Get OPS link:**  
   `GET /api/v1/public/ops-link?route_id=<ROUTE_ID>&dateStr=2026-02-07&currency=USD`  
   - Replace `<ROUTE_ID>` with the id from step 1.  
   - Use a `dateStr` that is in the future and within the slot rule’s horizon.  
   - Copy the `opsParam` value from the response.

If you use a date that has no slots yet, `opsParam` will still be returned but the payload may have empty `slots`. Use a date after running “run-now” and within the rule’s horizon (e.g. tomorrow).

---

## 4. Frontend: serve the UI and set API base

The UI must be served over HTTP (not `file://`) and must know the API base URL.

**Serve the fly UI on port 8080** (CORS is allowed for `localhost:8080`).

From the **project root**, for example:

**Using the booking UI (from this repo):**

```bash
cd ops_console/fly
python -m http.server 8080
```

**Set the API base** in the browser (so the UI calls your backend):

1. Open http://localhost:8080/booking.html (you can open it without `?ops=` first).  
2. Open DevTools (F12) → Console.  
3. Run:
   ```js
   localStorage.setItem("FLYSUNBIRD_API_BASE", "http://localhost:8000/api/v1");
   ```
4. Refresh the page (or close and reopen the tab).

---

## 5. Open the booking flow with the OPS link (README flow)

In the same browser (where you set `FLYSUNBIRD_API_BASE`):

Open:

```
http://localhost:8080/booking.html?ops=<opsParam>
```

Replace `<opsParam>` with the value from step 3 (the `opsParam` from `/api/v1/public/ops-link`).

You should see the route, date, and slots. Then:

1. Choose a slot → **Select**  
2. Fill passengers → **Continue to Payment**  
3. Fill billing and card (or use Selcom if that UI path is used) → **Pay now**  

If Cybersource is not configured in `.env`, the payment request will fail (e.g. 500). You can still test the rest of the flow and use **Mark paid** in Swagger or the ops console instead (see below).

---

## 6. Test in Swagger (API-only)

Use Swagger for a full API-only test:

1. **Get routes:** `GET /api/v1/public/routes` → note `route_id`.  
2. **Get time-entries (slots):**  
   `GET /api/v1/public/time-entries?route_id=<ROUTE_ID>&dateStr=2026-02-07`  
   → pick one slot’s `id` (`timeEntryId`).  
3. **Create booking:** `POST /api/v1/public/bookings`  
   - Body (example):
   ```json
   {
     "timeEntryId": "<TIME_ENTRY_ID>",
     "pax": 1,
     "bookerEmail": "customer@example.com",
     "bookerName": "Test User",
     "passengers": [{"first": "Test", "last": "User", "phone": "+255123456789"}]
   }
   ```
   - Copy `bookingRef` from the response.  
4. **Mark paid (instead of card):**  
   - Log in as ops (or admin) and Authorize.  
   - `POST /api/v1/ops/bookings/{booking_ref}/mark-paid?pilot_email=pilot@flysunbird.co.tz`  
   - Replace `{booking_ref}` with the `bookingRef` from step 3.  
5. **Get booking:** `GET /api/v1/public/bookings/{booking_ref}`  
6. **Get ticket (if implemented):** `GET /api/v1/public/bookings/{booking_ref}/ticket`  

If Cybersource is configured, you can instead use:

- `POST /api/v1/public/payments/cybersource/sale` with `bookingRef`, `billTo`, `card`, `currency`  
- or `POST /api/v1/public/payments/cybersource/charge` with the full frontend-style payload.

---

## 7. Ops console (admin dashboard)

The ops console is static HTML under `ops_console/` (admin-dashboard, bookings, routes, slots, ops-payload, etc.). It is **not** served by the FastAPI app.

To use it:

1. Serve it over HTTP, e.g. from the backend repo:
   ```bash
   cd flysunbird_ops_plus_backend_CONNECTED_ALL/ops_console
   python -m http.server 8090
   ```
2. Open http://localhost:8090/admin-dashboard.html  
3. Log in (e.g. ops@flysunbird.co.tz / ops12345).  
4. The console will call the API; set its API base to `http://localhost:8000/api/v1` if it uses `FLYSUNBIRD_API_BASE` (or as configured in the console’s scripts).

From the ops console you can open the **OPS payload** page, pick route and date, get the booking link (`booking.html?ops=...`), and open it in a new tab (use the same origin or ensure the UI is served on 8080 with `FLYSUNBIRD_API_BASE` set as above).

---

## 8. Default users (from README / seed)

- admin@flysunbird.co.tz / admin12345  
- ops@flysunbird.co.tz / ops12345  
- finance@flysunbird.co.tz / finance12345  
- pilot@flysunbird.co.tz / pilot12345  

(Seed uses `@flysunbird.co.tz`; if your seed uses `.local`, use that.)

---

## How to check the system is working correctly

Follow these checks in order. If any step fails, fix it before continuing.

### 1. Backend is up

- Run: `docker compose up --build` in `flysunbird_ops_plus_backend_CONNECTED_ALL`.
- **Check:** In the logs you see no “[seed] users table not found” and no “relation \"bookings\" does not exist” from the worker. Uvicorn shows “Application startup complete”.
- **Check:** Open http://localhost:8000/health → you see `{"status":"ok"}`.
- **Check:** Open http://localhost:8000/docs → Swagger UI loads.

### 2. API returns routes and slots

- In Swagger (or a browser): **GET** `/api/v1/public/routes`.
- **Check:** Response is a list with at least one route; note its `id` (e.g. `route_id`).
- **Generate slots** so a date has flights: in Swagger, **POST** `/api/v1/auth/login` with `{"email":"ops@flysunbird.co.tz","password":"ops12345"}`, then **Authorize** with the `access_token`, then **GET** `/api/v1/ops/slot-rules` → copy one rule `id` → **POST** `/api/v1/ops/slot-rules/{rule_id}/run-now`.
- **Check:** `GET /api/v1/public/ops-link?route_id=<ROUTE_ID>&dateStr=2026-02-07&currency=USD` returns `{"opsParam":"..."}` and the decoded payload has a `slots` array (can be empty if that date has no slots; use a date after “run-now” if needed).
- **Check:** `GET /api/v1/public/time-entries?route_id=<ROUTE_ID>&dateStr=2026-02-07` returns `{"items":[...]}` with at least one slot (after run-now for that date).

### 3. Booking UI works (with ops link)

- Serve the fly UI: e.g. `cd ops_console/fly` then `python -m http.server 8080`.
- In the browser: set API base: `localStorage.setItem("FLYSUNBIRD_API_BASE", "http://localhost:8000/api/v1")` then refresh.
- Open `http://localhost:8080/booking.html?ops=<opsParam>` (use `opsParam` from step 2).
- **Check:** You see route, date, and at least one flight. Click **Select** on a flight → passenger page loads.
- Fill one passenger, click **Continue to Payment**.
- **Check:** Payment page loads with booking summary. (If Cybersource is not configured, paying by card may fail; you can still use “mark paid” in step 5.)

### 4. Booking UI works (without ops link – direct open)

- Open `http://localhost:8080/booking.html` (no `?ops=`).
- **Check:** You can select **From** (e.g. Dar es Salaam Airport), click **Next: Choose date**, pick a date, then select **Destination** (e.g. Zanzibar Airport). Slots load and you can **Select** and continue to passengers → payment.

### 5. Booking is created and can be marked paid

- After completing the flow in step 3 or 4, note the `bookingRef` (e.g. from the payment page URL or confirmation).
- In Swagger (logged in as ops): **POST** `/api/v1/ops/bookings/{booking_ref}/mark-paid?pilot_email=pilot@flysunbird.co.tz`.
- **Check:** Response is success (e.g. 200). **GET** `/api/v1/public/bookings/{booking_ref}` shows the booking with payment status updated.

### 6. Ops console (optional)

- Serve: `cd flysunbird_ops_plus_backend_CONNECTED_ALL/ops_console` then `python -m http.server 8090`.
- Open http://localhost:8090/admin-dashboard.html, log in (e.g. ops@flysunbird.co.tz / ops12345). Set the console’s API base to `http://localhost:8000/api/v1` if required.
- **Check:** You can open the OPS payload / inventory page, pick route + date, and use “Open Booking” or “Copy Link” to get `booking.html?ops=...` and open it in a new tab; the booking flow works as in step 3.

If all steps pass, the system is working as expected: backend, slots, public API, booking UI (with and without ops link), create booking, and mark paid (and optionally ops console).

---

## Quick checklist

- [ ] `docker compose up --build` in `flysunbird_ops_plus_backend_CONNECTED_ALL`  
- [ ] (Optional) Generate slots: Swagger → login → GET slot-rules → POST run-now  
- [ ] GET `/api/v1/public/routes` → get `route_id`  
- [ ] GET `/api/v1/public/ops-link?route_id=...&dateStr=...&currency=USD` → get `opsParam`  
- [ ] Serve fly UI on port 8080 (e.g. `ops_console/fly` with `python -m http.server 8080`)  
- [ ] In browser: `localStorage.setItem("FLYSUNBIRD_API_BASE", "http://localhost:8000/api/v1")`  
- [ ] Open `http://localhost:8080/booking.html?ops=<opsParam>` and complete the flow  
- [ ] Use Swagger for API-only tests and mark-paid  
- [ ] (Optional) Serve ops console on 8090 and use admin-dashboard + OPS payload page  

This matches the README: backend provides data and rules; you open the UI with `booking.html?ops=<opsParam>` and use the same API from both Swagger and the console.

---

## Test as if production (one local run)

Use this to run everything locally the same way you would in production: API + DB + Redis + Celery, then one UI server for admin and booking.

### 1. Start the backend

From `flysunbird_ops_plus_backend_CONNECTED_ALL`:

```bash
docker compose up --build
```

Wait until the API logs show "Uvicorn running" and migrations/seed have run.

### 2. Generate slots

- Open **http://localhost:8000/docs**
- **POST /api/v1/auth/login** → body: `{"email":"ops@flysunbird.co.tz","password":"ops12345"}` → copy `access_token`
- Click **Authorize** → enter `Bearer <access_token>` → Authorize
- **GET /api/v1/ops/slot-rules** → copy one rule `id`
- **POST /api/v1/ops/slot-rules/{rule_id}/run-now** (use that id)

### 3. Serve the UIs (admin + booking)

In a **new terminal**, from `flysunbird_ops_plus_backend_CONNECTED_ALL`:

```bash
python serve_ui.py
```

This serves the ops console on **http://localhost:8090** (CORS is already allowed for 8090). You get:

- **Admin:** http://localhost:8090/admin-dashboard.html  
- **Booking:** http://localhost:8090/fly/booking.html  

### 4. Set API base (once per browser)

Open any of the above URLs, then in the browser console (F12):

```js
localStorage.setItem('FSB_API_BASE', 'http://localhost:8000/api/v1');
localStorage.setItem('FLYSUNBIRD_API_BASE', 'http://localhost:8000/api/v1');
```

Refresh. (Admin uses `FSB_API_BASE`, booking uses `FLYSUNBIRD_API_BASE`.)

### 5. Test admin flow

1. Open http://localhost:8090/login.html  
2. API base: `http://localhost:8000/api/v1`, email: `ops@flysunbird.co.tz`, password: `ops12345` → Sign in  
3. Go to **Bookings Inbox**  
4. **Origin** → pick e.g. "Dar es Salaam Airport" → **Choose date** → calendar shows real availability → click a day  
5. **Choose Inventory Slot** → pick a slot → fill contact + passengers → **Create booking + reserve seats**  
6. Use **Mark Paid** or copy payment link and complete payment (if Cybersource test is configured).

### 6. Test customer flow

1. Open http://localhost:8090/fly/booking.html  
2. **From** → e.g. Dar es Salaam Airport → **Next: Choose date** → calendar with real prices → click a day  
3. **Select** a slot → fill passengers → **Continue to Payment**  
4. Pay (test card if Cybersource test keys are set) or note `bookingRef` and **Mark Paid** in admin.

### 7. Optional: payment test

If you added Cybersource **test** keys to `.env` (`CYBS_MERCHANT_ID`, `CYBS_KEY_ID`, `CYBS_SECRET_KEY_B64`), the payment page can charge a test card. If the gateway returns 404 (REST Payments not enabled), set **`CYBS_SANDBOX=true`** in `.env` to skip the real call and return mock success so you can test the full flow. Otherwise use **Mark Paid** in the ops console to simulate paid.

You now have API, slots, admin calendar, customer calendar, draft creation, and payment/mark-paid working as in a real deployment.
