/**
 * iPhone-like wheel date picker (no typing).
 * Usage:
 *   const picker = new DateWheelPicker({ title: "Date of birth", min: "1900-01-01", max: "2026-01-31" });
 *   picker.attachTo(inputEl, (isoDate)=>{ ... });
 */
class DateWheelPicker {
  constructor({ title="Select date", min="1900-01-01", max=null } = {}) {
    this.title = title;
    this.min = new Date(min + "T00:00:00");
    this.max = max ? new Date(max + "T00:00:00") : null;
    this.onSelect = null;
    this._build();
  }

  _build(){
    const sheet = document.createElement("div");
    sheet.className = "sheet";
    sheet.innerHTML = `
      <div class="backdrop" data-close></div>
      <div class="panel" role="dialog" aria-modal="true">
        <div class="top">
          <button class="btn" type="button" data-close>Cancel</button>
          <div class="title">${this.title}</div>
          <button class="btn primary" type="button" data-done>Done</button>
        </div>
        <div class="wheels">
          <div class="wheel" data-wheel="day"></div>
          <div class="wheel" data-wheel="month"></div>
          <div class="wheel" data-wheel="year"></div>
        </div>
        <div class="hint" style="padding:10px 6px 4px">
          Tip: swipe/scroll each column. The highlighted row is selected.
        </div>
      </div>
    `;
    document.body.appendChild(sheet);
    this.sheet = sheet;
    this.wDay = sheet.querySelector('[data-wheel="day"]');
    this.wMonth = sheet.querySelector('[data-wheel="month"]');
    this.wYear = sheet.querySelector('[data-wheel="year"]');

    sheet.querySelectorAll("[data-close]").forEach(el => el.addEventListener("click", ()=>this.close()));
    sheet.querySelector("[data-done]").addEventListener("click", ()=>this._done());

    // close on ESC
    document.addEventListener("keydown", (e)=>{
      if(e.key === "Escape" && this.sheet.classList.contains("open")) this.close();
    });
  }

  attachTo(input, onSelect){
    this.onSelect = onSelect;
    input.setAttribute("readonly", "readonly");
    input.addEventListener("click", ()=> this.open(input.value || null));
    input.addEventListener("keydown", (e)=> e.preventDefault());
  }

  open(initialISO=null){
    this._populateWheels(initialISO);
    this.sheet.classList.add("open");
    // lock page scroll
    document.documentElement.style.overflow = "hidden";
    document.body.style.overflow = "hidden";
  }

  close(){
    this.sheet.classList.remove("open");
    document.documentElement.style.overflow = "";
    document.body.style.overflow = "";
  }

  _populateWheels(initialISO){
    const now = new Date();
    const init = initialISO ? new Date(initialISO + "T00:00:00") : now;
    const initDate = isNaN(init) ? now : init;

    // years
    const yMax = (this.max ? this.max.getFullYear() : now.getFullYear());
    const yMin = this.min.getFullYear();
    const years = [];
    for(let y=yMax; y>=yMin; y--) years.push(y); // reverse like iOS
    this._fillWheel(this.wYear, years.map(y=>({v:y, label:String(y)})));

    // months 1-12
    const months = Array.from({length:12}, (_,i)=> i+1);
    const monthLabels = months.map(m=>{
      const d = new Date(2020, m-1, 1);
      return d.toLocaleString("en", { month:"short" });
    });
    this._fillWheel(this.wMonth, months.map((m,i)=>({v:m, label: monthLabels[i]})));

    // days depends on month/year
    const targetY = this._clamp(initDate.getFullYear(), yMin, yMax);
    const targetM = this._clamp(initDate.getMonth()+1, 1, 12);
    this._fillDays(targetY, targetM);

    // set initial positions
    this._scrollToValue(this.wYear, targetY);
    this._scrollToValue(this.wMonth, targetM);
    this._scrollToValue(this.wDay, initDate.getDate());

    // when year/month scroll changes -> adjust days
    const onChange = ()=>{
      const y = this._getSelectedValue(this.wYear);
      const m = this._getSelectedValue(this.wMonth);
      const prevD = this._getSelectedValue(this.wDay) || 1;
      this._fillDays(y, m);
      this._scrollToValue(this.wDay, Math.min(prevD, this._daysInMonth(y,m)));
    };
    // throttle events
    let t=null;
    const bindWheel = (wheel)=>{
      wheel.addEventListener("scroll", ()=>{
        if(t) clearTimeout(t);
        t=setTimeout(onChange, 120);
      }, { passive:true });
    };
    bindWheel(this.wYear); bindWheel(this.wMonth);
  }

  _fillDays(y, m){
    const days = Array.from({length: this._daysInMonth(y,m)}, (_,i)=> i+1);
    this._fillWheel(this.wDay, days.map(d=>({v:d, label:String(d)})));
  }

  _fillWheel(wheel, items){
    wheel.innerHTML = items.map(it=>`<div class="opt" data-v="${it.v}">${it.label}</div>`).join("");
  }

  _getSelectedValue(wheel){
    const opts = Array.from(wheel.querySelectorAll(".opt"));
    if(!opts.length) return null;
    const mid = wheel.scrollTop + wheel.clientHeight/2;
    let best = opts[0], bestDist = Infinity;
    for(const o of opts){
      const top = o.offsetTop + o.offsetHeight/2;
      const dist = Math.abs(top - mid);
      if(dist < bestDist){ bestDist = dist; best = o; }
    }
    return parseInt(best.dataset.v, 10);
  }

  _scrollToValue(wheel, value){
    const el = wheel.querySelector(`.opt[data-v="${value}"]`);
    if(!el) return;
    // center it
    const target = el.offsetTop - (wheel.clientHeight/2 - el.offsetHeight/2);
    wheel.scrollTop = target;
  }

  _daysInMonth(y,m){
    return new Date(y, m, 0).getDate();
  }

  _clamp(n, a, b){ return Math.max(a, Math.min(b, n)); }

  _done(){
    const y = this._getSelectedValue(this.wYear);
    const m = this._getSelectedValue(this.wMonth);
    const d = this._getSelectedValue(this.wDay);
    if(!y || !m || !d) return;

    const iso = `${y}-${String(m).padStart(2,"0")}-${String(d).padStart(2,"0")}`;
    const dt = new Date(iso + "T00:00:00");
    if(dt < this.min) return;
    if(this.max && dt > this.max) return;

    this.close();
    if(this.onSelect) this.onSelect(iso);
  }
}


window.DateWheelPicker = DateWheelPicker;
