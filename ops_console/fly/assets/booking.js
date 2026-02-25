/* ===== Constants (same as original) ===== */
const CAPACITY = 3;
const BASE_30 = 200;
let TZS_RATE = 2450;
const MAX_DAYS = 60;

async function loadTzsRate() {
  const base = (window.FLYSUNBIRD_API_BASE || localStorage.getItem("FLYSUNBIRD_API_BASE") || (window.location.origin + "/api/v1")).replace(/\/$/, "");
  if (!base) return;
  try {
    const res = await fetch(base + "/public/fx-rate");
    if (res.ok) { const d = await res.json(); TZS_RATE = Number(d.usdToTzs) || 2450; }
  } catch (_) {}
}

/* ===== Helpers ===== */
const $ = (s) => document.querySelector(s);
const $$ = (s) => Array.from(document.querySelectorAll(s));
const fmt = (usd, cur) => (cur === "USD" ? `$${usd.toFixed(0)}` : `TZS ${(usd * TZS_RATE | 0).toLocaleString()}`);

/* ===== OPS-provided demo/availability payload =====
   Purpose: keep UI BLANK unless OPS preloads schedules.
   OPS can preload by:
   1) Setting sessionStorage key 'flysunbird_ops_payload_v1' to JSON string, OR
   2) Opening booking.html?ops=<base64url(json)>
   Payload shape:
   {
     from:"Dar es Salaam (DAR)", to:"Zanzibar (ZNZ)", region:"Tanzania",
     currency:"USD", dateStr:"2026-02-03",
     slots:[{start:"09:00", end:"10:10", priceUSD:220, seatsAvailable:3, flightNo:"FSB101", cabin:"Economy"}]
   }
*/
const OPS_KEY = "flysunbird_ops_payload_v1";
function b64urlDecode(str){
  try{
    str = str.replace(/-/g,'+').replace(/_/g,'/');
    const pad = str.length % 4;
    if (pad) str += "=".repeat(4-pad);
    return atob(str);
  }catch(e){ return null; }
}
function readOpsPayload(){
  try{
    const qp = new URLSearchParams(location.search);
    const opsParam = qp.get("ops");
    if (opsParam){
      const raw = b64urlDecode(opsParam);
      if (raw){
        sessionStorage.setItem(OPS_KEY, raw);
      }
    }
    const saved = sessionStorage.getItem(OPS_KEY);
    return saved ? JSON.parse(saved) : null;
  }catch(e){ return null; }
}
const OPS_PAYLOAD = readOpsPayload();
if (OPS_PAYLOAD){
  // Pre-fill minimal state (but do not force selection if payload missing fields)
  state.from = OPS_PAYLOAD.from || state.from || "";
  state.to = OPS_PAYLOAD.to || state.to || "";
  state.region = OPS_PAYLOAD.region || state.region || "";
  state.currency = (OPS_PAYLOAD.currency || state.currency || "USD");
  if (OPS_PAYLOAD.dateStr){
    state.date = OPS_PAYLOAD.dateStr;
  }
  saveState(state);
}
function getOpsSlots(dateStr){
  if (!OPS_PAYLOAD) return null;
  if (OPS_PAYLOAD.dateStr && dateStr && OPS_PAYLOAD.dateStr !== dateStr) return null;
  if (!Array.isArray(OPS_PAYLOAD.slots)) return null;
  return OPS_PAYLOAD.slots;
}


function hashStr(s){ let h=0; for(let i=0;i<s.length;i++) h=((h<<5)-h)+s.charCodeAt(i)|0; return h>>>0; }
function seededNoise(seed){ const x=Math.sin(seed)*10000; return x-Math.floor(x); }
function dailyPriceUSD(from, dayIndex){
  const w=[5,6].includes(new Date(Date.now()+dayIndex*86400000).getDay()) ? 1.15 : 1.0;
  const adj = 1 + (hashStr(from) % 7) / 50;
  const n = 0.75 + seededNoise(hashStr(from) + dayIndex*97) * 0.9;
  return Math.round(BASE_30 * adj * n * w);
}
function priceColorUSD(usd){
  if (usd <= 180) return "#10b981";
  if (usd <= 223) return "#f59e0b";
  if (usd <= 280) return "#8b5cf6";
  return "#ef4444";
}
function to12h(t){
  try{
    const [hh,mm]=t.split(":").map(Number);
    const ampm=hh>=12?"PM":"AM";
    const h=((hh%12)||12);
    return `${String(h).padStart(2,"0")}:${String(mm).padStart(2,"0")} ${ampm}`;
  }catch(e){ return t; }
}
function diffMins(start,end){
  try{
    const [sh,sm]=start.split(":").map(Number);
    const [eh,em]=end.split(":").map(Number);
    let s=sh*60+sm, e=eh*60+em;
    let d=e-s; if(d<0) d+=1440; return d;
  }catch(e){ return 0; }
}

