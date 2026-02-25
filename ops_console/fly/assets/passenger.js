const state = initState();
const $ = (s)=>document.querySelector(s);
const $$ = (s)=>Array.from(document.querySelectorAll(s));

const API_BASE = (window.FLYSUNBIRD_API_BASE || localStorage.getItem("FLYSUNBIRD_API_BASE") || (window.location.origin ? window.location.origin + "/api/v1" : "")).replace(/\/$/,"");
async function apiPost(path, body){
  const res = await fetch(API_BASE + path, {method:"POST", headers: {"Content-Type":"application/json"}, body: JSON.stringify(body||{})});
  let data=null; try{ data = await res.json(); }catch(_e){}
  if(!res.ok){
    const msg = (data && (data.detail||data.message)) ? (data.detail||data.message) : (await res.text());
    throw new Error(typeof msg==="string"?msg:JSON.stringify(msg));
  }
  return data;
}
function makeBookingRef(){
  const d = new Date();
  const y = d.getFullYear(), m = String(d.getMonth()+1).padStart(2,'0'), day = String(d.getDate()).padStart(2,'0');
  return `FSB-${y}${m}${day}-${Math.random().toString(36).slice(2,6).toUpperCase()}`;
}

const TZS_RATE = 2450;
const KG2LB = 2.20462262185;
const fmt = (usd, cur) => (cur === "USD" ? `$${usd.toFixed(0)}` : `TZS ${(usd*TZS_RATE|0).toLocaleString()}`);

if(!state.selected){
  window.location.href = "booking.html";
}

const COUNTRIES = window.COUNTRIES || [];

const TERMS_META = { version: "2025", docSha256: "edfe624c7f9b2dac0ced3b189039f693c0683123f12881d3702b0fcf4d19631d" };
function initTermsConsent(){
  const cb = document.getElementById("agreeTerms");
  if(!cb) return;
  // restore from state (session) or localStorage (if present)
  try {
    const persisted = localStorage.getItem("flysunbird_terms_acceptance_v1");
    if(persisted && (!state.termsAcceptance || !state.termsAcceptance.agreed)) {
      const parsed = JSON.parse(persisted);
      if(parsed && parsed.agreed && parsed.agreedAt) {
        state.termsAcceptance = {...parsed, version: TERMS_META.version, docSha256: TERMS_META.docSha256};
        saveState(state);
      }
    }
  } catch(e){}

  cb.checked = !!(state.termsAcceptance && state.termsAcceptance.agreed);
  cb.addEventListener("change", ()=>{
    if(cb.checked){
      const iso = new Date().toISOString();
      state.termsAcceptance = { agreed:true, agreedAt: iso, version: TERMS_META.version, docSha256: TERMS_META.docSha256 };
      try { localStorage.setItem("flysunbird_terms_acceptance_v1", JSON.stringify(state.termsAcceptance)); } catch(e){}
    } else {
      state.termsAcceptance = { agreed:false, agreedAt:null, version: TERMS_META.version, docSha256: TERMS_META.docSha256 };
      try { localStorage.removeItem("flysunbird_terms_acceptance_v1"); } catch(e){}
    }
    saveState(state);
    updateProgress();
  });
}


