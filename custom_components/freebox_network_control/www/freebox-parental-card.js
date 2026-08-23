/*
 * Freebox Parental Control — bundled Lovelace card
 * Self-contained (no build, no external dependencies). Shipped and
 * auto-registered by the freebox_network_control integration.
 *
 * Usage: add a card of type `custom:freebox-parental-card` to any dashboard.
 * It auto-discovers the integration's schedules sensor.
 */

const WEEKDAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"];
const WEEKDAY_LABELS = {
  mon: "Lun", tue: "Mar", wed: "Mer", thu: "Jeu",
  fri: "Ven", sat: "Sam", sun: "Dim",
};
const DOMAIN = "freebox_network_control";

class FreeboxParentalCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._editing = null; // schedule id, "new", or null
    this._form = null;
    this._hass = null;
    this._built = false;
  }

  setConfig(config) {
    this._config = config || {};
  }

  getCardSize() {
    return 6;
  }

  set hass(hass) {
    this._hass = hass;
    this._render();
  }

  // ---- data helpers -------------------------------------------------------
  _schedulesSensor() {
    if (!this._hass) return null;
    const states = this._hass.states;
    if (this._config.entity && states[this._config.entity]) {
      return states[this._config.entity];
    }
    // auto-discover: a sensor exposing `profiles` and `schedules`
    for (const eid of Object.keys(states)) {
      if (!eid.startsWith("sensor.")) continue;
      const a = states[eid].attributes || {};
      if (Array.isArray(a.profiles) && Array.isArray(a.schedules)) {
        return states[eid];
      }
    }
    return null;
  }

  _profiles() {
    const s = this._schedulesSensor();
    return (s && s.attributes.profiles) || [];
  }

  _schedules() {
    const s = this._schedulesSensor();
    return (s && s.attributes.schedules) || [];
  }

  _switchForProfile(pid) {
    const states = this._hass.states;
    for (const eid of Object.keys(states)) {
      if (!eid.startsWith("switch.")) continue;
      if (states[eid].attributes.profile_id === pid) return eid;
    }
    return null;
  }

  _deviceSensorForProfile(pid) {
    const states = this._hass.states;
    for (const eid of Object.keys(states)) {
      if (!eid.startsWith("sensor.")) continue;
      const a = states[eid].attributes || {};
      if (a.profile_id === pid && Array.isArray(a.device_status)) return eid;
    }
    return null;
  }

  _profileName(pid) {
    const p = this._profiles().find((x) => x.id === pid);
    return p ? p.name : String(pid);
  }

  // ---- service calls ------------------------------------------------------
  _callSwitch(entity, on) {
    this._hass.callService("switch", on ? "turn_on" : "turn_off", {
      entity_id: entity,
    });
  }

  _cutFor(entity, minutes) {
    this._hass.callService(DOMAIN, "cut_for", { entity_id: entity, minutes });
  }

  _saveSchedule(data) {
    this._hass.callService(DOMAIN, "schedule_upsert", data);
    this._editing = null;
    this._form = null;
    this._render(true);
  }

  _deleteSchedule(id) {
    this._hass.callService(DOMAIN, "schedule_delete", { id });
    this._editing = null;
    this._form = null;
    this._render(true);
  }

  _daysSummary(days) {
    days = WEEKDAYS.filter((d) => (days || []).includes(d));
    if (!days.length) return "aucun jour";
    if (days.length === 7) return "tous les jours";
    if (JSON.stringify(days) === JSON.stringify(["mon","tue","wed","thu","fri"]))
      return "en semaine";
    if (JSON.stringify(days) === JSON.stringify(["sat","sun"]))
      return "le week-end";
    return days.map((d) => WEEKDAY_LABELS[d]).join(", ");
  }

  // ---- rendering ----------------------------------------------------------
  _render(force) {
    if (!this._hass) return;
    const sensor = this._schedulesSensor();
    if (!sensor) {
      this.shadowRoot.innerHTML =
        `<ha-card><div class="empty">Intégration Freebox Parental Control introuvable.</div></ha-card>` +
        this._styles();
      return;
    }

    // Don't clobber an open editor on background hass updates.
    if (this._editing && !force && this._built) {
      this._refreshDynamic();
      return;
    }

    const profiles = this._profiles();
    const schedules = this._schedules();

    let html = `<ha-card><div class="wrap">`;
    html += `<div class="title"><ha-icon icon="mdi:shield-account"></ha-icon> Contrôle parental Freebox</div>`;

    // --- profiles ---
    html += `<div class="section">Internet par profil</div>`;
    for (const p of profiles) {
      const sw = this._switchForProfile(p.id);
      const on = sw ? this._hass.states[sw].state === "on" : false;
      const dsE = this._deviceSensorForProfile(p.id);
      const ds = dsE ? this._hass.states[dsE].attributes : {};
      const online = ds.online_count != null ? ds.online_count : 0;
      const total = ds.devices ? ds.devices.length : 0;
      html += `
        <div class="profile">
          <div class="prow">
            <div class="pname">
              <ha-icon icon="mdi:account"></ha-icon>
              <span>${p.name}</span>
              <span class="badge">${online}/${total} en ligne</span>
            </div>
            <label class="switch">
              <input type="checkbox" data-sw="${sw}" ${on ? "checked" : ""}>
              <span class="slider"></span>
            </label>
          </div>
          <div class="cutrow">
            <span class="cutlabel">Couper :</span>
            <button class="chip" data-cut="${sw}" data-min="30">30 min</button>
            <button class="chip" data-cut="${sw}" data-min="60">1 h</button>
            <button class="chip" data-cut="${sw}" data-min="120">2 h</button>
          </div>
        </div>`;
    }

    // --- schedules ---
    html += `<div class="section">Programmations
      <button class="add" data-add="1"><ha-icon icon="mdi:plus"></ha-icon> Ajouter</button></div>`;

    if (this._editing) {
      html += this._editorHtml();
    } else if (!schedules.length) {
      html += `<div class="empty small">Aucune programmation. Cliquez sur « Ajouter ».</div>`;
    } else {
      for (const s of schedules) {
        const state = s.enabled ? "✅" : "⏸️";
        html += `
          <div class="sched">
            <div class="sinfo" data-edit="${s.id}">
              <div class="sname">${state} ${s.name}</div>
              <div class="smeta">${this._profileName(s.profile_id)} · ${(s.cut||"").slice(0,5)} → ${(s.restore||"").slice(0,5)} · ${this._daysSummary(s.days)}</div>
            </div>
            <div class="sactions">
              <ha-icon class="iconbtn" icon="mdi:pencil" data-edit="${s.id}"></ha-icon>
              <ha-icon class="iconbtn danger" icon="mdi:delete" data-del="${s.id}"></ha-icon>
            </div>
          </div>`;
      }
    }

    html += `</div></ha-card>` + this._styles();
    this.shadowRoot.innerHTML = html;
    this._built = true;
    this._bind();
  }

  _editorHtml() {
    const profiles = this._profiles();
    const f = this._form || {};
    const days = f.days || ["mon", "tue", "wed", "thu", "fri"];
    const dayBtns = WEEKDAYS.map(
      (d) =>
        `<button class="day ${days.includes(d) ? "on" : ""}" data-day="${d}">${WEEKDAY_LABELS[d]}</button>`
    ).join("");
    const profOpts = profiles
      .map(
        (p) =>
          `<option value="${p.id}" ${String(f.profile_id) === String(p.id) ? "selected" : ""}>${p.name}</option>`
      )
      .join("");
    return `
      <div class="editor">
        <label>Nom<input type="text" id="f_name" value="${(f.name || "").replace(/"/g, "&quot;")}" placeholder="Ex. Semaine, Week-end"></label>
        <label>Profil<select id="f_profile">${profOpts}</select></label>
        <div class="times">
          <label>Coupure<input type="time" id="f_cut" value="${f.cut || "21:00"}"></label>
          <label>Rétablissement<input type="time" id="f_restore" value="${f.restore || "07:00"}"></label>
        </div>
        <div class="dayrow">${dayBtns}</div>
        <label class="chkline"><input type="checkbox" id="f_enabled" ${f.enabled === false ? "" : "checked"}> Activer</label>
        <div class="edbtns">
          <button class="cancel" data-cancel="1">Annuler</button>
          <button class="save" data-save="1">Enregistrer</button>
        </div>
      </div>`;
  }

  _refreshDynamic() {
    // Light refresh of switch states while editor is open.
    for (const p of this._profiles()) {
      const sw = this._switchForProfile(p.id);
      if (!sw) continue;
      const box = this.shadowRoot.querySelector(`input[data-sw="${sw}"]`);
      if (box) box.checked = this._hass.states[sw].state === "on";
    }
  }

  _bind() {
    const root = this.shadowRoot;

    root.querySelectorAll('input[data-sw]').forEach((el) =>
      el.addEventListener("change", (e) =>
        this._callSwitch(e.target.getAttribute("data-sw"), e.target.checked)
      )
    );
    root.querySelectorAll("[data-cut]").forEach((el) =>
      el.addEventListener("click", (e) => {
        const b = e.currentTarget;
        this._cutFor(b.getAttribute("data-cut"), parseInt(b.getAttribute("data-min"), 10));
      })
    );
    root.querySelectorAll("[data-add]").forEach((el) =>
      el.addEventListener("click", () => {
        this._editing = "new";
        this._form = { name: "", profile_id: (this._profiles()[0] || {}).id, cut: "21:00", restore: "07:00", days: ["mon","tue","wed","thu","fri"], enabled: true };
        this._render(true);
      })
    );
    root.querySelectorAll("[data-edit]").forEach((el) =>
      el.addEventListener("click", (e) => {
        const id = e.currentTarget.getAttribute("data-edit");
        const s = this._schedules().find((x) => x.id === id);
        if (!s) return;
        this._editing = id;
        this._form = {
          id: s.id, name: s.name, profile_id: s.profile_id,
          cut: (s.cut || "21:00").slice(0, 5), restore: (s.restore || "07:00").slice(0, 5),
          days: (s.days || []).slice(), enabled: s.enabled !== false,
        };
        this._render(true);
      })
    );
    root.querySelectorAll("[data-del]").forEach((el) =>
      el.addEventListener("click", (e) =>
        this._deleteSchedule(e.currentTarget.getAttribute("data-del"))
      )
    );

    // editor bindings
    root.querySelectorAll("[data-day]").forEach((el) =>
      el.addEventListener("click", (e) => {
        const d = e.currentTarget.getAttribute("data-day");
        const days = new Set(this._form.days || []);
        if (days.has(d)) days.delete(d); else days.add(d);
        this._form.days = WEEKDAYS.filter((x) => days.has(x));
        e.currentTarget.classList.toggle("on");
      })
    );
    const cancel = root.querySelector("[data-cancel]");
    if (cancel) cancel.addEventListener("click", () => { this._editing = null; this._form = null; this._render(true); });
    const save = root.querySelector("[data-save]");
    if (save) save.addEventListener("click", () => this._onSave());
  }

  _onSave() {
    const root = this.shadowRoot;
    const name = root.querySelector("#f_name").value.trim() || "Programmation";
    const profile_id = parseInt(root.querySelector("#f_profile").value, 10);
    const cut = root.querySelector("#f_cut").value || "21:00";
    const restore = root.querySelector("#f_restore").value || "07:00";
    const enabled = root.querySelector("#f_enabled").checked;
    const days = (this._form.days && this._form.days.length) ? this._form.days : ["mon","tue","wed","thu","fri"];
    const data = { name, profile_id, cut, restore, enabled, days };
    if (this._editing && this._editing !== "new") data.id = this._editing;
    this._saveSchedule(data);
  }

  _styles() {
    return `<style>
      ha-card { padding: 0; }
      .wrap { padding: 12px 14px 16px; }
      .title { font-size: 1.15rem; font-weight: 600; display:flex; align-items:center; gap:8px; margin-bottom: 6px; }
      .title ha-icon { color: var(--primary-color); }
      .section { margin: 14px 0 6px; font-weight: 600; color: var(--secondary-text-color);
                 text-transform: uppercase; font-size: 0.72rem; letter-spacing: .5px;
                 display:flex; align-items:center; justify-content:space-between; }
      .profile { border:1px solid var(--divider-color); border-radius:10px; padding:8px 10px; margin-bottom:8px; }
      .prow { display:flex; align-items:center; justify-content:space-between; }
      .pname { display:flex; align-items:center; gap:8px; font-weight:500; }
      .pname ha-icon { color: var(--secondary-text-color); }
      .badge { font-size:.7rem; color:var(--secondary-text-color); background:var(--secondary-background-color);
               padding:2px 7px; border-radius:10px; font-weight:400; }
      .cutrow { display:flex; align-items:center; gap:6px; margin-top:8px; flex-wrap:wrap; }
      .cutlabel { font-size:.75rem; color:var(--secondary-text-color); }
      .chip { border:1px solid var(--divider-color); background:transparent; color:var(--primary-text-color);
              border-radius:14px; padding:3px 10px; font-size:.75rem; cursor:pointer; }
      .chip:hover { background: var(--secondary-background-color); }
      .add { border:none; background:transparent; color:var(--primary-color); cursor:pointer;
             font-size:.75rem; display:flex; align-items:center; gap:2px; }
      .add ha-icon { --mdc-icon-size:16px; }
      .sched { display:flex; align-items:center; justify-content:space-between;
               border:1px solid var(--divider-color); border-radius:10px; padding:8px 10px; margin-bottom:6px; }
      .sinfo { cursor:pointer; flex:1; }
      .sname { font-weight:500; }
      .smeta { font-size:.75rem; color:var(--secondary-text-color); margin-top:2px; }
      .sactions { display:flex; gap:10px; }
      .iconbtn { cursor:pointer; color:var(--secondary-text-color); --mdc-icon-size:20px; }
      .iconbtn:hover { color:var(--primary-color); }
      .iconbtn.danger:hover { color: var(--error-color); }
      .editor { border:1px solid var(--primary-color); border-radius:10px; padding:12px; margin-bottom:8px;
                display:flex; flex-direction:column; gap:10px; }
      .editor label { display:flex; flex-direction:column; font-size:.75rem; color:var(--secondary-text-color); gap:3px; }
      .editor input[type=text], .editor input[type=time], .editor select {
        padding:7px; border-radius:7px; border:1px solid var(--divider-color);
        background:var(--card-background-color); color:var(--primary-text-color); font-size:.9rem; }
      .times { display:flex; gap:10px; }
      .times label { flex:1; }
      .dayrow { display:flex; gap:4px; flex-wrap:wrap; }
      .day { border:1px solid var(--divider-color); background:transparent; color:var(--primary-text-color);
             border-radius:8px; padding:5px 9px; font-size:.75rem; cursor:pointer; }
      .day.on { background:var(--primary-color); color:var(--text-primary-color,#fff); border-color:var(--primary-color); }
      .chkline { flex-direction:row !important; align-items:center; gap:6px; color:var(--primary-text-color) !important; }
      .edbtns { display:flex; justify-content:flex-end; gap:8px; margin-top:2px; }
      .cancel { background:transparent; border:none; color:var(--secondary-text-color); cursor:pointer; padding:8px 12px; }
      .save { background:var(--primary-color); color:var(--text-primary-color,#fff); border:none;
              border-radius:8px; padding:8px 16px; cursor:pointer; font-weight:500; }
      .empty { padding:16px; text-align:center; color:var(--secondary-text-color); }
      .empty.small { padding:10px; font-size:.85rem; }
      /* switch */
      .switch { position:relative; display:inline-block; width:42px; height:24px; }
      .switch input { opacity:0; width:0; height:0; }
      .slider { position:absolute; cursor:pointer; inset:0; background:var(--switch-unchecked-color,#9e9e9e);
                border-radius:24px; transition:.2s; }
      .slider:before { position:absolute; content:""; height:18px; width:18px; left:3px; bottom:3px;
                       background:#fff; border-radius:50%; transition:.2s; }
      .switch input:checked + .slider { background:var(--primary-color); }
      .switch input:checked + .slider:before { transform:translateX(18px); }
    </style>`;
  }
}

customElements.define("freebox-parental-card", FreeboxParentalCard);

window.customCards = window.customCards || [];
window.customCards.push({
  type: "freebox-parental-card",
  name: "Freebox Parental Control",
  description: "Contrôle parental Freebox : profils, coupures et programmations.",
});

console.info("%c FREEBOX-PARENTAL-CARD ", "background:#e30613;color:#fff;border-radius:3px", "loaded");