/* ===== State ===== */
const state = initState();

// API base: explicit config, or same-origin /api/v1 when UI is served with the backend (deployed)
const API_BASE = (window.FLYSUNBIRD_API_BASE || localStorage.getItem("FLYSUNBIRD_API_BASE") || (window.location.origin + "/api/v1")).replace(/\/$/, "");
let calendarAvailability = {}; // dateStr -> { minPriceUSD } from GET /public/calendar-availability

function fetchCalendarAvailability(){
  if (!state.from) return Promise.resolve();
  const y = viewMonth.getFullYear(), m = viewMonth.getMonth();
  const start = new Date(y, m, 1);
  const end = new Date(y, m + 2, 0);
  const startStr = toLocalDateStr(start);
  const endStr = toLocalDateStr(end);
  const url = `${API_BASE}/public/calendar-availability?from_label=${encodeURIComponent(state.from)}&start=${startStr}&end=${endStr}&pax=${Math.max(1, state.pax || 1)}`;
  return fetch(url).then(r=> r.ok ? r.json() : {}).then(data=> { calendarAvailability = data || {}; }).catch(()=> { calendarAvailability = {}; });
}

// date range (use local dates to avoid UTC shift in timezones ahead of UTC)
function toLocalDateStr(d) {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return y + "-" + m + "-" + day;
}
const today = new Date(); today.setHours(0,0,0,0);
const endDay = new Date(today); endDay.setDate(endDay.getDate()+MAX_DAYS);
let viewMonth = new Date(today.getFullYear(), today.getMonth(), 1);

const allowedPax = () => state.region === "ZANZIBAR" ? 5 : 6;

/* ===== Stepper visuals ===== */
function setStep(idx){
  const nodes = $$("#stepper .step");
  nodes.forEach((s,i)=>{
    s.classList.remove("active","done");
    if(i<idx) s.classList.add("done");
    if(i===idx) s.classList.add("active");
  });
}

/* ===== From dropdown ===== */
const fromDrop = $("#fromDrop");
$("#fromBtn").addEventListener("click", ()=> fromDrop.classList.toggle("open"));
document.addEventListener("click", (e)=>{ if(!fromDrop.contains(e.target)) fromDrop.classList.remove("open"); });

$$('#fromDrop .sub').forEach((b)=>{
  b.addEventListener("click", ()=>{
    state.from = b.dataset.value;
    state.region = b.dataset.region;
    $("#fromLabel").textContent = state.from;
    fromDrop.classList.remove("open");
    syncPax(Math.min(state.pax, allowedPax()));
    validateWizard();
    setStep(0);
    saveState(state);
  });
});

/* ===== MOBILE SUBMENU SUPPORT (touch) ===== */
(function(){
  const mq = window.matchMedia("(max-width: 760px)");
  const parents = document.querySelectorAll("#fromDrop .item.has-sub");
  parents.forEach(p=>{
    p.addEventListener("click", (e)=>{
      if(!mq.matches) return;
      if(e.target && (e.target.classList.contains("sub") || e.target.closest(".submenu"))) return;
      e.preventDefault();
      p.classList.toggle("open-sub");
    });
  });
  const drop = document.getElementById("fromDrop");
  if(drop){
    const obs = new MutationObserver(()=>{
      if(!drop.classList.contains("open")){
        drop.querySelectorAll(".item.has-sub").forEach(p=>p.classList.remove("open-sub"));
      }
    });
    obs.observe(drop, {attributes:true, attributeFilter:["class"]});
  }
})();