// Country dial codes (expanded list with flags). If a country isn't present, we fall back to +255.
const DIAL_CODES = [
  {name:"Afghanistan", dial:"+93", flag:"🇦🇫"},
  {name:"Albania", dial:"+355", flag:"🇦🇱"},
  {name:"Algeria", dial:"+213", flag:"🇩🇿"},
  {name:"Andorra", dial:"+376", flag:"🇦🇩"},
  {name:"Angola", dial:"+244", flag:"🇦🇴"},
  {name:"Antigua and Barbuda", dial:"+1", flag:"🇦🇬"},
  {name:"Argentina", dial:"+54", flag:"🇦🇷"},
  {name:"Armenia", dial:"+374", flag:"🇦🇲"},
  {name:"Australia", dial:"+61", flag:"🇦🇺"},
  {name:"Austria", dial:"+43", flag:"🇦🇹"},
  {name:"Azerbaijan", dial:"+994", flag:"🇦🇿"},
  {name:"Bahamas", dial:"+1", flag:"🇧🇸"},
  {name:"Bahrain", dial:"+973", flag:"🇧🇭"},
  {name:"Bangladesh", dial:"+880", flag:"🇧🇩"},
  {name:"Barbados", dial:"+1", flag:"🇧🇧"},
  {name:"Belarus", dial:"+375", flag:"🇧🇾"},
  {name:"Belgium", dial:"+32", flag:"🇧🇪"},
  {name:"Belize", dial:"+501", flag:"🇧🇿"},
  {name:"Benin", dial:"+229", flag:"🇧🇯"},
  {name:"Bhutan", dial:"+975", flag:"🇧🇹"},
  {name:"Bolivia", dial:"+591", flag:"🇧🇴"},
  {name:"Bosnia and Herzegovina", dial:"+387", flag:"🇧🇦"},
  {name:"Botswana", dial:"+267", flag:"🇧🇼"},
  {name:"Brazil", dial:"+55", flag:"🇧🇷"},
  {name:"Brunei", dial:"+673", flag:"🇧🇳"},
  {name:"Bulgaria", dial:"+359", flag:"🇧🇬"},
  {name:"Burkina Faso", dial:"+226", flag:"🇧🇫"},
  {name:"Burundi", dial:"+257", flag:"🇧🇮"},
  {name:"Cambodia", dial:"+855", flag:"🇰🇭"},
  {name:"Cameroon", dial:"+237", flag:"🇨🇲"},
  {name:"Canada", dial:"+1", flag:"🇨🇦"},
  {name:"Cape Verde", dial:"+238", flag:"🇨🇻"},
  {name:"Central African Republic", dial:"+236", flag:"🇨🇫"},
  {name:"Chad", dial:"+235", flag:"🇹🇩"},
  {name:"Chile", dial:"+56", flag:"🇨🇱"},
  {name:"China", dial:"+86", flag:"🇨🇳"},
  {name:"Colombia", dial:"+57", flag:"🇨🇴"},
  {name:"Comoros", dial:"+269", flag:"🇰🇲"},
  {name:"Congo (Congo-Brazzaville)", dial:"+242", flag:"🇨🇬"},
  {name:"DR Congo", dial:"+243", flag:"🇨🇩"},
  {name:"Costa Rica", dial:"+506", flag:"🇨🇷"},
  {name:"Côte d’Ivoire", dial:"+225", flag:"🇨🇮"},
  {name:"Croatia", dial:"+385", flag:"🇭🇷"},
  {name:"Cuba", dial:"+53", flag:"🇨🇺"},
  {name:"Cyprus", dial:"+357", flag:"🇨🇾"},
  {name:"Czechia", dial:"+420", flag:"🇨🇿"},
  {name:"Denmark", dial:"+45", flag:"🇩🇰"},
  {name:"Djibouti", dial:"+253", flag:"🇩🇯"},
  {name:"Dominica", dial:"+1", flag:"🇩🇲"},
  {name:"Dominican Republic", dial:"+1", flag:"🇩🇴"},
  {name:"Ecuador", dial:"+593", flag:"🇪🇨"},
  {name:"Egypt", dial:"+20", flag:"🇪🇬"},
  {name:"El Salvador", dial:"+503", flag:"🇸🇻"},
  {name:"Equatorial Guinea", dial:"+240", flag:"🇬🇶"},
  {name:"Eritrea", dial:"+291", flag:"🇪🇷"},
  {name:"Estonia", dial:"+372", flag:"🇪🇪"},
  {name:"Eswatini", dial:"+268", flag:"🇸🇿"},
  {name:"Ethiopia", dial:"+251", flag:"🇪🇹"},
  {name:"Fiji", dial:"+679", flag:"🇫🇯"},
  {name:"Finland", dial:"+358", flag:"🇫🇮"},
  {name:"France", dial:"+33", flag:"🇫🇷"},
  {name:"Gabon", dial:"+241", flag:"🇬🇦"},
  {name:"Gambia", dial:"+220", flag:"🇬🇲"},
  {name:"Georgia", dial:"+995", flag:"🇬🇪"},
  {name:"Germany", dial:"+49", flag:"🇩🇪"},
  {name:"Ghana", dial:"+233", flag:"🇬🇭"},
  {name:"Greece", dial:"+30", flag:"🇬🇷"},
  {name:"Grenada", dial:"+1", flag:"🇬🇩"},
  {name:"Guatemala", dial:"+502", flag:"🇬🇹"},
  {name:"Guinea", dial:"+224", flag:"🇬🇳"},
  {name:"Guinea-Bissau", dial:"+245", flag:"🇬🇼"},
  {name:"Guyana", dial:"+592", flag:"🇬🇾"},
  {name:"Haiti", dial:"+509", flag:"🇭🇹"},
  {name:"Honduras", dial:"+504", flag:"🇭🇳"},
  {name:"Hungary", dial:"+36", flag:"🇭🇺"},
  {name:"Iceland", dial:"+354", flag:"🇮🇸"},
  {name:"India", dial:"+91", flag:"🇮🇳"},
  {name:"Indonesia", dial:"+62", flag:"🇮🇩"},
  {name:"Iran", dial:"+98", flag:"🇮🇷"},
  {name:"Iraq", dial:"+964", flag:"🇮🇶"},
  {name:"Ireland", dial:"+353", flag:"🇮🇪"},
  {name:"Israel", dial:"+972", flag:"🇮🇱"},
  {name:"Italy", dial:"+39", flag:"🇮🇹"},
  {name:"Jamaica", dial:"+1", flag:"🇯🇲"},
  {name:"Japan", dial:"+81", flag:"🇯🇵"},
  {name:"Jordan", dial:"+962", flag:"🇯🇴"},
  {name:"Kazakhstan", dial:"+7", flag:"🇰🇿"},
  {name:"Kenya", dial:"+254", flag:"🇰🇪"},
  {name:"Kuwait", dial:"+965", flag:"🇰🇼"},
  {name:"Kyrgyzstan", dial:"+996", flag:"🇰🇬"},
  {name:"Laos", dial:"+856", flag:"🇱🇦"},
  {name:"Latvia", dial:"+371", flag:"🇱🇻"},
  {name:"Lebanon", dial:"+961", flag:"🇱🇧"},
  {name:"Lesotho", dial:"+266", flag:"🇱🇸"},
  {name:"Liberia", dial:"+231", flag:"🇱🇷"},
  {name:"Libya", dial:"+218", flag:"🇱🇾"},
  {name:"Liechtenstein", dial:"+423", flag:"🇱🇮"},
  {name:"Lithuania", dial:"+370", flag:"🇱🇹"},
  {name:"Luxembourg", dial:"+352", flag:"🇱🇺"},
  {name:"Madagascar", dial:"+261", flag:"🇲🇬"},
  {name:"Malawi", dial:"+265", flag:"🇲🇼"},
  {name:"Malaysia", dial:"+60", flag:"🇲🇾"},
  {name:"Maldives", dial:"+960", flag:"🇲🇻"},
  {name:"Mali", dial:"+223", flag:"🇲🇱"},
  {name:"Malta", dial:"+356", flag:"🇲🇹"},
  {name:"Mauritania", dial:"+222", flag:"🇲🇷"},
  {name:"Mauritius", dial:"+230", flag:"🇲🇺"},
  {name:"Mexico", dial:"+52", flag:"🇲🇽"},
  {name:"Moldova", dial:"+373", flag:"🇲🇩"},
  {name:"Monaco", dial:"+377", flag:"🇲🇨"},
  {name:"Mongolia", dial:"+976", flag:"🇲🇳"},
  {name:"Montenegro", dial:"+382", flag:"🇲🇪"},
  {name:"Morocco", dial:"+212", flag:"🇲🇦"},
  {name:"Mozambique", dial:"+258", flag:"🇲🇿"},
  {name:"Myanmar", dial:"+95", flag:"🇲🇲"},
  {name:"Namibia", dial:"+264", flag:"🇳🇦"},
  {name:"Nepal", dial:"+977", flag:"🇳🇵"},
  {name:"Netherlands", dial:"+31", flag:"🇳🇱"},
  {name:"New Zealand", dial:"+64", flag:"🇳🇿"},
  {name:"Nicaragua", dial:"+505", flag:"🇳🇮"},
  {name:"Niger", dial:"+227", flag:"🇳🇪"},
  {name:"Nigeria", dial:"+234", flag:"🇳🇬"},
  {name:"North Macedonia", dial:"+389", flag:"🇲🇰"},
  {name:"Norway", dial:"+47", flag:"🇳🇴"},
  {name:"Oman", dial:"+968", flag:"🇴🇲"},
  {name:"Pakistan", dial:"+92", flag:"🇵🇰"},
  {name:"Panama", dial:"+507", flag:"🇵🇦"},
  {name:"Papua New Guinea", dial:"+675", flag:"🇵🇬"},
  {name:"Paraguay", dial:"+595", flag:"🇵🇾"},
  {name:"Peru", dial:"+51", flag:"🇵🇪"},
  {name:"Philippines", dial:"+63", flag:"🇵🇭"},
  {name:"Poland", dial:"+48", flag:"🇵🇱"},
  {name:"Portugal", dial:"+351", flag:"🇵🇹"},
  {name:"Qatar", dial:"+974", flag:"🇶🇦"},
  {name:"Romania", dial:"+40", flag:"🇷🇴"},
  {name:"Russia", dial:"+7", flag:"🇷🇺"},
  {name:"Rwanda", dial:"+250", flag:"🇷🇼"},
  {name:"Saudi Arabia", dial:"+966", flag:"🇸🇦"},
  {name:"Senegal", dial:"+221", flag:"🇸🇳"},
  {name:"Serbia", dial:"+381", flag:"🇷🇸"},
  {name:"Seychelles", dial:"+248", flag:"🇸🇨"},
  {name:"Sierra Leone", dial:"+232", flag:"🇸🇱"},
  {name:"Singapore", dial:"+65", flag:"🇸🇬"},
  {name:"Slovakia", dial:"+421", flag:"🇸🇰"},
  {name:"Slovenia", dial:"+386", flag:"🇸🇮"},
  {name:"Somalia", dial:"+252", flag:"🇸🇴"},
  {name:"South Africa", dial:"+27", flag:"🇿🇦"},
  {name:"South Sudan", dial:"+211", flag:"🇸🇸"},
  {name:"Spain", dial:"+34", flag:"🇪🇸"},
  {name:"Sri Lanka", dial:"+94", flag:"🇱🇰"},
  {name:"Sudan", dial:"+249", flag:"🇸🇩"},
  {name:"Sweden", dial:"+46", flag:"🇸🇪"},
  {name:"Switzerland", dial:"+41", flag:"🇨🇭"},
  {name:"Syria", dial:"+963", flag:"🇸🇾"},
  {name:"Taiwan", dial:"+886", flag:"🇹🇼"},
  {name:"Tajikistan", dial:"+992", flag:"🇹🇯"},
  {name:"Tanzania", dial:"+255", flag:"🇹🇿"},
  {name:"Thailand", dial:"+66", flag:"🇹🇭"},
  {name:"Togo", dial:"+228", flag:"🇹🇬"},
  {name:"Trinidad and Tobago", dial:"+1", flag:"🇹🇹"},
  {name:"Tunisia", dial:"+216", flag:"🇹🇳"},
  {name:"Turkey", dial:"+90", flag:"🇹🇷"},
  {name:"Turkmenistan", dial:"+993", flag:"🇹🇲"},
  {name:"Uganda", dial:"+256", flag:"🇺🇬"},
  {name:"Ukraine", dial:"+380", flag:"🇺🇦"},
  {name:"United Arab Emirates", dial:"+971", flag:"🇦🇪"},
  {name:"United Kingdom", dial:"+44", flag:"🇬🇧"},
  {name:"United States", dial:"+1", flag:"🇺🇸"},
  {name:"Uruguay", dial:"+598", flag:"🇺🇾"},
  {name:"Uzbekistan", dial:"+998", flag:"🇺🇿"},
  {name:"Venezuela", dial:"+58", flag:"🇻🇪"},
  {name:"Vietnam", dial:"+84", flag:"🇻🇳"},
  {name:"Yemen", dial:"+967", flag:"🇾🇪"},
  {name:"Zambia", dial:"+260", flag:"🇿🇲"},
  {name:"Zimbabwe", dial:"+263", flag:"🇿🇼"},
];

