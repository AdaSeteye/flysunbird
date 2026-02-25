/*
  Booking confirmation (production-ready UI wiring)
  - Fetches from API when ref in URL (GET /public/bookings/{ref})
  - Falls back to sessionStorage state (storage.js)
  - Allows backend/admin to override via window.FSB_CONFIRM_OVERRIDE
  - Provides real user actions: copy ref, download calendar (.ics), share link
*/

const state = initState();
const $ = (s) => document.querySelector(s);
const API_BASE = (window.FLYSUNBIRD_API_BASE || localStorage.getItem("FLYSUNBIRD_API_BASE") || (window.location.origin + "/api/v1")).replace(/\/$/, "");

// Backend/admin can override any display field without changing markup.
const override = window.FSB_CONFIRM_OVERRIDE || null;

// URL overrides (OPS/Admin can pass ?ref=FSB-123&status=paid or pending)
const qp = new URLSearchParams(location.search);
const urlRef = qp.get("ref");
const urlStatus = (qp.get("status") || "").toLowerCase();
if (urlRef) { state.bookingRef = urlRef; saveState(state); }
if (urlStatus) { state.paymentStatus = urlStatus; saveState(state); }

// Data from API (when ref in URL and fetch succeeds)
let apiBooking = null;

function safe(obj, path, fallback) {
  try {
    return path.split('.').reduce((acc, k) => (acc && acc[k] !== undefined ? acc[k] : undefined), obj) ?? fallback;
  } catch {
    return fallback;
  }
}

async function fetchTzsRate() {
  if (!API_BASE) return 2450;
  try {
    const res = await fetch(API_BASE + "/public/fx-rate");
    if (res.ok) { const d = await res.json(); return Number(d.usdToTzs || d.rate) || 2450; }
  } catch (_) {}
  return 2450;
}

function fmtMoney(usd, cur, tzsRate) {
  const TZS_RATE = tzsRate || 2450;
  const n = Number(usd || 0);
  if ((cur || "USD").toUpperCase() === "TZS") return `TZS ${Math.round(n * TZS_RATE).toLocaleString()}`;
  return `$${Math.round(n).toLocaleString()}`;
}

function calcTotalUSD(){
  const per = Number(state.selected?.priceUSD || 0);
  const pax = (state.passengers?.length || state.pax || 1);
  return per * pax;
}

function getData(tzsRate) {
  const p0 = (apiBooking && apiBooking.passengers && apiBooking.passengers[0]) || (state.passengers && state.passengers[0]) || {};
  const passengers = apiBooking
    ? (apiBooking.passengers || []).map(p => ({ first: p.first || "", last: p.last || "", phone: p.phone || "", dob: p.dob || "", nationality: p.nationality || "", type: "Passenger" }))
    : (Array.isArray(state.passengers) ? state.passengers : []).map(p => ({ first: p.first || "", last: p.last || "", phone: p.phone || "", dob: p.dob || p.dobISO || "", nationality: p.nationality || "", type: p.type || "Passenger" }));

  const te = (apiBooking && apiBooking.timeEntry) || {};
  const trip = apiBooking
    ? {
        fromCity: apiBooking.from || te.from_label || "—",
        fromAirport: "",
        toCity: apiBooking.to || te.to_label || "—",
        toAirport: "",
        date: apiBooking.dateStr || te.date_str || "—",
        dep: te.start || "—",
        arr: te.end || "—",
        flightNo: te.flightNo || te.flight_no || "FSB",
        cabin: te.cabin || "Economy",
        baggage: "Cabin baggage",
        checkin: "Opens 24h before"
      }
    : {
        fromCity: state.from || "—",
        fromAirport: "",
        toCity: state.to || "—",
        toAirport: "",
        date: state.selected?.dateStr || "—",
        dep: state.selected?.start || "—",
        arr: state.selected?.end || "—",
        flightNo: state.selected?.flightNo || "FSB",
        cabin: state.selected?.cabin || "Economy",
        baggage: state.selected?.baggage || "Cabin baggage",
        checkin: "Opens 24h before"
      };

  const paySt = (apiBooking && (apiBooking.paymentStatus || "").toLowerCase()) || (state.paymentStatus || "pending").toLowerCase();
  const paymentStatus = paySt;
  const totalUSD = apiBooking ? (Number(apiBooking.totalUSD) || 0) : calcTotalUSD();
  const currency = (apiBooking && apiBooking.currency) || state.currency || "USD";
  const payment = {
    status: paymentStatus === "paid" ? "PAID" : "PENDING",
    method: (state.paymentMethod || "Card"),
    amount: fmtMoney(totalUSD, currency, tzsRate)
  };

  const data = {
    reference: (apiBooking && apiBooking.bookingRef) || state.bookingRef || "—",
    payment,
    trip,
    passengers
  };

  if (!override) return data;

  return {
    reference: safe(override, "reference", data.reference),
    payment: {
      status: safe(override, "payment.status", data.payment.status),
      method: safe(override, "payment.method", data.payment.method),
      amount: safe(override, "payment.amount", data.payment.amount),
    },
    trip: {
      ...data.trip,
      ...(override.trip || {})
    },
    passengers: Array.isArray(override.passengers) ? override.passengers : data.passengers
  };
}