/* ===== Pax stepper ===== */
const paxTop = $("#paxTop");
const paxBox = $("#paxBox");
function syncPax(n){
  const val = Math.max(1, parseInt(n||"1",10));
  state.pax = val;
  paxTop.value = String(state.pax);
  validateWizard();
  setStep(1);
  saveState(state);
}
$("#incPax").addEventListener("click", ()=> syncPax(parseInt(paxTop.value||"1",10)+1));
$("#decPax").addEventListener("click", ()=> syncPax(parseInt(paxTop.value||"1",10)-1));
paxTop.addEventListener("input", ()=> syncPax(paxTop.value));

/* ===== Currency selector ===== */
function setCurrency(cur){
  state.currency = cur;
  // Update segmented buttons (if present on page)
  document.querySelectorAll(".cur-btn").forEach(btn=>{
    const active = btn.dataset.cur === cur;
    btn.classList.toggle("active", active);
    btn.setAttribute("aria-selected", active ? "true" : "false");
  });
  saveState(state);
  // Refresh any rendered prices
  if ($("#calendarBlock").style.display === "block") renderCalendar();
  if ($("#resultsSection").style.display === "block") renderResults();
}

// Init default UI state
setCurrency(state.currency || "USD");
loadTzsRate();

// Bind clicks
document.querySelectorAll(".cur-btn").forEach(btn=>{
  btn.addEventListener("click", ()=>{
    setCurrency(btn.dataset.cur);
    setStep(2);
  });
});


/* ===== Validation ===== */
function validateWizard(){
  const hasFrom = !!state.from;
  const over = state.pax > allowedPax();
  $("#fromDrop").classList.toggle("error", !hasFrom);
  paxBox.classList.toggle("error", over);
  $("#btnToCalendar").disabled = !(hasFrom && !over);
}

/* ===== Calendar ===== */
function withinRange(date){ return date >= today && date < endDay; }
function getMonthMatrix(ym){
  const m0 = new Date(ym.getFullYear(), ym.getMonth(), 1);
  const startW = (m0.getDay()+6)%7;
  const daysInM = new Date(ym.getFullYear(), ym.getMonth()+1, 0).getDate();
  const grid = [];
  const total = Math.ceil((startW+daysInM)/7)*7;
  for(let i=0;i<total;i++){
    const d=i-startW+1;
    grid.push(d>=1 && d<=daysInM ? new Date(ym.getFullYear(), ym.getMonth(), d) : null);
  }
  return grid;
}
function monthBlock(container, monthDate){
  const grid = getMonthMatrix(new Date(monthDate.getFullYear(), monthDate.getMonth(), 1));
  container.innerHTML = `
    <div class="m-title">${monthDate.toLocaleString("en",{month:"long", year:"numeric"})}</div>
    <div class="wk"><div class="n">M</div><div class="n">T</div><div class="n">W</div><div class="n">T</div><div class="n">F</div><div class="n">S</div><div class="n">S</div></div>
    <div class="days"></div>
  `;
  const body = container.querySelector(".days");
  grid.forEach((d)=>{
    const cell = document.createElement("div");
    cell.className = "d";
    if(!d){ cell.style.visibility="hidden"; body.appendChild(cell); return; }
    const enabled = withinRange(d);
    if(!enabled){
      cell.classList.add("disabled");
      cell.innerHTML = `<div class="p">${d.getDate()}</div>`;
      body.appendChild(cell); return;
    }
    const dateStr = toLocalDateStr(d);
    const hasSlots = state.from && (dateStr in calendarAvailability);
    const noSlots = state.from && !hasSlots;
    let usd, priceStr, color;
    if (hasSlots) {
      usd = calendarAvailability[dateStr].minPriceUSD;
      priceStr = (state.currency === "USD") ? `from $${usd}` : `from ${(usd * TZS_RATE | 0).toLocaleString()} TZS`;
      color = priceColorUSD(usd);
    } else if (noSlots) {
      usd = 0;
      priceStr = "No flights";
      color = "transparent";
      cell.classList.add("no-slots");
    } else {
      usd = 0;
      priceStr = "—";
      color = "transparent";
    }

    cell.innerHTML = `
      <div style="display:grid;gap:4px;text-align:center">
        <div class="dw">${d.toLocaleString("en",{weekday:"short"})}</div>
        <div class="p">${d.getDate()}</div>
        <div class="pr">${priceStr}</div>
      </div>
      <i class="color" style="background:${color}"></i>
    `;
    if (noSlots) cell.title = "No available slots for this date";
    cell.addEventListener("click", ()=>{
      state.date = dateStr;
      $$(".d").forEach(x=>x.classList.remove("sel"));
      cell.classList.add("sel");
      saveState(state);
      goToResults();
    });
    body.appendChild(cell);
  });
}