function populateDialCodes(sel){
  const list = DIAL_CODES.slice().sort((a,b)=> a.name.localeCompare(b.name));
  sel.innerHTML = list.map(c=> `<option value="${c.dial}">${c.flag} ${c.name} (${c.dial})</option>`).join("");
  return list;
}

function computePhone(p){
  const dial = p.phoneCountry || "+255";
  const num = String(p.phoneNumber || "").replace(/\s+/g,"").replace(/^\+/, "");
  // if user typed leading 0, keep it (common local), but store with dial prefix
  p.phone = num ? `${dial}${num.startsWith("0") ? num.slice(1) : num}` : "";
}

// normalize phone fields for existing data (backwards compatible)
if(Array.isArray(state.passengers)){
  state.passengers.forEach(p=>{
    if(!p || typeof p !== "object") return;
    if(!p.phoneCountry) p.phoneCountry = "+255";
    if(!p.phoneNumber && p.phone){
      const s = String(p.phone).trim();
      // try to split the stored E.164 number into (dial code + local number)
      // Prefer the LONGEST matching dial code.
      const known = Array.from(new Set(DIAL_CODES.map(d=>d.dial))).sort((a,b)=> b.length - a.length);
      const hit = known.find(k=> s.startsWith(k));
      if(hit){
        p.phoneCountry = hit;
        p.phoneNumber = s.slice(hit.length);
      }else if(s.startsWith("+") && s.length>4){
        p.phoneCountry = s.slice(0,4);
        p.phoneNumber = s.slice(4);
      }else{
        p.phoneNumber = s;
      }
    }
    computePhone(p);
  });
}


