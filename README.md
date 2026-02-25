# flysunbird# FlySunbird Enterprise Backend (UI Contract Locked)

This backend **does not modify** your UI. It only provides data & rules.

## UI Contract (from `fly.zip`)
Your `booking.js` reads OPS payload from:
- `sessionStorage["flysunbird_ops_payload_v1"]`, OR
- `booking.html?ops=<base64url(json)>`

Payload shape must be:
```json
{
  "from":"Dar es Salaam (DAR)",
  "to":"Zanzibar (ZNZ)",
  "region":"Tanzania",
  "currency":"USD",
  "dateStr":"2026-02-03",
  "slots":[{"start":"09:00","end":"10:10","priceUSD":220,"seatsAvailable":3,"flightNo":"FSB101","cabin":"Economy"}]
}
```

This backend serves that shape **exactly**.

## Run locally
```bash
docker compose up --build
```

API: http://localhost:8000  
Docs: http://localhost:8000/docs  
MailHog: http://localhost:8025

## Get OPS payload for UI
1) Find route_id (seed creates one default route DAR->ZNZ style labels).
2) Call:

`GET /api/v1/public/ops-link?route_id=<ROUTE_ID>&dateStr=2026-02-07&currency=USD`

It returns:
```json
{"opsParam":"<base64url...>"}
```

Open your UI without editing it:
`booking.html?ops=<opsParam>`

## Booking & payment (backend)
- Create booking: `POST /api/v1/public/bookings`
- Mark paid (OPS/Admin): `POST /api/v1/ops/bookings/{booking_ref}/mark-paid?pilot_email=pilot@something.com`

Seat-hold expiry runs automatically (Celery beat every minute).
Slot generation runs automatically (every 6 hours) using `slot_rules`.

## Default users (local/dev)

Seeded accounts are defined in `app/seed.py`. Use those emails with the passwords set there (change them in production).