function doRenderCalendarBody(){
  monthBlock($("#m1"), viewMonth);
  const nextM = new Date(viewMonth.getFullYear(), viewMonth.getMonth()+1, 1);
  monthBlock($("#m2"), nextM);
  $("#rangeHint").textContent =
    today.toLocaleDateString("en",{day:"2-digit", month:"short"}) + " – " +
    new Date(endDay - 86400000).toLocaleDateString("en",{day:"2-digit", month:"short", year:"numeric"});
}

function renderCalendar(){
  if (API_BASE && state.from) {
    fetchCalendarAvailability().then(doRenderCalendarBody);
    return;
  }
  doRenderCalendarBody();
}

$("#prevBtn").addEventListener("click", ()=>{
  const prev = new Date(viewMonth.getFullYear(), viewMonth.getMonth()-1, 1);
  const earliest = new Date(today.getFullYear(), today.getMonth(), 1);
  if(prev < earliest) return;
  viewMonth = prev;
  if (API_BASE && state.from) fetchCalendarAvailability().then(doRenderCalendarBody); else doRenderCalendarBody();
});
$("#nextBtn").addEventListener("click", ()=>{
  const next = new Date(viewMonth.getFullYear(), viewMonth.getMonth()+1, 1);
  const last = new Date(endDay.getFullYear(), endDay.getMonth(), 1);
  if(next > last) return;
  viewMonth = next;
  if (API_BASE && state.from) fetchCalendarAvailability().then(doRenderCalendarBody); else doRenderCalendarBody();
});

/* ===== Mobile iPhone-like date picker for booking date ===== */
const mobilePicker = new DateWheelPicker({
  title: "Choose flight date",
  min: toLocalDateStr(today),
  max: toLocalDateStr(new Date(endDay.getTime() - 86400000))
});
mobilePicker.attachTo($("#mobileDate"), (iso)=>{
  state.date = iso;
  saveState(state);
  // jump calendar view near selected date
  const dt = new Date(iso+"T00:00:00");
  viewMonth = new Date(dt.getFullYear(), dt.getMonth(), 1);
  $("#calendarBlock").style.display = "block";
  $("#preCalActions").style.display = "none";
  renderCalendar();
  // highlight selected
  setTimeout(()=> {
    const day = String(dt.getDate());
    $$(".d").forEach(el=>{
      const p = el.querySelector(".p");
      if(p && p.textContent === day) el.classList.add("sel");
    });
  }, 0);
  goToResults();
});

/* Show calendar */
$("#btnToCalendar").addEventListener("click", ()=>{
  $("#preCalActions").style.display = "none";
  $("#calendarBlock").style.display = "block";
  if (state.from) fetchCalendarAvailability().then(doRenderCalendarBody); else doRenderCalendarBody();
  setStep(2);
});

/* ===== Results (slots from API; OPS link uses pre-filled payload for that one date) ===== */
function buildSlotsFromOpsPayload(dateStr){
  const opsSlots = getOpsSlots(dateStr);
  if (!opsSlots || !opsSlots.length) return null;
  return opsSlots.map(s=>({
    timeEntryId: s.id,
    start: s.start,
    end: s.end,
    seatsAvailable: Number(s.seatsAvailable ?? CAPACITY),
    booked: Math.max(0, CAPACITY - (s.seatsAvailable ?? CAPACITY)),
    priceUSD: Number(s.priceUSD ?? 0),
    dateStr: dateStr,
    flightNo: s.flightNo || "FSB",
    cabin: s.cabin || "Economy",
    baggage: s.baggage || "Cabin baggage",
    from_label: OPS_PAYLOAD ? OPS_PAYLOAD.from : null,
    to_label: OPS_PAYLOAD ? OPS_PAYLOAD.to : null
  }));
}