function populateCountries(select){
  select.innerHTML = `<option value="" disabled selected>Select nationality</option>` +
    COUNTRIES.map(c=>`<option value="${c}">${c}</option>`).join("");
}

/* Summary */
function renderSummary(){
  const sum = $("#summary");
  const pax = state.pax || 1;
  const per = state.selected.priceUSD;
  const total = per * pax;
  sum.innerHTML = `
    <div class="head">
      <div class="t">🧾 Summary</div>
      <div class="pill">${state.currency}</div>
    </div>
    <div class="body">
      <div class="line"><div class="k">🛩️ From</div><div class="v">${state.from || "—"}</div></div>
      <div class="line"><div class="k">📅 Date</div><div class="v">${state.selected.dateStr}</div></div>
      <div class="line"><div class="k">⏰ Time</div><div class="v">${state.selected.start}–${state.selected.end}</div></div>
      <div class="div"></div>
      <div class="line"><div class="k">Per seat</div><div class="v">${fmt(per, state.currency)}</div></div>
      <div class="line"><div class="k">Passengers</div><div class="v">× ${pax}</div></div>
      <div class="div"></div>
      <div class="total"><div class="k">Total</div><div class="v">${fmt(total, state.currency)}</div></div>
      <div class="hint">You can edit passengers now, then proceed to payment.</div>
    </div>
  `;
}

