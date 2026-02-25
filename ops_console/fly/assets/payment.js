const state = initState();
const $ = (s)=>document.querySelector(s);
const $$ = (s)=>Array.from(document.querySelectorAll(s));

let TZS_RATE = 2450;
const fmt = (usd, cur) => (cur === "USD" ? `$${usd.toFixed(0)}` : `TZS ${(usd*TZS_RATE|0).toLocaleString()}`);
async function loadTzsRate() {
  const base = (window.FLYSUNBIRD_API_BASE || localStorage.getItem("FLYSUNBIRD_API_BASE") || "").replace(/\/$/, "");
  if (!base) return;
  try {
    const res = await fetch(base + "/public/fx-rate");
    if (res.ok) { const d = await res.json(); TZS_RATE = Number(d.usdToTzs) || 2450; }
  } catch (_) {}
}

// Optional: configure your backend API base via:
// 1) localStorage.setItem("FLYSUNBIRD_API_BASE","https://api.flysunbird.co.tz")
// 2) window.FLYSUNBIRD_API_BASE = "https://api.flysunbird.co.tz"
const API_BASE =
  (window.FLYSUNBIRD_API_BASE || localStorage.getItem("FLYSUNBIRD_API_BASE") || (window.location.origin ? window.location.origin + "/api/v1" : "")).replace(/\/$/, "");

const qp = new URLSearchParams(typeof location !== "undefined" && location.search || "");
const urlRef = qp.get("bookingRef") || qp.get("ref");
const urlAmount = qp.get("amount");
const urlCurrency = qp.get("currency") || "USD";

async function hydrateFromUrlOrRedirect() {
  if (state.selected && Array.isArray(state.passengers) && state.passengers.length) return;
  if (urlRef && API_BASE) {
    try {
      const res = await fetch(API_BASE + "/public/bookings/" + encodeURIComponent(urlRef));
      if (res.ok) {
        const b = await res.json();
        if ((b.paymentStatus || "").toLowerCase() === "paid") {
          window.location.href = "confirmation.html?ref=" + encodeURIComponent(urlRef);
          return;
        }
        const te = b.timeEntry || {};
        state.bookingRef = b.bookingRef || urlRef;
        state.from = b.from || te.from_label || "";
        state.to = b.to || te.to_label || "";
        const total = Number(b.totalUSD) || Number(urlAmount) || 0;
        const paxNum = Math.max(1, b.pax || 1);
        state.selected = {
          timeEntryId: b.timeEntryId || te.id,
          dateStr: b.dateStr || te.date_str || "",
          start: te.start || "",
          end: te.end || "",
          priceUSD: Number(b.unitPriceUSD) || (total / paxNum) || Number(urlAmount) || 0,
          flightNo: te.flightNo || te.flight_no || "FSB",
          cabin: te.cabin || "Economy"
        };
        const contactEmail = b.contactEmail || "";
        state.passengers = (b.passengers || []).map((p, i) => ({
          first: p.first || "",
          last: p.last || "",
          phone: p.phone || "",
          email: i === 0 ? (p.email || contactEmail || "") : (p.email || "")
        }));
        if (state.passengers.length === 0) state.passengers = [{ first: "", last: "", phone: "", email: contactEmail || "" }];
        state.pax = b.pax || state.passengers.length || 1;
        state.currency = urlCurrency || b.currency || "USD";
        state.totalUSD = total;
        saveState(state);
        return;
      }
    } catch (_) {}
  }
  if (!state.selected || !Array.isArray(state.passengers) || !state.passengers.length) {
    if (urlRef) window.location.href = "booking.html?ref=" + encodeURIComponent(urlRef);
    else window.location.href = "booking.html";
  }
}

function calcTotal(){
  if (state.totalUSD != null && Number(state.totalUSD) > 0) return Number(state.totalUSD);
  const per = state.selected && state.selected.priceUSD != null ? state.selected.priceUSD : 0;
  const pax = state.pax || (state.passengers && state.passengers.length) || 1;
  return per * pax || 0;
}