function setText(id, value){
  const el = document.getElementById(id);
  if (el) el.textContent = value;
}

function render(tzsRate) {
  const data = getData(tzsRate);

  // Empty state hint
  const emptyHint = document.getElementById("emptyStateHint");
  if (emptyHint) {
    const refEmpty = !data.reference || data.reference === "—";
    const tripEmpty = !data.trip.fromCity || data.trip.fromCity === "—";
    emptyHint.style.display = (refEmpty && tripEmpty) ? "block" : "none";
  }

  // Status pill
  const pill = $("#statusPill");
  const pillDot = $("#statusDot");
  const pillText = $("#statusText");
  const isPaid = String(data.payment.status).toUpperCase() === "PAID";
  pill.classList.remove("success","pending");
  pill.classList.add(isPaid ? "success" : "pending");
  if (pillDot) pillDot.style.background = isPaid ? "#12b76a" : "#f59e0b";
  if (pillText) pillText.textContent = isPaid ? "Booking Confirmed" : "Booking Pending";

  // Status note + ticket button
  const note = $("#statusNote");
  const ticketBtn = $("#ticketBtn");
  if (note){
    note.textContent = isPaid
      ? "Your payment is confirmed. You can view/print your ticket."
      : "This booking is not confirmed yet. Complete payment from OPS/Admin to issue the ticket.";
  }
  if (ticketBtn){
    ticketBtn.disabled = !isPaid;
    ticketBtn.classList.toggle("disabled", !isPaid);
    ticketBtn.onclick = () => {
      if (!isPaid) return;
      const ref = encodeURIComponent(data.reference || "");
      window.location.href = `ticket.html?ref=${ref}`;
    };
  }


  setText("refCode", data.reference);
  setText("payStatus", data.payment.status);
  setText("payMethod", data.payment.method);
  setText("payAmount", data.payment.amount);

  const payStatusEl = $("#payStatus");
  if (payStatusEl){
    payStatusEl.classList.remove("paid","pending");
    payStatusEl.classList.add(isPaid ? "paid" : "pending");
  }

  // Trip
  setText("fromCity", data.trip.fromCity);
  setText("fromAirport", data.trip.fromAirport || "");
  setText("toCity", data.trip.toCity);
  setText("toAirport", data.trip.toAirport || "");
  setText("flightDate", data.trip.date);
  setText("depTime", data.trip.dep);
  setText("arrTime", data.trip.arr);
  setText("flightNo", data.trip.flightNo);
  setText("baggage", data.trip.baggage);
  setText("checkin", data.trip.checkin);
  setText("cabinBadge", data.trip.cabin);

  // Passengers
  const paxList = $("#paxList");
  const paxCount = $("#paxCount");
  const pax = Array.isArray(data.passengers) ? data.passengers : [];
  if (paxCount) paxCount.textContent = String(pax.length || 1);

  if (paxList){
    if (!pax.length){
      paxList.innerHTML = `<div class="pax-item"><div><div class="pax-name">Passenger</div><div class="pax-meta">Details will appear after you add passengers.</div></div><div class="pax-tag">—</div></div>`;
    } else {
      paxList.innerHTML = pax.map((p, idx)=>{
        const full = `${(p.first||"").trim()} ${(p.last||"").trim()}`.trim() || `Passenger ${idx+1}`;
        const metaParts = [];
        if (p.dob) metaParts.push(`DOB: ${p.dob}`);
        if (p.phone) metaParts.push(`Phone: ${p.phone}`);
        if (p.nationality) metaParts.push(p.nationality);
        return `
          <div class="pax-item">
            <div>
              <div class="pax-name">${escapeHtml(full)}</div>
              <div class="pax-meta">${escapeHtml(metaParts.join(" • ") || "—")}</div>
            </div>
            <div class="pax-tag">${escapeHtml(p.type || "Passenger")}</div>
          </div>
        `;
      }).join("");
    }
  }

  // Manage booking: go to confirmation with ref (view status / ticket)
  const manageBtn = $("#manageBtn");
  if (manageBtn){
    manageBtn.addEventListener("click", ()=>{
      const ref = encodeURIComponent(data.reference || "");
      window.location.href = `confirmation.html?ref=${ref}`;
    });
  }

  // Back to payment
  const backPay = $("#backToPaymentBtn");
  if (backPay){
    backPay.addEventListener("click", ()=> window.location.href = "payment.html");
  }

  // New booking (reset)
  const newBtn = $("#newBookingBtn");
  if (newBtn){
    newBtn.addEventListener("click", ()=>{
      const keepCur = state.currency;
      saveState({ currency: keepCur });
      window.location.href = "booking.html";
    });
  }

  // Copy ref (two buttons)
  const copy1 = $("#copyRefBtn");
  const copy2 = $("#copyRefBtn2");
  [copy1, copy2].forEach(btn=>{
    if (!btn) return;
    btn.addEventListener("click", async ()=>{
      await copyText(data.reference || "");
      const prev = btn.textContent;
      btn.textContent = "Copied";
      setTimeout(()=> btn.textContent = prev, 1200);
    });
  });

  // Download Itinerary / Invoice (html snapshots – backend can swap to PDF later)
  const itinBtn = $("#downloadItinBtn");
  if (itinBtn){
    itinBtn.addEventListener("click", ()=>{
      const html = buildItineraryHTML(data);
      downloadFile(`itinerary_${data.reference||"booking"}.html`, html, "text/html");
    });
  }

  const invBtn = $("#downloadInvoiceBtn");
  if (invBtn){
    invBtn.addEventListener("click", ()=>{
      const html = buildInvoiceHTML(data);
      downloadFile(`receipt_${data.reference||"booking"}.html`, html, "text/html");
    });
  }

  // Add to calendar (.ics) – real feature
  const calBtn = $("#addCalendarBtn");
  if (calBtn){
    calBtn.addEventListener("click", ()=>{
      const ics = buildICS(data);
      downloadFile(`flysunbird_${data.reference||"booking"}.ics`, ics, "text/calendar");
    });
  }

  // Share (native share if available, else copy link)
  const shareBtn = $("#shareBtn");
  if (shareBtn){
    shareBtn.addEventListener("click", async ()=>{
      const link = `${window.location.origin}${window.location.pathname}?ref=${encodeURIComponent(data.reference||"")}`;
      const text = `FlySunbird booking reference: ${data.reference}`;
      try{
        if (navigator.share){
          await navigator.share({ title: "FlySunbird booking", text, url: link });
        } else {
          await copyText(`${text}\n${link}`);
          const prev = shareBtn.textContent;
          shareBtn.textContent = "Copied";
          setTimeout(()=> shareBtn.textContent = prev, 1200);
        }
      }catch{
        // ignore
      }
    });
  }
}