/* Passenger cards */
function passengerTemplate(idx, data){
  // A passenger is complete when the user has provided first and last name,
  // a government ID number, date of birth and nationality. For passenger 0,
  // email is also required (booking contact).
  const filled = !!(data.first && data.last && data.govId && data.dob && data.nationality) && (idx > 0 || (data.email && data.email.trim()));
  const wUnit = data.weightUnit || "kg";
  const phoneCountry = data.phoneCountry || "+255";
  const wVal = (data.weightValue ?? "");

  return `
  <div class="pax-card" data-idx="${idx}">
    <div class="pax-head">
      <div class="title">Passenger ${idx+1}</div>
      <div class="meta">
        <span class="pill">${filled ? "✅ Complete" : "⚠️ Incomplete"}</span>
        <span class="pill">Required</span>
      </div>
    </div>
    <div class="pax-body">
      <!-- Using a flexible row-based layout to better control responsiveness. Each
           field takes up half the row on larger screens and full width on mobile. -->
      <div class="form-fields">
        <!-- Name and Surname -->
        <div class="field weight-field">
          <label>Name (as on Government ID)</label>
          <input class="input" data-k="first" type="text" value="${escapeHtml(data.first||"")}" placeholder="First name" required>
        </div>
        <div class="field">
          <label>Surname</label>
          <input class="input" data-k="last" type="text" value="${escapeHtml(data.last||"")}" placeholder="Surname" required>
        </div>
        <!-- Government ID and Gender -->
        <div class="field">
          <label>Government ID Number</label>
          <input class="input" data-k="govId" type="text" value="${escapeHtml(data.govId||"")}" placeholder="e.g. Passport/NIDA" required>
        </div>
        <div class="field">
          <label>Gender</label>
          <div class="seg" role="radiogroup" aria-label="Gender">
            <input type="radio" id="sexM_${idx}" name="sex_${idx}" value="Male" ${data.sex === "Male" ? "checked" : ""}>
            <label for="sexM_${idx}">Male</label>
            <input type="radio" id="sexF_${idx}" name="sex_${idx}" value="Female" ${data.sex === "Female" || !data.sex ? "checked" : ""}>
            <label for="sexF_${idx}">Female</label>
          </div>
        </div>
        <!-- Date of birth (full row) -->
        <div class="field dob-field" style="flex-basis:100%">
          <label>Date of birth</label>
          <div class="dob-selects" data-dob-selects="1">
            <select class="input dob-sel" data-dob-part="day" required aria-label="Day">
              <option value="">Day</option>
            </select>
            <select class="input dob-sel" data-dob-part="month" required aria-label="Month">
              <option value="">Month</option>
            </select>
            <select class="input dob-sel" data-dob-part="year" required aria-label="Year">
              <option value="">Year</option>
            </select>
          </div>
          <input type="hidden" data-k="dob" value="${escapeHtml(data.dob||"")}">
          <div class="hint">Select day, month, and year.</div>
        </div>
        <!-- Nationality and Weight -->
        <div class="field">
          <label>Nationality</label>
          <select class="input select" data-k="nationality" required></select>
        </div>
        <div class="field">
          <label>Weight</label>
          <div class="unit">
            <input class="input" data-k="weightValue" type="number" min="0" step="0.1" value="${wVal}" placeholder="0.0" style="">
            <div class="unit-toggle" data-unit-toggle>
              <button type="button" data-unit="kg" class="${wUnit==="kg"?"active":""}">kg</button>
              <button type="button" data-unit="lb" class="${wUnit==="lb"?"active":""}">lb</button>
            </div>
          </div>
          <div class="hint">Minimal toggle. We convert automatically.</div>
        </div>
        <!-- Phone (full row) -->
        <div class="field phone-field">
          <label>Phone</label>
          <div class="phone">
            <select class="input select phone-sel" data-k="phoneCountry"></select>
            <input class="input phone-num" data-k="phoneNumber" type="tel" inputmode="tel" value="${escapeHtml(data.phoneNumber||"")}" placeholder="Phone number" ${idx===0 ? "required" : ""}>
          </div>
          <div class="hint">${idx===0 ? "Required for booking contact." : "Optional (same contact used if empty)."}</div>
        </div>
        ${idx === 0 ? `
        <!-- Email (passenger 1 only – booking contact) -->
        <div class="field">
          <label>Contact email</label>
          <input class="input" data-k="email" type="email" value="${escapeHtml(data.email||"")}" placeholder="name@email.com" required>
          <div class="hint">Required for booking confirmation and tickets.</div>
        </div>
        ` : ""}
      </div>
    </div>
  </div>
  `;
}