function renderSummary(){
  const sum = $("#summary");
  const total = calcTotal();
  const p0 = state.passengers[0] || {};
  sum.innerHTML = `
    <div class="head">
      <div class="t">💳 Checkout</div>
      <div class="pill">${state.currency}</div>
    </div>
    <div class="body">
      <div class="line"><div class="k">Booking reference</div><div class="v"><strong>${state.bookingRef}</strong></div></div>
      <div class="line"><div class="k">🛩️ From</div><div class="v">${state.from || "—"}</div></div>
      <div class="line"><div class="k">📅 Date</div><div class="v">${state.selected.dateStr}</div></div>
      <div class="line"><div class="k">⏰ Time</div><div class="v">${state.selected.start}–${state.selected.end}</div></div>
      <div class="div"></div>
      <div class="line"><div class="k">Passengers</div><div class="v">${state.passengers.length}</div></div>
      <div class="line"><div class="k">Contact</div><div class="v">${(p0.first||"")} ${(p0.last||"")}</div></div>
      <div class="line"><div class="k">Phone</div><div class="v">${p0.phone || "—"}</div></div>
      <div class="div"></div>
      <div class="total"><div class="k">Total</div><div class="v">${fmt(total, state.currency)}</div></div>
      <div class="hint">Pay with Stripe (redirect) or use Selcom for local/demo.</div>
    </div>
  `;
}

function setMethod(method){
  state.paymentMethod = method; saveState(state);
  $$(".method").forEach(m=> m.classList.toggle("active", m.dataset.method === method));
  $$(".pay-form").forEach(f=> f.style.display = (f.dataset.method === method) ? "block" : "none");
}

$("#backPassengers").addEventListener("click", ()=> window.location.href = "passenger.html");
$("#backBooking").addEventListener("click", ()=> window.location.href = "booking.html");

$$(".method").forEach(m=>{
  m.addEventListener("click", ()=> setMethod(m.dataset.method));
  m.addEventListener("keydown", (e)=>{
    if(e.key === "Enter" || e.key === " "){ e.preventDefault(); setMethod(m.dataset.method); }
  });
});

// booking reference (reserve early so the user sees it even before paying)
function makeBookingRef(){
  const d = new Date();
  const y = d.getFullYear();
  const m = String(d.getMonth()+1).padStart(2,'0');
  const day = String(d.getDate()).padStart(2,'0');
  const rnd = Math.random().toString(36).slice(2,6).toUpperCase();
  return `FSB-${y}${m}${day}-${rnd}`;
}

// ensure we always have a reference visible
if(!state.bookingRef){
  state.bookingRef = urlRef || makeBookingRef();
  state.paymentStatus = state.paymentStatus || "pending";
  saveState(state);
}

function validateRequired(method){
  const form = document.querySelector(`.pay-form[data-method="${method}"]`);
  if(!form) return { ok:true };
  const req = Array.from(form.querySelectorAll("[data-required='1']"));
  const missing = req.filter(i=> !String(i.value||"").trim());
  if(missing.length){
    missing[0].focus();
    return { ok:false, msg:"Please fill all required payment fields." };
  }
  return { ok:true };
}

$("#payNow").addEventListener("click", async ()=>{
  const method = state.paymentMethod || "stripe";

  const v = validateRequired(method);
  if(!v.ok){
    alert(v.msg);
    return;
  }

  // Stripe Checkout (redirect): create session and redirect to Stripe
  if(method === "stripe"){
    try {
      $("#payNow").disabled = true;
      $("#payNow").textContent = "Redirecting to Stripe…";
      if(!API_BASE){
        alert("API base not configured. Set FLYSUNBIRD_API_BASE.");
        return;
      }
      const res = await fetch(API_BASE + "/public/payments/stripe/create-checkout-session", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          bookingRef: state.bookingRef,
          currency: state.currency || "USD"
        })
      });
      const data = await res.json().catch(() => ({}));
      if(!res.ok){
        const msg = (data.detail != null || data.message != null) ? (data.detail || data.message) : "Payment request failed";
        throw new Error(typeof msg === "string" ? msg : JSON.stringify(msg));
      }
      if(data.paymentStatus === "paid" || !data.url){
        window.location.href = "confirmation.html?ref=" + encodeURIComponent(state.bookingRef || "");
        return;
      }
      window.location.href = data.url;
      return;
    } catch(e){
      console.error(e);
      alert(e && e.message ? e.message : "Could not start Stripe checkout.");
    } finally {
      $("#payNow").disabled = false;
      $("#payNow").textContent = "Pay now";
    }
    return;
  }

  // Selcom: UI-only / demo (no backend charge).
  if(method === "selcom"){
    state.paymentStatus = "paid";
    state.paidAt = new Date().toISOString();
    state.paymentProvider = "selcom";
    saveState(state);
    window.location.href = "confirmation.html?ref=" + encodeURIComponent(state.bookingRef || "");
    return;
  }
});

(async function init(){
  await hydrateFromUrlOrRedirect();
  if (state.selected && Array.isArray(state.passengers) && state.passengers.length) {
    renderSummary();
    loadTzsRate().then(() => { if (typeof renderSummary === 'function') renderSummary(); });
    setMethod(state.paymentMethod || "stripe");
  }
})();
