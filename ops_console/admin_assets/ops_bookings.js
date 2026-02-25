// Ops-side storage for captured bookings (until backend is wired).
// This is NOT "test codes". It's the same fields your client collects.
// Later we swap these functions to call FastAPI endpoints without changing UI.

const OpsBookings = (() => {
  const KEY = "flysunbird_ops_bookings_v1";
  function getApiBase() { return (window.API_BASE || localStorage.getItem("FSB_API_BASE") || "").replace(/\/$/, ""); }
  function getToken() { return localStorage.getItem("FSB_TOKEN") || ""; }
  async function refreshAccessToken() {
    var base = getApiBase(), ref = localStorage.getItem("FSB_REFRESH_TOKEN");
    if (!base || !ref) return false;
    try {
      var r = await fetch(base + "/auth/refresh?refresh_token=" + encodeURIComponent(ref), { method: "POST", headers: { "Content-Type": "application/json" } });
      if (!r.ok) return false;
      var data = await r.json();
      if (data.access_token) { localStorage.setItem("FSB_TOKEN", data.access_token); if (data.refresh_token) localStorage.setItem("FSB_REFRESH_TOKEN", data.refresh_token); return true; }
    } catch (e) {}
    return false;
  }
  const api = async (method, path, body, _retried) => {
    var API_BASE = getApiBase(), API_TOKEN = getToken();
    if (!API_BASE) throw new Error("API base not set. Sign in from the login page and use an API URL that includes /api/v1 (e.g. http://localhost:8000/api/v1).");
    var res = await fetch(API_BASE + path, { method, headers: { "Content-Type": "application/json", ...(API_TOKEN ? { "Authorization": "Bearer " + API_TOKEN } : {}) }, body: body ? JSON.stringify(body) : undefined });
    if (res.status === 401 && !_retried && await refreshAccessToken()) return api(method, path, body, true);
    if (!res.ok) {
      var text = await res.text();
      if (res.status === 401) throw new Error("Session expired or invalid. Please sign in again from the login page.");
      if (res.status === 403) throw new Error("You don't have permission to view bookings. Your role must be ops, admin, superadmin, or finance.");
      var detail = text;
      try { var j = JSON.parse(text); if (j && j.detail) detail = typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail); } catch (_) {}
      throw new Error(detail || res.statusText);
    }
    return await res.json();
  };

  const uid = () => `bk_${Math.random().toString(16).slice(2)}_${Date.now().toString(16)}`;

  function load(){
    try{
      const raw = localStorage.getItem(KEY);
      return raw ? JSON.parse(raw) : [];
    }catch(e){ return []; }
  }
  function save(list){ localStorage.setItem(KEY, JSON.stringify(list)); }

  function add(b){
    const list = load();
    const now = new Date().toISOString();
    const x = {
      id: uid(),
      createdAt: now,
      status: "PENDING", // PENDING | CONFIRMED | CANCELLED | FAILED
      paymentStatus: "UNPAID", // UNPAID | PAID | FAILED | REFUNDED
      ...b
    };
    list.unshift(x);
    save(list);
    return x;
  }

  function update(id, patch){
    const list = load();
    const x = list.find(i=>i.id===id);
    if(!x) return null;
    Object.assign(x, patch, {updatedAt: new Date().toISOString()});
    save(list);
    return x;
  }

  function remove(id){
    const list = load().filter(i=>i.id!==id);
    save(list);
    return true;
  }

async function listRemote(){
  return await api("GET","/ops/bookings");
}
async function getRemote(ref){
  return await api("GET", `/ops/bookings/${ref}`);
}
async function createDraftRemote(payload){
  return await api("POST","/ops/bookings/create-draft", payload);
}
async function paymentLinkRemote(ref){
  return await api("GET", `/ops/bookings/${ref}/payment-link`);
}
async function markPaidRemote(ref, pilotEmail){
  const q = pilotEmail ? `?pilot_email=${encodeURIComponent(pilotEmail)}` : "";
  return await api("POST", `/ops/bookings/${encodeURIComponent(ref)}/mark-paid${q}`);
}
async function cancelRemote(ref, body){
  const payload = body && typeof body === "object"
    ? { decision_note: body.decision_note || body.reason || "", refund_amount_usd: Number(body.refund_amount_usd) || 0, approve: true }
    : { decision_note: "", refund_amount_usd: 0, approve: true };
  return await api("POST", `/ops/bookings/${encodeURIComponent(ref)}/cancel`, payload);
}
async function refundRemote(ref, payload){
  return await api("POST", `/ops/bookings/${ref}/refund`, payload);
}
async function resendTicketRemote(ref, reason){
  return await api("POST", `/ops/bookings/${encodeURIComponent(ref)}/resend-ticket`, { reason: reason || "Resent from OPS" });
}
async function assignPilotRemote(ref, pilotEmail){
  return await api("POST", `/ops/bookings/${encodeURIComponent(ref)}/assign-pilot`, { pilot_email: pilotEmail || "" });
}

function reset(){


    localStorage.removeItem(KEY);
    return [];
  }

  return { load, save, add, update, remove, reset, listRemote, getRemote, createDraftRemote, paymentLinkRemote, markPaidRemote, cancelRemote, refundRemote, resendTicketRemote, assignPilotRemote };
})();