async function fetchSlotsForDate(dateStr){
  const fromOps = buildSlotsFromOpsPayload(dateStr);
  if (fromOps) return fromOps;
  if (!state.from) return [];
  try {
    const url = `${API_BASE}/public/time-entries?from_label=${encodeURIComponent(state.from)}&dateStr=${encodeURIComponent(dateStr)}`;
    const res = await fetch(url);
    if (!res.ok) return [];
    const data = await res.json();
    const items = data.items || [];
    return items.map(s=>({
      timeEntryId: s.id,
      start: s.start,
      end: s.end,
      seatsAvailable: Number(s.seatsAvailable ?? CAPACITY),
      booked: Math.max(0, (s.seatsAvailable != null ? CAPACITY - s.seatsAvailable : 0)),
      priceUSD: Number(s.priceUSD ?? 0),
      dateStr: dateStr,
      flightNo: s.flightNo || "FSB",
      cabin: s.cabin || "Economy",
      baggage: "Cabin baggage",
      from_label: s.from_label,
      to_label: s.to_label
    }));
  } catch (e) {
    return [];
  }
}

async function renderResults(){
  const dateStr = state.date;
  $("#selSummary").textContent = `${state.from} • ${new Date(dateStr+"T00:00:00").toLocaleDateString("en",{weekday:"short",day:"2-digit",month:"short",year:"numeric"})}`;
  const box = $("#results");
  box.innerHTML = "<div class=\"sub\">Loading slots…</div>";
  const want = state.pax;

  const slots = await fetchSlotsForDate(dateStr);
  box.innerHTML = "";
  slots.forEach(slot=>{
    const left = slot.seatsAvailable != null ? slot.seatsAvailable : (CAPACITY - (slot.booked || 0));
    if (left < want) return;

    const row = document.createElement("div");
    row.className = "row";
    row.innerHTML = `
      <div class="colM">
        <div class="times"><div class="t">${to12h(slot.start)}</div></div>
        <div class="tags">
          <span class="badge ${left>0?'ok':'bad'}">${left>0?`${left} seats left`:'Full'}</span>
          <span class="badge">🕒 ${diffMins(slot.start, slot.end)} min experience</span>
        </div>
      </div>
      <div class="colR">
        <div class="price">${fmt(slot.priceUSD, state.currency)} <span class="subp">/seat</span></div>
        <div class="subp">Total for ${want}: <strong>${fmt(slot.priceUSD*want, state.currency)}</strong></div>
        <button class="btn primary">Select</button>
      </div>
    `;
    row.querySelector("button").addEventListener("click", ()=>{
      state.selected = { ...slot, dateStr };
      if (slot.to_label) state.to = slot.to_label;
      if (slot.from_label) state.from = slot.from_label;
      saveState(state);
      // Prep passenger list count
      if (!Array.isArray(state.passengers)) state.passengers = [];
      if (state.passengers.length > state.pax) state.passengers = state.passengers.slice(0, state.pax);
      saveState(state);
      window.location.href = "passenger.html";
    });
    box.appendChild(row);
  });

  if(!box.children.length){
    box.innerHTML = `<div class="card" style="padding:16px"><span class="hint">No flights can fit ${want} passenger(s) on this date. Reduce passengers.</span></div>`;
  }
}

function goToResults(){
  if(!state.date) return;
  $("#wizard").style.display = "none";
  $("#resultsSection").style.display = "block";
  renderResults();
}

$("#changeDate").addEventListener("click", ()=>{
  $("#resultsSection").style.display = "none";
  $("#wizard").style.display = "block";
  $("#preCalActions").style.display = "none";
  $("#calendarBlock").style.display = "block";
  setStep(2);
  renderCalendar();
});

/* ===== Init UI from stored state ===== */
function boot(){
  const fromLabel = $("#fromLabel");
  if(fromLabel && state.from) fromLabel.textContent = state.from;
  if(paxTop) paxTop.value = String(state.pax || 1);
  const curTag = $("#curTag");
  if(curTag) curTag.textContent = state.currency || "USD";
  $$(".cur-opt").forEach(o=>o.classList.toggle("active", o.dataset.cur === state.currency));
  if(typeof validateWizard === "function") validateWizard();

  // If already have date (e.g. returning from passenger/payment), show results and sync calendar month
  if(state.date){
    const dt = new Date(state.date + "T00:00:00");
    if (!isNaN(dt.getTime())) viewMonth = new Date(dt.getFullYear(), dt.getMonth(), 1);
    const preCal = $("#preCalActions");
    const calBlock = $("#calendarBlock");
    if(preCal) preCal.style.display = "none";
    if(calBlock) calBlock.style.display = "block";
    if(typeof renderCalendar === "function") renderCalendar();
    if(typeof goToResults === "function") goToResults();
  }
}
boot();
