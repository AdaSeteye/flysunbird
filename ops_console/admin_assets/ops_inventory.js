// Ops-side inventory (minimal) for offline bookings.
// No route codes. Just Origin text, Destination text, Date, Slot time, Seats available, Price.
// When Ops creates/Confirms a booking, seats are reduced automatically.

const OpsInventory = (() => {
  const KEY = "flysunbird_ops_inventory_v1";
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
    if (!API_BASE) throw new Error("API_BASE not set. Sign in from the login page.");
    var res = await fetch(API_BASE + path, { method, headers: { "Content-Type": "application/json", ...(API_TOKEN ? { "Authorization": "Bearer " + API_TOKEN } : {}) }, body: body ? JSON.stringify(body) : undefined });
    if (res.status === 401 && !_retried && await refreshAccessToken()) return api(method, path, body, true);
    if (!res.ok) {
      var text = await res.text();
      if (res.status === 401) throw new Error("Session expired or invalid. Please sign in again from the login page.");
      throw new Error(text || res.statusText);
    }
    return await res.json();
  };

  const uid = () => `inv_${Math.random().toString(16).slice(2)}_${Date.now().toString(16)}`;

  function load(){
    try{
      const raw = localStorage.getItem(KEY);
      return raw ? JSON.parse(raw) : [];
    }catch(e){ return []; }
  }
  function save(list){ localStorage.setItem(KEY, JSON.stringify(list)); }

  function seed(){
    const today = new Date().toISOString().slice(0,10);
    const list = [
      {id: uid(), region:"Coastal", from:"Dar es Salaam", subregion:"Zanzibar", date: today, start:"09:00", end:"10:10", seatsAvailable:3, price:220, currency:"USD", status:"OPEN"},
      {id: uid(), region:"Coastal", from:"Dar es Salaam", subregion:"Zanzibar", date: today, start:"15:00", end:"16:10", seatsAvailable:2, price:240, currency:"USD", status:"OPEN"},
    ];
    save(list);
    return list;
  }

  function ensure(){
    const list = load();
    if(list.length) return list;
    return seed();
  }

  function add(item){
    const list = load();
    const x = {
      id: uid(),
      region: item.region || "",
      from: item.from || "", 
      subregion: item.subregion || "",
      
      date: item.date || null,
      start: item.start || "",
      end: item.end || "",
      seatsAvailable: Number(item.seatsAvailable||0),
      price: Number(item.price||0),
      currency: item.currency || "USD",
      status: item.status || "OPEN" // OPEN | CLOSED
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

  function reserveSeats(id, pax){
    const list = load();
    const x = list.find(i=>i.id===id);
    if(!x) return {ok:false, msg:"Inventory not found"};
    if(x.status !== "OPEN") return {ok:false, msg:"Inventory is CLOSED"};
    pax = Number(pax||1);
    if(pax<=0) pax=1;
    if(Number(x.seatsAvailable||0) < pax) return {ok:false, msg:"Not enough seats available"};
    x.seatsAvailable = Number(x.seatsAvailable||0) - pax;
    x.updatedAt = new Date().toISOString();
    save(list);
    return {ok:true, item:x};
  }

async function listRemote(dateStr){
  const q = dateStr ? `?dateStr=${encodeURIComponent(dateStr)}` : "";
  return await api("GET", `/ops/time-entries${q}`);
}
async function createRemote(payload){
  return await api("POST","/ops/time-entries", payload);
}
async function patchRemote(id, payload){
  return await api("PATCH", `/ops/time-entries/${id}`, payload);
}
async function deleteRemote(id){
  return await api("DELETE", `/ops/time-entries/${id}`);
}

function reset(){


    localStorage.removeItem(KEY);
    return seed();
  }

  return { load, save, ensure, add, update, remove, reserveSeats, reset, listRemote, createRemote, patchRemote, deleteRemote };
})();
