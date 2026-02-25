// Admin/Ops store (localStorage) for Locations, FX, Terms and demo routes/slotPlans.

const AdminStore = (() => {
  const KEY = "flysunbird_admin_store_v1";

  const uid = (p="id") => `${p}_${Math.random().toString(16).slice(2)}_${Date.now().toString(16)}`;
  const todayISO = () => new Date().toISOString().slice(0,10);

  const seed = () => ({
    locations: [
      {id: uid("loc"), region:"Tanzania", code:"DAR", name:"Dar es Salaam", subs:["City Center","Airport"], active:true},
      {id: uid("loc"), region:"Tanzania", code:"ZNZ", name:"Zanzibar", subs:["Stone Town","Nungwi","Kendwa Rocks","Airport"], active:true},
    ],
    routes: [
      {id: uid("rt"), from:"Dar es Salaam (DAR)", to:"Zanzibar (ZNZ)", region:"Tanzania", active:true},
      {id: uid("rt"), from:"Zanzibar (ZNZ)", to:"Dar es Salaam (DAR)", region:"Tanzania", active:true},
    ],
    // slot inventory keyed by (from,to,dateStr)
    slotPlans: [
      {
        id: uid("plan"),
        from:"Dar es Salaam (DAR)",
        to:"Zanzibar (ZNZ)",
        region:"Tanzania",
        currency:"USD",
        dateStr: todayISO(),
        slots: [
          {start:"09:00", end:"10:10", priceUSD:220, seatsAvailable:3, flightNo:"FSB101", cabin:"Economy", baggage:"Cabin baggage"},
          {start:"15:00", end:"16:10", priceUSD:240, seatsAvailable:2, flightNo:"FSB103", cabin:"Economy", baggage:"Cabin baggage"},
        ]
      }
    ],
    fx: { default:"USD", enabled:["USD","TZS"], tzsPerUsd: 2450 },
    terms: { version:"2025", docSha256:"edfe624c7f9b2dac0ced3b189039f693c0683123f12881d3702b0fcf4d19631d", url:"fly/terms-and-conditions.html" },
    payments: [], // future
    bookings: []  // future
  });

  const load = () => {
    try{
      const raw = localStorage.getItem(KEY);
      if(!raw){
        const s = seed();
        localStorage.setItem(KEY, JSON.stringify(s));
        return s;
      }
      return JSON.parse(raw);
    }catch(e){
      const s = seed();
      localStorage.setItem(KEY, JSON.stringify(s));
      return s;
    }
  };

  const save = (data) => localStorage.setItem(KEY, JSON.stringify(data));
  const reset = () => { const s=seed(); save(s); return s; };

  // Locations
  const listLocations = () => load().locations;
  const addLocation = (loc) => {
    const d=load();
    const x={id: uid("loc"), region:loc.region||"", code:loc.code||"", name:loc.name||"", subs:loc.subs||[], active:true};
    d.locations.unshift(x); save(d); return x;
  };
  const updateLocation = (id, patch) => { const d=load(); const x=d.locations.find(a=>a.id===id); if(!x) return null; Object.assign(x,patch); save(d); return x; };
  const deleteLocation = (id) => { const d=load(); d.locations=d.locations.filter(a=>a.id!==id); save(d); return true; };

  // Routes
  const listRoutes = () => load().routes;
  const addRoute = (r) => { const d=load(); const x={id: uid("rt"), ...r, active:true}; d.routes.unshift(x); save(d); return x; };
  const updateRoute = (id, patch) => { const d=load(); const x=d.routes.find(a=>a.id===id); if(!x) return null; Object.assign(x,patch); save(d); return x; };
  const deleteRoute = (id) => { const d=load(); d.routes=d.routes.filter(a=>a.id!==id); save(d); return true; };

  // Slot plans
  const listSlotPlans = () => load().slotPlans;
  const upsertSlotPlan = (plan) => {
    const d=load();
    let x = d.slotPlans.find(p => p.from===plan.from && p.to===plan.to && p.dateStr===plan.dateStr);
    if(!x){
      x={id: uid("plan"), from:plan.from, to:plan.to, region:plan.region||"", currency:plan.currency||"USD", dateStr:plan.dateStr, slots:[]};
      d.slotPlans.unshift(x);
    }
    x.region = plan.region||x.region;
    x.currency = plan.currency||x.currency;
    x.slots = Array.isArray(plan.slots) ? plan.slots : x.slots;
    save(d);
    return x;
  };
  const deleteSlotPlan = (id) => { const d=load(); d.slotPlans=d.slotPlans.filter(p=>p.id!==id); save(d); return true; };

  // FX / Terms
  const getFx = () => load().fx;
  const setFx = (fx) => { const d=load(); d.fx = {...d.fx, ...fx}; save(d); return d.fx; };

  const getTerms = () => load().terms;
  const setTerms = (t) => { const d=load(); d.terms = {...d.terms, ...t}; save(d); return d.terms; };

  return {
    load, save, reset,
    listLocations, addLocation, updateLocation, deleteLocation,
    listRoutes, addRoute, updateRoute, deleteRoute,
    listSlotPlans, upsertSlotPlan, deleteSlotPlan,
    getFx, setFx,
    getTerms, setTerms
  };
})();

// Helpers
function b64urlEncode(str){
  const b64 = btoa(unescape(encodeURIComponent(str)));
  return b64.replace(/\+/g,'-').replace(/\//g,'_').replace(/=+$/,'');
}
