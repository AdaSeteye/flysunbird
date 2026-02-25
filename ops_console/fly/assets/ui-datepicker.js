
/**
 * PopupDatePicker - lightweight, dependency-free calendar modal.
 * - Accessible: ESC closes, focus trap basic, click outside closes.
 * - Outputs ISO date YYYY-MM-DD
 */
class PopupDatePicker {
  constructor(opts = {}) {
    this.title = opts.title || "Select date";
    this.min = opts.min || "1900-01-01";
    this.max = opts.max || new Date().toISOString().slice(0,10);
    this._onSelect = null;
    this._input = null;

    const today = new Date();
    this._viewYear = today.getFullYear();
    this._viewMonth = today.getMonth(); // 0-11

    // If input has a value, start there
    this._opened = false;
    this._modal = null;
  }

  attachTo(inputEl, onSelect) {
    this._input = inputEl;
    this._onSelect = onSelect;

    // Initialize view to current value if valid
    const v = (inputEl.value || "").trim();
    const d = this._parseISO(v);
    if (d) { this._viewYear = d.getFullYear(); this._viewMonth = d.getMonth(); }

    // Click opens
    inputEl.addEventListener("click", (e) => {
      e.preventDefault();
      this.open();
    });
    inputEl.addEventListener("keydown", (e) => {
      if (e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        this.open();
      }
    });
  }

  open() {
    if (this._opened) return;
    this._opened = true;

    // Build modal
    const overlay = document.createElement("div");
    overlay.className = "dp-overlay";
    overlay.innerHTML = `
      <div class="dp-modal" role="dialog" aria-modal="true" aria-label="${this._esc(this.title)}">
        <div class="dp-head">
          <div class="dp-title">${this._esc(this.title)}</div>
          <button type="button" class="dp-x" aria-label="Close">✕</button>
        </div>
        <div class="dp-nav">
          <button type="button" class="dp-navbtn" data-act="prev" aria-label="Previous month">‹</button>
          <div class="dp-month" aria-live="polite"></div>
          <button type="button" class="dp-navbtn" data-act="next" aria-label="Next month">›</button>
        </div>
        <div class="dp-dow" aria-hidden="true">
          <span>Mo</span><span>Tu</span><span>We</span><span>Th</span><span>Fr</span><span>Sa</span><span>Su</span>
        </div>
        <div class="dp-grid"></div>
        <div class="dp-foot">
          <button type="button" class="dp-btn" data-act="today">Today</button>
          <button type="button" class="dp-btn dp-btn-primary" data-act="done">Done</button>
        </div>
      </div>
    `;

    document.body.appendChild(overlay);
    this._modal = overlay;

    const close = () => this.close();
    overlay.addEventListener("click", (e) => { if (e.target === overlay) close(); });
    overlay.querySelector(".dp-x").addEventListener("click", close);

    overlay.querySelector('[data-act="prev"]').addEventListener("click", ()=>{ this._shiftMonth(-1); });
    overlay.querySelector('[data-act="next"]').addEventListener("click", ()=>{ this._shiftMonth(1); });

    overlay.querySelector('[data-act="today"]').addEventListener("click", ()=> {
      const iso = new Date().toISOString().slice(0,10);
      this._selectISO(iso);
      this._setViewFromISO(iso);
      this._render();
    });

    overlay.querySelector('[data-act="done"]').addEventListener("click", ()=> {
      // If nothing selected, do nothing; otherwise close.
      this.close();
    });

    this._render();

    // Key handling
    this._keyHandler = (e) => {
      if (!this._opened) return;
      if (e.key === "Escape") { e.preventDefault(); this.close(); }
    };
    document.addEventListener("keydown", this._keyHandler);

    // Focus
    const firstBtn = overlay.querySelector(".dp-x");
    firstBtn && firstBtn.focus();
  }

  close() {
    if (!this._opened) return;
    this._opened = false;
    if (this._modal) {
      this._modal.remove();
      this._modal = null;
    }
    if (this._keyHandler) {
      document.removeEventListener("keydown", this._keyHandler);
      this._keyHandler = null;
    }
    if (this._input) this._input.focus();
  }

  _render() {
    if (!this._modal) return;
    const monthEl = this._modal.querySelector(".dp-month");
    const gridEl = this._modal.querySelector(".dp-grid");

    const monthName = new Date(this._viewYear, this._viewMonth, 1).toLocaleString(undefined, { month: "long", year: "numeric" });
    monthEl.textContent = monthName;

    // Build days
    gridEl.innerHTML = "";
    const first = new Date(this._viewYear, this._viewMonth, 1);
    const last = new Date(this._viewYear, this._viewMonth + 1, 0);
    // Monday-based: convert JS Sunday=0.. to Monday=0..
    const firstDow = (first.getDay() + 6) % 7;
    const daysInMonth = last.getDate();

    const minD = this._parseISO(this.min);
    const maxD = this._parseISO(this.max);

    const current = this._parseISO((this._input?.value||"").trim());
    const currentISO = current ? this._toISO(current) : null;

    // Fill leading blanks
    for (let i=0;i<firstDow;i++){
      const b = document.createElement("div");
      b.className = "dp-cell dp-blank";
      gridEl.appendChild(b);
    }

    for (let day=1; day<=daysInMonth; day++){
      const d = new Date(this._viewYear, this._viewMonth, day);
      const iso = this._toISO(d);
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "dp-cell dp-day";
      btn.textContent = String(day);
      btn.dataset.iso = iso;

      const disabled = (minD && d < minD) || (maxD && d > maxD);
      if (disabled) {
        btn.disabled = true;
        btn.classList.add("is-disabled");
      }
      if (currentISO && iso === currentISO) btn.classList.add("is-selected");

      btn.addEventListener("click", () => {
        this._selectISO(iso);
        // highlight immediately
        this._modal.querySelectorAll(".dp-day.is-selected").forEach(el=>el.classList.remove("is-selected"));
        btn.classList.add("is-selected");
      });

      gridEl.appendChild(btn);
    }
  }

  _selectISO(iso) {
    if (!this._input) return;
    this._input.value = iso;
    if (typeof this._onSelect === "function") this._onSelect(iso);
  }

  _shiftMonth(delta) {
    let m = this._viewMonth + delta;
    let y = this._viewYear;
    if (m < 0) { m = 11; y -= 1; }
    if (m > 11) { m = 0; y += 1; }
    this._viewMonth = m;
    this._viewYear = y;
    this._render();
  }

  _setViewFromISO(iso) {
    const d = this._parseISO(iso);
    if (!d) return;
    this._viewYear = d.getFullYear();
    this._viewMonth = d.getMonth();
  }

  _parseISO(iso) {
    if (!iso || !/^\d{4}-\d{2}-\d{2}$/.test(iso)) return null;
    const [y,m,d] = iso.split("-").map(n=>parseInt(n,10));
    const dt = new Date(y, m-1, d);
    if (dt.getFullYear()!==y || dt.getMonth()!==m-1 || dt.getDate()!==d) return null;
    return dt;
  }

  _toISO(d) {
    const y = d.getFullYear();
    const m = String(d.getMonth()+1).padStart(2,"0");
    const da = String(d.getDate()).padStart(2,"0");
    return `${y}-${m}-${da}`;
  }

  _esc(s) {
    return String(s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  }
}


window.PopupDatePicker = PopupDatePicker;