function escapeHtml(str){
  return String(str ?? "").replace(/[&<>"]/g, (c)=>({
    "&":"&amp;",
    "<":"&lt;",
    ">":"&gt;",
    '"':"&quot;"
  }[c]));
}

async function copyText(text){
  try{
    await navigator.clipboard.writeText(text);
  }catch{
    // fallback
    const ta = document.createElement("textarea");
    ta.value = text;
    ta.style.position = "fixed";
    ta.style.left = "-9999px";
    document.body.appendChild(ta);
    ta.select();
    document.execCommand("copy");
    ta.remove();
  }
}

function downloadFile(filename, content, mime){
  const blob = new Blob([content], { type: mime || "application/octet-stream" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(()=> URL.revokeObjectURL(url), 500);
}

function buildICS(data){
  // We don't have true timestamps in this UI flow, so we store all-day event for the selected date string.
  // Backend can replace with real times.
  const ref = (data.reference || "").replace(/\s+/g, "");
  const dateGuess = guessICSDate(data.trip.date);
  const dt = dateGuess || todayICS();
  const uid = `${ref || "FSB"}-${Date.now()}@flysunbird`;
  const summary = `FlySunbird Trip (${ref || "Booking"})`;
  const location = `${data.trip.fromCity} → ${data.trip.toCity}`;
  const desc = `Booking reference: ${data.reference}\nFlight: ${data.trip.flightNo}\nDepart: ${data.trip.dep}\nArrive: ${data.trip.arr}`;

  return [
    "BEGIN:VCALENDAR",
    "VERSION:2.0",
    "PRODID:-//FlySunbird//Booking//EN",
    "CALSCALE:GREGORIAN",
    "METHOD:PUBLISH",
    "BEGIN:VEVENT",
    `UID:${uid}`,
    `DTSTAMP:${nowICS()}`,
    `DTSTART;VALUE=DATE:${dt}`,
    `DTEND;VALUE=DATE:${dt}`,
    `SUMMARY:${escapeICS(summary)}`,
    `LOCATION:${escapeICS(location)}`,
    `DESCRIPTION:${escapeICS(desc)}`,
    "END:VEVENT",
    "END:VCALENDAR"
  ].join("\r\n");
}

function escapeICS(s){
  return String(s || "").replace(/\\/g,"\\\\").replace(/\n/g,"\\n").replace(/,/g,"\\,").replace(/;/g,"\\;");
}

function nowICS(){
  const d = new Date();
  const pad = (n)=>String(n).padStart(2,'0');
  return `${d.getUTCFullYear()}${pad(d.getUTCMonth()+1)}${pad(d.getUTCDate())}T${pad(d.getUTCHours())}${pad(d.getUTCMinutes())}${pad(d.getUTCSeconds())}Z`;
}

function todayICS(){
  const d = new Date();
  const pad = (n)=>String(n).padStart(2,'0');
  return `${d.getUTCFullYear()}${pad(d.getUTCMonth()+1)}${pad(d.getUTCDate())}`;
}

function guessICSDate(label){
  // Accept formats like "Feb 01, 2026" or "2026-02-01"
  const s = String(label||"").trim();
  if (!s) return null;
  if (/^\d{4}-\d{2}-\d{2}$/.test(s)) return s.replaceAll("-", "");
  const m = s.match(/^(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+(\d{1,2}),\s*(\d{4})$/i);
  if (!m) return null;
  const monthMap = {jan:"01",feb:"02",mar:"03",apr:"04",may:"05",jun:"06",jul:"07",aug:"08",sep:"09",oct:"10",nov:"11",dec:"12"};
  const mm = monthMap[m[1].toLowerCase()];
  const dd = String(m[2]).padStart(2,'0');
  const yyyy = m[3];
  return `${yyyy}${mm}${dd}`;
}

function buildItineraryHTML(data){
  return `<!doctype html><html><head><meta charset="utf-8"/><meta name="viewport" content="width=device-width,initial-scale=1"/>
  <title>Itinerary - ${escapeHtml(data.reference)}</title>
  <style>body{font-family:Arial,sans-serif;margin:24px;color:#111}h1{margin:0 0 6px}small{color:#555}
  .box{border:1px solid #ddd;border-radius:12px;padding:14px;margin-top:14px}
  .grid{display:grid;grid-template-columns:1fr 1fr;gap:10px}
  @media(max-width:620px){.grid{grid-template-columns:1fr}}
  </style></head><body>
  <h1>FlySunbird Itinerary</h1>
  <small>Booking reference: <b>${escapeHtml(data.reference)}</b></small>
  <div class="box">
    <h3 style="margin:0 0 8px">Trip</h3>
    <div class="grid">
      <div><small>From</small><div><b>${escapeHtml(data.trip.fromCity)}</b></div></div>
      <div><small>To</small><div><b>${escapeHtml(data.trip.toCity)}</b></div></div>
      <div><small>Date</small><div><b>${escapeHtml(data.trip.date)}</b></div></div>
      <div><small>Flight</small><div><b>${escapeHtml(data.trip.flightNo)}</b></div></div>
      <div><small>Departure</small><div><b>${escapeHtml(data.trip.dep)}</b></div></div>
      <div><small>Arrival</small><div><b>${escapeHtml(data.trip.arr)}</b></div></div>
      <div><small>Cabin</small><div><b>${escapeHtml(data.trip.cabin)}</b></div></div>
      <div><small>Baggage</small><div><b>${escapeHtml(data.trip.baggage)}</b></div></div>
    </div>
  </div>
  <div class="box">
    <h3 style="margin:0 0 8px">Passengers</h3>
    <ul>${(data.passengers||[]).map(p=>`<li>${escapeHtml(((p.first||'')+' '+(p.last||'')).trim()||'Passenger')} ${p.dob?`<small>(DOB ${escapeHtml(p.dob)})</small>`:''}</li>`).join('') || '<li>—</li>'}</ul>
  </div>
  </body></html>`;
}

function buildInvoiceHTML(data){
  return `<!doctype html><html><head><meta charset="utf-8"/><meta name="viewport" content="width=device-width,initial-scale=1"/>
  <title>Receipt - ${escapeHtml(data.reference)}</title>
  <style>body{font-family:Arial,sans-serif;margin:24px;color:#111}h1{margin:0 0 6px}small{color:#555}
  .box{border:1px solid #ddd;border-radius:12px;padding:14px;margin-top:14px}
  .row{display:flex;justify-content:space-between;gap:12px;flex-wrap:wrap}
  </style></head><body>
  <h1>FlySunbird Receipt</h1>
  <small>Booking reference: <b>${escapeHtml(data.reference)}</b></small>
  <div class="box">
    <div class="row"><div><small>Status</small><div><b>${escapeHtml(data.payment.status)}</b></div></div><div><small>Method</small><div><b>${escapeHtml(data.payment.method)}</b></div></div></div>
    <div style="height:12px"></div>
    <div class="row"><div><small>Amount</small><div><b>${escapeHtml(data.payment.amount)}</b></div></div><div><small>Flight</small><div><b>${escapeHtml(data.trip.flightNo)}</b></div></div></div>
  </div>
  </body></html>`;
}

(async function init() {
  let tzsRate = 2450;
  if (urlRef && API_BASE) {
    try {
      const res = await fetch(API_BASE + "/public/bookings/" + encodeURIComponent(urlRef));
      if (res.ok) {
        apiBooking = await res.json();
        state.bookingRef = apiBooking.bookingRef || urlRef;
        state.paymentStatus = (apiBooking.paymentStatus || "pending").toLowerCase();
        state.from = apiBooking.from || (apiBooking.timeEntry && apiBooking.timeEntry.from_label);
        state.to = apiBooking.to || (apiBooking.timeEntry && apiBooking.timeEntry.to_label);
        saveState(state);
      }
    } catch (_) {}
    tzsRate = await fetchTzsRate();
  }
  render(tzsRate);
})();
