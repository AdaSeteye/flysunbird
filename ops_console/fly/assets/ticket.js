/* Ticket page
   - Reads session state (storage.js) or fetches GET /public/bookings/{ref} when ref in URL
   - URL params override: ?ref=FSB-123&status=paid&from=...&to=...
*/
const state = initState();
const $ = (s) => document.querySelector(s);
const API_BASE = (window.FLYSUNBIRD_API_BASE || localStorage.getItem("FLYSUNBIRD_API_BASE") || (window.location && window.location.origin ? window.location.origin + "/api/v1" : "")).replace(/\/$/, "");

function qp(name){
  try { return new URLSearchParams(location.search).get(name); } catch { return null; }
}

function setText(id, val){
  var el = document.getElementById(id);
  if (el) el.textContent = (val === undefined || val === null || val === "") ? "—" : String(val);
}

function renderQR(ref){
  var qr = document.getElementById("tQR");
  if (!qr) return;
  qr.innerHTML = "";
  var ticketUrl = API_BASE && ref && ref !== "—" ? (API_BASE + "/public/bookings/" + encodeURIComponent(ref) + "/ticket") : null;
  if (ticketUrl && typeof QRCode !== "undefined") {
    try { new QRCode(qr, { text: ticketUrl, width: 110, height: 110 }); } catch (e) { qr.textContent = ref; }
  } else {
    qr.textContent = ref || "—";
  }
}

function renderTicket(data){
  const ref = data.bookingRef || data.reference || "—";
  const st = (data.paymentStatus || data.payment_status || "pending").toLowerCase();
  const statusLabel = (st === "paid" || st === "confirmed") ? "CONFIRMED" : "PENDING";
  const te = data.timeEntry || {};
  const from = data.from || te.from_label || "—";
  const to = data.to || te.to_label || "—";
  const date = data.dateStr || data.date || te.date_str || "—";
  const dep = te.start || "—";
  const arr = te.end || "—";
  const flight = te.flightNo || te.flight_no || "FSB";
  const pax0 = (data.passengers && data.passengers[0]) ? data.passengers[0] : null;
  const passenger = pax0 ? `${(pax0.first||"").trim()} ${(pax0.last||"").trim()}`.trim() || "—" : "—";

  setText("tRef", ref);
  setText("tStatus", statusLabel);
  setText("tFrom", from);
  setText("tTo", to);
  setText("tDate", date);
  setText("tDep", dep);
  setText("tArr", arr);
  setText("tFlight", flight);
  setText("tPassenger", passenger);

  renderQR(ref);

  const warn = document.getElementById("tWarn");
  if (warn){
    warn.textContent = (statusLabel === "CONFIRMED")
      ? "Ticket confirmed. Print / Save PDF for boarding."
      : "This ticket is not confirmed yet. Complete payment / OPS confirmation to issue the final ticket.";
  }

  const printBtn = document.getElementById("printBtn");
  if (printBtn) printBtn.onclick = () => window.print();

  const dlBtn = document.getElementById("downloadTicketBtn");
  if (dlBtn) {
    dlBtn.style.display = statusLabel === "CONFIRMED" && API_BASE ? "inline-block" : "none";
    dlBtn.onclick = () => {
      window.open(API_BASE + "/public/bookings/" + encodeURIComponent(ref) + "/ticket", "_blank");
    };
  }
}

(async function hydrate(){
  const urlRef = qp("ref");
  if (urlRef && API_BASE) {
    try {
      const res = await fetch(API_BASE + "/public/bookings/" + encodeURIComponent(urlRef));
      if (res.ok) {
        const data = await res.json();
        renderTicket(data);
        return;
      }
    } catch (e) { /* fallback to state/params */ }
  }

  const ref = urlRef || state.bookingRef || "—";
  const st = (qp("status") || state.paymentStatus || "pending").toLowerCase();
  const statusLabel = (st === "paid" || st === "confirmed") ? "CONFIRMED" : "PENDING";
  const from = qp("from") || state.from || "—";
  const to = qp("to") || state.to || "—";
  const date = qp("date") || state.selected?.dateStr || state.date || "—";
  const dep = qp("dep") || state.selected?.start || "—";
  const arr = qp("arr") || state.selected?.end || "—";
  const flight = qp("flight") || state.selected?.flightNo || "FSB";
  const pax0 = (Array.isArray(state.passengers) && state.passengers[0]) ? state.passengers[0] : null;
  const passenger = qp("passenger") || (pax0 ? `${pax0.firstName || pax0.first || ""} ${pax0.lastName || pax0.last || ""}`.trim() : "") || "—";

  setText("tRef", ref);
  setText("tStatus", statusLabel);
  setText("tFrom", from);
  setText("tTo", to);
  setText("tDate", date);
  setText("tDep", dep);
  setText("tArr", arr);
  setText("tFlight", flight);
  setText("tPassenger", passenger);

  renderQR(ref);

  const warn = document.getElementById("tWarn");
  if (warn) warn.textContent = (statusLabel === "CONFIRMED") ? "Ticket confirmed. Print / Save PDF for boarding." : "This ticket is not confirmed yet. Complete payment / OPS confirmation to issue the final ticket.";

  const printBtn = document.getElementById("printBtn");
  if (printBtn) printBtn.onclick = () => window.print();

  const dlBtn = document.getElementById("downloadTicketBtn");
  if (dlBtn) {
    dlBtn.style.display = (statusLabel === "CONFIRMED" && API_BASE) ? "inline-block" : "none";
    dlBtn.onclick = () => { if (ref && ref !== "—") window.open(API_BASE + "/public/bookings/" + encodeURIComponent(ref) + "/ticket", "_blank"); };
  }
})();