function escapeHtml(s){
  return String(s).replace(/[&<>"']/g, (m)=>({ "&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#039;" }[m]));
}


function ensurePassengerCount(){
  const want = state.pax || 1;
  if(!Array.isArray(state.passengers)) state.passengers = [];
  // Start with 1 passenger card, then let user add until "want"
  if(state.passengers.length === 0){
    state.passengers.push({
      first:"", last:"", govId:"", email:"",
      sex:"Female", dob:"", nationality:"",
      weightUnit:"kg", weightValue:"", phone:""
    });
  }
  if(state.passengers.length > want) state.passengers = state.passengers.slice(0, want);
}


const DOB_MONTHS = [
  {v:"01", t:"Jan"}, {v:"02", t:"Feb"}, {v:"03", t:"Mar"}, {v:"04", t:"Apr"},
  {v:"05", t:"May"}, {v:"06", t:"Jun"}, {v:"07", t:"Jul"}, {v:"08", t:"Aug"},
  {v:"09", t:"Sep"}, {v:"10", t:"Oct"}, {v:"11", t:"Nov"}, {v:"12", t:"Dec"}
];

function daysInMonth(year, month){
  // month: 1-12
  const y = parseInt(year, 10);
  const m = parseInt(month, 10);
  if(!y || !m) return 31;
  return new Date(y, m, 0).getDate(); // day 0 of next month = last day of month
}

function setupDobDropdowns(card, p){
  const wrap = card.querySelector("[data-dob-selects='1']");
  if(!wrap) return;

  const selDay = wrap.querySelector("[data-dob-part='day']");
  const selMonth = wrap.querySelector("[data-dob-part='month']");
  const selYear = wrap.querySelector("[data-dob-part='year']");
  const hidden = card.querySelector("input[type='hidden'][data-k='dob']");

  // Populate options once per render
  if(selDay && selDay.options.length <= 1){
    for(let d=1; d<=31; d++){
      const v = String(d).padStart(2,"0");
      const opt = document.createElement("option");
      opt.value = v;
      opt.textContent = v;
      selDay.appendChild(opt);
    }
  }
  if(selMonth && selMonth.options.length <= 1){
    DOB_MONTHS.forEach(m=>{
      const opt = document.createElement("option");
      opt.value = m.v;
      opt.textContent = m.t;
      selMonth.appendChild(opt);
    });
  }
  if(selYear && selYear.options.length <= 1){
    const nowY = new Date().getFullYear();
    for(let y=nowY; y>=1900; y--){
      const opt = document.createElement("option");
      opt.value = String(y);
      opt.textContent = String(y);
      selYear.appendChild(opt);
    }
  }

  // Initialize from stored value YYYY-MM-DD
  if(p.dob && typeof p.dob === "string" && p.dob.includes("-")){
    const parts = p.dob.split("-");
    if(parts.length === 3){
      selYear.value = parts[0] || "";
      selMonth.value = parts[1] || "";
      selDay.value = parts[2] || "";
    }
  }

  function normalizeDay(){
    const y = selYear.value;
    const m = selMonth.value;
    const maxD = daysInMonth(y, m);
    const cur = parseInt(selDay.value || "0", 10);
    if(cur && cur > maxD){
      selDay.value = String(maxD).padStart(2,"0");
    }
  }

  function commit(){
    normalizeDay();
    const y = selYear.value;
    const m = selMonth.value;
    const d = selDay.value;

    if(y && m && d){
      const iso = `${y}-${m}-${d}`;
      p.dob = iso;
      if(hidden) hidden.value = iso;
    } else {
      p.dob = "";
      if(hidden) hidden.value = "";
    }
    saveState(state);
    updateProgress();
  }

  // When year/month changes, adjust day max and commit
  ["change","input"].forEach(evt=>{
    selDay.addEventListener(evt, commit);
    selMonth.addEventListener(evt, commit);
    selYear.addEventListener(evt, commit);
  });

  // Ensure hidden matches on first render
  if(hidden){
    hidden.value = p.dob || "";
  }
}


function renderPassengers(){
  ensurePassengerCount();
  const list = $("#paxList");
  list.innerHTML = state.passengers.map((p,i)=> passengerTemplate(i,p)).join("");

  // populate nationality
  $$("#paxList [data-k='nationality']").forEach((sel, i)=>{
    populateCountries(sel);
    sel.value = state.passengers[i].nationality || "";
  });

// populate phone country codes
  $$("#paxList [data-k='phoneCountry']").forEach((sel, i)=>{
    populateDialCodes(sel);
    sel.value = state.passengers[i].phoneCountry || "+255";
    sel.addEventListener("change", ()=>{
      state.passengers[i].phoneCountry = sel.value;
      computePhone(state.passengers[i]);
      saveState(state);
      updateProgress();
    });
  });

  // bind inputs
  $$("#paxList .pax-card").forEach((card)=>{
    const idx = parseInt(card.dataset.idx, 10);
    const p = state.passengers[idx];

    setupDobDropdowns(card, p);

    // input change
    card.querySelectorAll("[data-k]").forEach((el)=>{
      const key = el.dataset.k;

      if(key === "dob"){
        // Date of birth is handled by the DOB dropdowns (day/month/year) in setupDobDropdowns()
      } else if(el.tagName === "SELECT"){
        el.addEventListener("change", ()=>{
          p[key] = el.value;
          saveState(state);
          updateProgress();
        });
      } else {
        el.addEventListener("input", ()=>{
          p[key] = el.value;
          if(key === "phoneNumber"){
            computePhone(p);
          }
          saveState(state);
          updateProgress();
        });
      }
    });

    // sex toggle
    card.querySelectorAll(`input[name="sex_${idx}"]`).forEach(r=>{
      r.addEventListener("change", ()=>{
        if(r.checked){ p.sex = r.value; saveState(state); }
      });
    });

    // unit toggle
    const toggle = card.querySelector("[data-unit-toggle]");
    const btns = Array.from(toggle.querySelectorAll("button"));
    btns.forEach(btn=>{
      btn.addEventListener("click", ()=>{
        const target = btn.dataset.unit;
        if(p.weightUnit === target) return;
        const val = parseFloat(p.weightValue || "0");
        if(isFinite(val) && val){
          p.weightValue = target === "kg" ? (val / KG2LB).toFixed(1) : (val * KG2LB).toFixed(1);
        }
        p.weightUnit = target;
        btns.forEach(b=> b.classList.toggle("active", b.dataset.unit === target));
        card.querySelector("[data-k='weightValue']").value = p.weightValue || "";
        saveState(state);
      });
    });
  });

  updateProgress();
}


function updateProgress(){
  const want = state.pax || 1;
  // Consider a passenger complete when required fields (first/last name, ID, DOB and nationality) are present.
  const complete = state.passengers.filter((p, i) => p.first && p.last && p.govId && p.dob && p.nationality && (i > 0 || (p.email && p.email.trim()))).length;
  const count = state.passengers.length;
  $("#progress").textContent = `${complete} / ${want} passenger(s) completed`;
  $("#addPassenger").disabled = count >= want;

  const termsOk = !!(state.termsAcceptance && state.termsAcceptance.agreed);
  const ready = (count === want) && (complete === want) && termsOk;
  $("#toPayment").disabled = !ready;

  const btn = $("#toPayment");
  if(!termsOk){
    btn.textContent = "Agree to Terms & Conditions to continue";
  } else {
    btn.textContent = ready ? "Continue to Payment" : (count < want ? `Add ${want - count} more passenger(s)` : "Complete all required fields");
  }
}

$("#addPassenger").addEventListener("click", ()=>{
  const want = state.pax || 1;
  if(state.passengers.length >= want) return;
  state.passengers.push({
    first:"", last:"", govId:"",
    sex:"Female", dob:"", nationality:"",
    weightUnit:"kg", weightValue:"", phone:""
  });
  saveState(state);
  renderPassengers();
initTermsConsent();
updateProgress();
});

$("#backBooking").addEventListener("click", ()=>{
  window.location.href = "booking.html";
});

$("#toPayment").addEventListener("click", async ()=>{
  if(!(state.termsAcceptance && state.termsAcceptance.agreed)){
    alert("Please agree to the Terms & Conditions to continue.");
    const cb = document.getElementById("agreeTerms");
    if(cb) cb.focus();
    return;
  }
  if(!state.passengers[0].phone || !state.passengers[0].phone.trim()){
    alert("Please enter a phone number for Passenger 1 (booking contact).");
    return;
  }
  saveState(state);

  if(state.selected && state.selected.timeEntryId && API_BASE){
    try {
      $("#toPayment").disabled = true;
      $("#toPayment").textContent = "Creating booking…";
      const p0 = state.passengers[0] || {};
      const body = {
        timeEntryId: state.selected.timeEntryId,
        pax: state.pax || state.passengers.length || 1,
        bookerEmail: (p0.email || "").trim() || "customer@flysunbird.local",
        bookerName: `${(p0.first||"").trim()} ${(p0.last||"").trim()}`.trim() || "Customer",
        passengers: state.passengers.map(p=>({
          first: p.first, last: p.last, gender: p.sex || "", dob: p.dob || "",
          nationality: p.nationality || "", idType: "", idNumber: p.govId || "",
          phone: p.phone || ""
        }))
      };
      const created = await apiPost("/public/bookings", body);
      state.bookingRef = created.bookingRef;
      state.paymentStatus = created.paymentStatus || "unpaid";
      state.holdExpiresAt = created.holdExpiresAt || null;
      state.totalUSD = created.totalUSD;
      state.totalTZS = created.totalTZS;
      state.currency = created.currency || state.currency || "USD";
      saveState(state);
      window.location.href = "payment.html?bookingRef=" + encodeURIComponent(state.bookingRef || "");
    } catch(e){
      alert(e.message || String(e));
    } finally {
      $("#toPayment").disabled = false;
      $("#toPayment").textContent = "Continue to Payment";
    }
  } else {
    if(!state.bookingRef) state.bookingRef = makeBookingRef();
    saveState(state);
    window.location.href = "payment.html?bookingRef=" + encodeURIComponent(state.bookingRef || "");
  }
});

initTermsConsent();

renderSummary();
renderPassengers();
