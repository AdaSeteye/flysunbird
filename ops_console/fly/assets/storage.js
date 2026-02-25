/* Shared session storage helpers for multi-page flow */
var STORAGE_KEY = "flysunbird_booking_state_v1";
function loadState() {
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch (e) {
    return null;
  }
}
function saveState(state) {
  sessionStorage.setItem(STORAGE_KEY, JSON.stringify(state));
}
function initState() {
  const s = loadState();
  if (s) {
    if (!s.termsAcceptance) {
      s.termsAcceptance = { agreed:false, agreedAt:null, version:"2025", docSha256:"edfe624c7f9b2dac0ced3b189039f693c0683123f12881d3702b0fcf4d19631d" };
      saveState(s);
    }
    return s;
  }
  const fresh = {
    from: "", to: "", region: "",
    pax: 1,
    currency: "USD",
    date: null,
    selected: null, // {start,end,booked,priceUSD, dateStr}
    termsAcceptance: { agreed:false, agreedAt:null, version:"2025", docSha256:"edfe624c7f9b2dac0ced3b189039f693c0683123f12881d3702b0fcf4d19631d" },
    passengers: []  // array of passenger objects
  };
  saveState(fresh);
  return fresh;
}


// Expose helpers for non-module usage
window.loadState = loadState;
window.saveState = saveState;
window.initState = initState;
