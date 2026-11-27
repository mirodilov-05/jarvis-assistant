/* Jarvis — application shell: data, router, home dashboard with configurable widgets, command search, presentation.
 * Pages for the other sections live in pages.js (window.PAGES) and help.js. */
(function () {
  "use strict";

  /* ---------- helpers ---------- */
  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => [...r.querySelectorAll(s)];
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
  const num = (v, d = 0) => (v == null || Number.isNaN(Number(v)) ? "—" : Number(v).toFixed(d));
  const ymd = (d = new Date()) => d.toLocaleDateString("sv-SE");
  const hm = (d) => (d ? new Date(d).toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" }) : "");
  const dmy = (d) => (d ? new Date(d).toLocaleString("ru-RU", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" }) : "");
  const dur = (s) => { s = Math.max(0, Math.round(s)); const m = Math.floor(s / 60), r = s % 60; return `${String(m).padStart(2, "0")}:${String(r).padStart(2, "0")}`; };
  const rate = (b) => (b >= 1048576 ? (b / 1048576).toFixed(1) + " МБ/с" : Math.round(b / 1024) + " КБ/с");
  const plural = (n, a, b, c) => (n % 10 === 1 && n % 100 !== 11 ? a : n % 10 >= 2 && n % 10 <= 4 && (n % 100 < 10 || n % 100 >= 20) ? b : c);

  async function api(path, method = "GET", body) {
    const opt = { method, headers: {} };
    if (method !== "GET") { opt.headers["Content-Type"] = "application/json"; opt.headers["X-Jarvis"] = "1"; }
    if (body !== undefined) opt.body = JSON.stringify(body);
    const r = await fetch(path, opt);
    const ct = r.headers.get("content-type") || "";
    const data = ct.includes("json") ? await r.json() : await r.text();
    if (!r.ok) {
      const msg = (data && (data.message || data.error || data.reply)) || r.statusText || "ошибка";
      throw Object.assign(new Error(msg), { data, status: r.status });
    }
    return data;
  }
  let toastT = 0;
  function toast(text) {
    const t = $("#toast"); t.textContent = text; t.classList.add("show");
    clearTimeout(toastT); toastT = setTimeout(() => t.classList.remove("show"), 2800);
  }
  /* A dialog that returns a promise: resolves true for the primary button. */
  function ask({ title, text = "", html = "", yes = "Да", no = "Отмена", danger = false }) {
    return new Promise((res) => {
      const d = $("#dlg");
      d.innerHTML = `<h3 id="dlgTitle">${esc(title)}</h3>${text ? `<p>${esc(text)}</p>` : ""}${html}
        <div class="bs"><button class="btn" value="no">${esc(no)}</button>${yes ? `<button class="btn ${danger ? "danger" : "primary"}" value="yes">${esc(yes)}</button>` : ""}</div>`;
      d.onclose = () => res(d.returnValue === "yes");
      d.returnValue = "";
      d.querySelectorAll("button[value]").forEach((b) => { b.onclick = () => d.close(b.value); });
      d.showModal();
      const first = d.querySelector("input,select,textarea,button.primary,button.danger");
      setTimeout(() => first && first.focus(), 30);
    });
  }
  function dialog(html, title = "") {
    const d = $("#dlg");
    d.innerHTML = (title ? `<h3 id="dlgTitle">${esc(title)}</h3>` : "") + html + `<div class="bs"><button class="btn" value="close">Закрыть</button></div>`;
    d.onclose = () => {};
    d.querySelector('button[value="close"]').onclick = () => d.close();
    d.showModal();
    return d;
  }

  /* ---------- icons (simple outlines) ---------- */
  const ICON = {
    cpu: '<rect x="6" y="6" width="12" height="12" rx="2"/><path d="M9 2v4M15 2v4M9 18v4M15 18v4M2 9h4M2 15h4M18 9h4M18 15h4"/>',
    goal: '<circle cx="12" cy="12" r="8"/><circle cx="12" cy="12" r="3"/>',
    task: '<rect x="4" y="4" width="16" height="16" rx="3"/><path d="M8 12l3 3 5-6"/>',
    focus: '<circle cx="12" cy="13" r="8"/><path d="M12 9v4l2.5 2M9 2h6"/>',
    weather: '<path d="M7 18h10a4 4 0 0 0 .5-8A6 6 0 0 0 6 9.5 4.3 4.3 0 0 0 7 18z"/>',
    net: '<path d="M2 9a15 15 0 0 1 20 0M5 12.5a10 10 0 0 1 14 0M8.5 16a5 5 0 0 1 7 0M12 20h.01"/>',
    battery: '<rect x="2" y="7" width="18" height="10" rx="2"/><path d="M22 11v2"/>',
    sound: '<path d="M4 10v4h4l5 4V6L8 10z"/><path d="M16.5 9a4 4 0 0 1 0 6"/>',
    display: '<rect x="2" y="4" width="20" height="13" rx="2"/><path d="M8 21h8M12 17v4"/>',
    apps: '<rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/>',
    tv: '<rect x="2" y="5" width="20" height="13" rx="2"/><path d="M8 21l4-3 4 3"/>',
    cal: '<rect x="3" y="5" width="18" height="16" rx="2"/><path d="M3 10h18M8 3v4M16 3v4"/>',
    msg: '<path d="M21 12a8 8 0 0 1-11.6 7.1L4 20l1-4.6A8 8 0 1 1 21 12z"/>',
    brain: '<path d="M9 4a3 3 0 0 0-3 3v1a3 3 0 0 0-2 5 3 3 0 0 0 2 5 3 3 0 0 0 6 1V4z"/><path d="M15 4a3 3 0 0 1 3 3v1a3 3 0 0 1 2 5 3 3 0 0 1-2 5 3 3 0 0 1-6 1V4z"/>',
    history: '<path d="M3 12a9 9 0 1 0 3-6.7L3 8"/><path d="M3 3v5h5M12 7v5l3 2"/>',
    memory: '<path d="M4 6c0-1.7 3.6-3 8-3s8 1.3 8 3-3.6 3-8 3-8-1.3-8-3zM4 6v12c0 1.7 3.6 3 8 3s8-1.3 8-3V6M4 12c0 1.7 3.6 3 8 3s8-1.3 8-3"/>',
    doc: '<path d="M14 3H6a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9z"/><path d="M14 3v6h6M8 13h8M8 17h5"/>',
    shield: '<path d="M12 3l8 3v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6z"/>',
    services: '<path d="M4 6h16M4 12h16M4 18h10"/><circle cx="19" cy="18" r="2"/>',
    clock: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
    lan: '<rect x="8" y="2" width="8" height="6" rx="1"/><rect x="2" y="16" width="8" height="6" rx="1"/><rect x="14" y="16" width="8" height="6" rx="1"/><path d="M12 8v4M6 16v-2h12v2"/>',
    log: '<path d="M4 5h16M4 10h10M4 15h16M4 20h8"/>',
    top: '<path d="M4 20V10M10 20V4M16 20v-7M22 20H2"/>',
    show: '<rect x="3" y="4" width="18" height="12" rx="2"/><path d="M12 16v4M8 20h8"/>',
    star: '<path d="M12 3l2.8 5.7 6.2.9-4.5 4.4 1 6.2L12 17.3 6.5 20.2l1-6.2-4.5-4.4 6.2-.9z"/>',
    move: '<path d="M12 3v18M3 12h18M9 6l3-3 3 3M9 18l3 3 3-3M6 9l-3 3 3 3M18 9l3 3-3 3"/>',
    x: '<path d="M6 6l12 12M18 6L6 18"/>',
    size: '<path d="M14 4h6v6M10 20H4v-6M20 4l-7 7M4 20l7-7"/>',
    paint: '<circle cx="12" cy="12" r="9"/><circle cx="8" cy="10" r="1.2"/><circle cx="12" cy="7.5" r="1.2"/><circle cx="16" cy="10" r="1.2"/>',
    gear: '<circle cx="12" cy="12" r="3"/><path d="M12 2v3M12 19v3M2 12h3M19 12h3M4.9 4.9l2.1 2.1M17 17l2.1 2.1M4.9 19.1L7 17M17 7l2.1-2.1"/>',
    mic: '<rect x="9" y="3" width="6" height="11" rx="3"/><path d="M5 11a7 7 0 0 0 14 0M12 18v3"/>',
    play: '<path d="M8 5v14l11-7z"/>',
    pause: '<path d="M8 5v14M16 5v14"/>',
    next: '<path d="M6 6l9 6-9 6zM18 6v12"/>',
    prev: '<path d="M18 6l-9 6 9 6zM6 6v12"/>',
    plus: '<path d="M12 5v14M5 12h14"/>',
    search: '<circle cx="11" cy="11" r="7"/><path d="M20 20l-4-4"/>',
    up: '<path d="M6 15l6-6 6 6"/>', down: '<path d="M6 9l6 6 6-6"/>', left: '<path d="M15 6l-6 6 6 6"/>', right: '<path d="M9 6l6 6-6 6"/>',
  };
  const svg = (name, cls = "") => `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" class="${cls}">${ICON[name] || ""}</svg>`;

  /* ---------- palettes and look ---------- */
  const PALETTES = [
    { id: "arctic", name: "Arctic Cyan", a: "#00f5ff", rgb: "0,245,255", bg: "#030508", shape: "rings", desc: "Серебристо-циановый. Кольца вокруг сферы." },
    { id: "solar", name: "Solar Magma", a: "#ff7a1a", rgb: "255,122,26", bg: "#030406", shape: "dots", desc: "Огненно-янтарный. Точечный глобус." },
    { id: "emerald", name: "Emerald Matrix", a: "#10b981", rgb: "16,185,129", bg: "#030706", shape: "grid", desc: "Изумрудный. Сетка и линия сканирования." },
    { id: "crimson", name: "Crimson Sentinel", a: "#ff2a55", rgb: "255,42,85", bg: "#050304", shape: "shield", desc: "Рубиново-красный. Сегменты щита." },
    { id: "violet", name: "Violet Astrolabe", a: "#8b5cf6", rgb: "139,92,246", bg: "#05040a", shape: "orbits", desc: "Фиолетовый. Наклонные орбиты." },
  ];
  const palette = (id) => PALETTES.find((p) => p.id === id) || PALETTES[0];
  const LOOKS = [["glass", "Стекло"], ["solid", "Сплошная"], ["minimal", "Минимал"]];
  const DENSITY = [["cozy", "Просторно"], ["compact", "Компактно"]];

  /* ---------- preferences (per PC, in this browser) ---------- */
  const WIDGET_DEFS = []; // filled below
  const DEFAULT_ITEMS = [
    { id: "cpu", col: "l", size: "m" }, { id: "goals", col: "l", size: "s" }, { id: "tasks", col: "l", size: "m" },
    { id: "focus", col: "l", size: "s" }, { id: "weather", col: "l", size: "s" },
    { id: "tv", col: "r", size: "s" }, { id: "calendar", col: "r", size: "m" }, { id: "messengers", col: "r", size: "s" },
    { id: "brain", col: "r", size: "s" }, { id: "history", col: "r", size: "m" },
  ];
  const DEFAULT_PREFS = { palette: "arctic", look: "glass", density: "cozy", anim: true, radius: 16, fs: 14, skin: "orbit", core: "globe",
    layout: { mode: "center", items: DEFAULT_ITEMS, presetName: "Главная" } };
  const PRESETS = {
    "Полный": null,
    "Минимум": [{ id: "cpu", col: "l", size: "s" }, { id: "tasks", col: "l", size: "m" }, { id: "calendar", col: "r", size: "m" }, { id: "history", col: "r", size: "s" }],
    "Работа": [{ id: "tasks", col: "l", size: "m" }, { id: "focus", col: "l", size: "s" }, { id: "goals", col: "l", size: "s" }, { id: "calendar", col: "r", size: "m" }, { id: "docs", col: "r", size: "s" }, { id: "memory", col: "r", size: "s" }, { id: "history", col: "r", size: "m" }],
    "Игры": [{ id: "cpu", col: "l", size: "m" }, { id: "net", col: "l", size: "s" }, { id: "sound", col: "l", size: "s" }, { id: "tv", col: "r", size: "s" }, { id: "programs", col: "r", size: "m" }, { id: "battery", col: "r", size: "s" }],
    "Учёба": [{ id: "goals", col: "l", size: "m" }, { id: "memory", col: "l", size: "s" }, { id: "focus", col: "l", size: "s" }, { id: "tasks", col: "r", size: "m" }, { id: "calendar", col: "r", size: "s" }, { id: "history", col: "r", size: "s" }],
  };
  let PREFS = clone(DEFAULT_PREFS);
  function clone(x) { return JSON.parse(JSON.stringify(x)); }
  function loadPrefs() {
    try {
      const x = JSON.parse(localStorage.getItem("jv.ui") || "null");
      if (x && x.v === 3) PREFS = { ...clone(DEFAULT_PREFS), ...x, layout: { ...clone(DEFAULT_PREFS.layout), ...(x.layout || {}) } };
    } catch { /* private window: the defaults are fine */ }
    // a widget added in a newer version appears off, so the layout never breaks
    const have = new Set(PREFS.layout.items.map((i) => i.id));
    WIDGET_DEFS.forEach((w) => { if (!have.has(w.id)) PREFS.layout.items.push({ id: w.id, col: "r", size: w.size, on: false }); });
    PREFS.layout.items = PREFS.layout.items.filter((i) => WIDGET_DEFS.some((w) => w.id === i.id));
  }
  function savePrefs() { try { localStorage.setItem("jv.ui", JSON.stringify({ v: 3, ...PREFS })); } catch { /* ignore */ } }
  function applyLook() {
    const p = palette(PREFS.palette), root = document.documentElement, st = root.style;
    st.setProperty("--accent", p.a); st.setProperty("--accent-rgb", p.rgb); st.setProperty("--bg", p.bg);
    st.setProperty("--r", PREFS.radius + "px"); st.setProperty("--fs", PREFS.fs + "px");
    root.dataset.look = PREFS.look; root.dataset.density = PREFS.density; root.dataset.anim = PREFS.anim ? "on" : "off";
    const shape = PREFS.shape && PREFS.shape !== "auto" ? PREFS.shape : p.shape;     // the owner's figure, or the colour's own
    if (window.JarvisCore) { JarvisCore.setShape(shape, p.rgb); JarvisCore.setCore && JarvisCore.setCore(PREFS.core); }
  }

  /* ---------- live data ---------- */
  const STATE = { hud: null, v3: null, conn: null, state: null, shield: null, cal: null, macros: null, last: {}, hist: { cpu: [], ram: [], gpu: [], down: [], up: [] } };
  const pushHist = (k, v) => { if (v == null || Number.isNaN(Number(v))) return; const a = STATE.hist[k]; a.push(Number(v)); if (a.length > 50) a.shift(); };
  function sparkline(vals, color = "var(--accent)", max = 100) {
    if (!vals || vals.length < 2) return `<svg class="spark" viewBox="0 0 100 40" preserveAspectRatio="none"></svg>`;
    const top = Math.max(max, ...vals, 1), step = 100 / (vals.length - 1);
    const pts = vals.map((v, i) => `${(i * step).toFixed(1)} ${(36 - (v / top) * 32).toFixed(1)}`).join(" L");
    return `<svg class="spark" viewBox="0 0 100 40" preserveAspectRatio="none" aria-hidden="true"><path d="M0 40 L${pts} L100 40Z" fill="${color}" opacity=".12"/><path class="line" d="M${pts}" stroke="${color}"/></svg>`;
  }
  const bar = (p, cls = "") => `<div class="bar ${cls}"><i style="width:${clamp(Number(p) || 0, 0, 100)}%"></i></div>`;
  const kv = (k, v, cls = "") => `<div class="kv"><span>${esc(k)}</span><b class="${cls}">${v}</b></div>`;
  const empty = (t, sub = "") => `<div class="empty"><b>${esc(t)}</b>${esc(sub)}</div>`;
  /** A radial gauge: value 0–100, the number in the middle, a caption under it. */
  function gauge(v, label, sub = "", color = "var(--accent)") {
    const p = clamp(Number(v) || 0, 0, 100), r = 26, L = 2 * Math.PI * r, warn = p >= 90 ? "var(--bad)" : p >= 75 ? "var(--warn)" : color;
    return `<div class="gauge" role="img" aria-label="${esc(label)}: ${Math.round(p)}%"><svg viewBox="0 0 64 64" aria-hidden="true">
      <circle cx="32" cy="32" r="${r}" class="g-bg"/><circle cx="32" cy="32" r="${r}" class="g-ticks"/>
      <circle cx="32" cy="32" r="${r}" class="g-v" style="stroke:${warn};stroke-dasharray:${(L * p / 100).toFixed(1)} ${L.toFixed(1)}"/></svg>
      <b>${v == null ? "—" : Math.round(p) + "%"}</b><span>${esc(label)}</span>${sub ? `<small>${esc(sub)}</small>` : ""}</div>`;
  }
  /** Seven days of a goal as a row of cells: brighter = more steps that day. */
  function habitRow(g) {
    const per = g.per_day || 1, log = g.log || {}, days = [];
    for (let i = 6; i >= 0; i--) { const d = new Date(Date.now() - i * 864e5); days.push(Number(log[ymd(d)] || 0)); }
    return `<div class="habit" aria-label="7 дней: ${days.join(", ")}">${days.map((n) => `<i style="--h:${clamp(n / per, 0, 1).toFixed(2)}" class="${n ? "on" : ""}"></i>`).join("")}</div>`;
  }
  const toggle = (on, act, args, label) => `<button type="button" class="tgl ${on ? "on" : ""}" role="switch" aria-checked="${on}" aria-label="${esc(label)}" data-act="${act}" data-args='${esc(JSON.stringify(args))}'><i></i></button>`;

  /* ---------- widgets ---------- */
  const H = () => STATE.hud || {};
  const btn = (label, act, args = {}, cls = "") => `<button class="btn sm ${cls}" data-act="${act}" data-args='${esc(JSON.stringify(args))}'>${label}</button>`;
  const iconBtn = (name, act, args = {}, label = "") => `<button class="btn sm icon ghost" data-act="${act}" data-args='${esc(JSON.stringify(args))}' aria-label="${esc(label)}" title="${esc(label)}">${svg(name)}</button>`;

  function defineWidgets() {
    const W = (id, name, icon, size, render, extra = {}) => WIDGET_DEFS.push({ id, name, icon, size, render, ...extra });
    W("cpu", "Нагрузка ПК", "cpu", "m", () => {
      const h = H(), s = h.sys || {}, g = h.gpu;
      return `<div class="gauges">${gauge(s.cpu, "процессор", s.cores ? `${s.cores} ядер` : "")}${gauge(s.ram_pct, "память", s.ram_total ? `${num(s.ram_used, 1)}/${num(s.ram_total, 0)} ГБ` : "", "#a78bff")}${gauge(g ? g.util : null, "видео", g ? `${num(g.temp)}°C` : "нет данных", "#37e0a0")}</div>
        ${sparkline(STATE.hist.cpu)}`;
    });
    W("goals", "Цели", "goal", "s", () => {
      const goals = (H().goals || []).slice(0, 4);
      if (!goals.length) return empty("Целей пока нет", "Добавьте в разделе «Цели»");
      return goals.map((g) => {
        const today = Number((g.log || {})[ymd()] || 0), per = g.per_day || 1, p = clamp((today / per) * 100, 0, 100);
        return `<div class="goal-row"><button type="button" class="goal-tick ${p >= 100 ? "done" : ""}" data-act="goal_mark" data-args='${esc(JSON.stringify({ id: g.id }))}' aria-label="Шаг по цели: ${esc(g.title)}">${p >= 100 ? "✓" : "+1"}</button>
          <div class="grow"><div class="row"><span class="grow ellipsis">${esc(g.title)}</span><b class="mono small">${Math.round(p)}%</b></div>${habitRow(g)}</div></div>`;
      }).join("") + `<div class="sub" style="margin-top:2px">Матрица привычек: последние 7 дней</div>`;
    });
    W("tasks", "Дела", "task", "m", () => {
      const open = (S().tasks || []).filter((t) => !t.done).sort((a, b) => (a.due || "9").localeCompare(b.due || "9")).slice(0, 5);
      const list = open.length ? open.map((t) => `<label class="item" style="padding:7px 0;min-height:0"><input type="checkbox" class="check" data-act="task_done" data-args='${esc(JSON.stringify({ id: t.id }))}' aria-label="Сделано: ${esc(t.text)}"><span class="grow ellipsis">${esc(t.text)}</span>${t.due ? `<span class="faint small">${hm(t.due)}</span>` : ""}</label>`).join("") : empty("Дел нет", "Добавьте первое ниже");
      return `${list}<form class="add-line" data-form="task"><input name="text" type="text" placeholder="Новое дело" aria-label="Новое дело" maxlength="160"><button class="btn sm primary" type="submit">Добавить</button></form>`;
    });
    W("focus", "Фокус", "focus", "s", () => {
      const left = Math.max(0, (H().focus?.until || 0) - Date.now() / 1000);
      return `<div class="big" data-left="${H().focus?.until || 0}">${left > 0 ? dur(left) : "25:00"}</div>
        <div class="sub">${left > 0 ? "фокус-щит закрывает отвлечения" : "закрывает YouTube, TikTok, Steam"}</div>
        <div class="foot">${left > 0 ? btn("Остановить", "focus", { minutes: 0 }, "danger") : [25, 50].map((m) => btn(m + " мин", "focus", { minutes: m }, m === 25 ? "primary" : "")).join("")}</div>`;
    });
    W("weather", "Погода", "weather", "s", () => {
      const w = H().weather;
      if (!w || w.temp == null) return empty(w?.error || "Загружаю погоду…");
      return `<div class="row" style="gap:12px"><div class="big">${w.temp}°</div><div class="sub">${esc(w.city)}<br>${esc(w.text)}</div></div>
        <div class="sub">ветер ${w.wind} км/ч · влажность ${w.hum}%${w.rain != null ? ` · дождь ${w.rain}%` : ""}</div>`;
    });
    W("net", "Сеть", "net", "s", () => {
      const h = H(), n = h.net || {};
      return `<div class="row" style="align-items:flex-end;gap:12px"><div class="big">${h.ping ?? "—"}<small>мс</small></div><div class="sub">до 1.1.1.1</div></div>
        ${sparkline(STATE.hist.down, "var(--accent)", 1)}
        ${kv("Приём", rate(n.down || 0), "acc")}${kv("Отдача", rate(n.up || 0))}${kv("Wi-Fi", esc(h.wifi?.ssid || "—"))}`;
    });
    W("battery", "Батарея", "battery", "s", () => {
      const b = H().battery;
      if (!b) return empty("Батареи нет", "Это стационарный компьютер");
      return `<div class="big">${b.pct}<small>%</small></div>${bar(b.pct, b.pct <= 20 && !b.plugged ? "bad" : "")}
        <div class="sub">${b.plugged ? "заряжается от сети" : b.left ? `хватит на ${Math.round(b.left / 60)} мин` : "от батареи"}</div>`;
    });
    W("sound", "Звук", "sound", "s", () => {
      const a = H().audio;
      if (!a) return empty("Звук недоступен");
      return `<div class="row"><button class="btn sm icon ghost" data-act="mute" aria-label="${a.mute ? "Включить" : "Выключить"} звук">${svg(a.mute ? "sound" : "sound")}</button>
        <input class="range grow" type="range" min="0" max="100" value="${a.volume}" style="--v:${a.volume}%" data-range="volume" aria-label="Громкость"><b class="mono" style="min-width:42px;text-align:right">${a.mute ? "тихо" : a.volume + "%"}</b></div>
        <div class="sub ellipsis" title="${esc(a.speaker)}">${esc(a.speaker || "Динамики")}</div>`;
    });
    W("display", "Экран", "display", "s", () => {
      const h = H(), s = (h.screens || [])[0];
      if (h.brightness == null) return `${s ? kv("Экран", `${s.w}×${s.h} · ${s.hz} Гц`) : ""}<div class="sub">Яркость этого экрана не меняется программно.</div>`;
      return `${kv("Экран", s ? `${s.w}×${s.h}` : "—")}<div class="row"><input class="range grow" type="range" min="5" max="100" value="${h.brightness}" style="--v:${h.brightness}%" data-range="brightness" aria-label="Яркость"><b class="mono">${h.brightness}%</b></div>`;
    });
    W("programs", "Программы", "apps", "m", () => {
      const list = H().programs || [];
      if (!list.length) return empty("Список программ загружается…");
      const running = list.filter((p) => p.running).slice(0, 4), others = list.filter((p) => !p.running).slice(0, 3);
      const row = (p) => `<div class="prog">${p.icon ? `<img src="/api/hud/icon/${encodeURIComponent(p.icon)}" alt="" loading="lazy" onerror="this.style.visibility='hidden'">` : `<span class="pi">${svg("apps")}</span>`}<span class="grow ellipsis">${esc(p.name)}</span><span class="faint small">${p.running ? "открыта" : "открыть"}</span>${toggle(p.running, p.running ? "prog_close" : "open", { name: p.name }, (p.running ? "Закрыть " : "Открыть ") + p.name)}</div>`;
      return `<div class="sub">Запущено: ${running.length} из ${list.length}</div>${running.map(row).join("")}${others.map(row).join("")}`;
    });
    W("top", "Процессы", "top", "s", () => {
      const rows = (H().top || []).slice(0, 5);
      if (!rows.length) return empty("Загружаю…");
      return rows.map((p) => `<div class="kv"><span class="ellipsis">${esc(p.name)}</span><b class="faint small">${p.cpu}% · ${p.mem} МБ</b>${p.safe ? iconBtn("x", "kill", { pid: p.pid, name: p.name }, "Завершить " + p.name) : ""}</div>`).join("");
    });
    W("tv", "Телевизор", "tv", "s", () => {
      const t = H().tv || {}, on = t.online && t.power === "on";
      const b = (what, label) => `<button class="btn sm" data-act="tv" data-args='${esc(JSON.stringify({ what }))}'>${label}</button>`;
      return `<div class="row"><span class="status-pill ${on ? "on" : ""}" style="padding:4px 10px"><i></i>${on ? "включён" : t.online ? "ожидание" : "не отвечает"}</span><span class="grow"></span>${on ? btn("Выкл", "tv", { what: "off" }, "danger") : btn("Вкл", "tv", { what: "on" }, "primary")}</div>
        <div class="tv-grid">${b("down", "−")}${b("up", "+")}${b("ch_down", "кан−")}${b("ch_up", "кан+")}${b("mute", "без звука")}${b("home", "домой")}${b("back", "назад")}${b("youtube", "YouTube")}</div>`;
    });
    W("calendar", "Календарь", "cal", "m", () => {
      const ev = STATE.cal;
      if (!ev) return empty("Загружаю календарь…");
      if (!ev.count) return empty("Календарь не подключён", "Добавьте ссылку .ics в «Настройки → Календарь»");
      const list = (ev.events || []).slice(0, 6);
      return list.length ? list.map((e) => `<div class="kv"><span class="ellipsis">${esc(e.title || "Событие")}</span><b class="faint small">${e.all_day ? "весь день" : hm(e.start)}</b></div>`).join("") : empty("На сегодня событий нет");
    });
    W("messengers", "Связь", "msg", "s", () => {
      const c = STATE.conn || {}, r = STATE.remote || {};
      const tg = c.telegram?.connected ? '<span class="chip ok">вход есть</span>' : '<span class="chip bad">нужен вход</span>';
      const bot = r.running ? '<span class="chip ok">работает</span>' : r.auth_error ? '<span class="chip bad">токен не принят</span>' : r.has_token ? '<span class="chip warn">выключен</span>' : '<span class="chip">не настроен</span>';
      const waTxt = { connected: "подключён", qr: "ждёт QR-кода", starting: "запускается", off: "выключен" }[c.whatsapp?.state] || (c.whatsapp?.enabled ? "запускается" : "выключен");
      const wa = c.whatsapp?.state === "connected" ? '<span class="chip ok">подключён</span>' : c.whatsapp?.enabled ? `<span class="chip warn">${esc(waTxt)}</span>` : '<span class="chip">выключен</span>';
      return `${kv("Telegram (вы)", tg)}${kv("Telegram-бот", bot)}${kv("WhatsApp", wa)}${kv("Почта", `${(c.email || []).length} ящ.`)}
        <div class="foot"><a class="btn sm" href="#/settings/messengers">Настроить</a></div>`;
    });
    W("brain", "Мозг и движки", "brain", "s", () => {
      const h = H(), c = h.cloud || {}, svc = h.services || [];
      const ol = svc.find((s) => s.name === "Ollama")?.on;
      const dot = (on) => `<span class="dot-st ${on ? "on" : ""}"></span>`;
      return `${kv("Groq (речь и ответы)", c.groq ? "есть ключ" : "нет ключа")}${kv("Gemini (зрение)", c.gemini ? "есть ключ" : "нет ключа")}
        ${kv("Ollama (без интернета)", ol ? "работает" : "выключен")}${kv("Навыков", num(h.skills))}
        ${kv("Уроков выучено", num(h.learning?.lessons_learned ?? 0))}`;
    });
    W("history", "История", "history", "m", () => {
      const list = (S().history || []).slice().reverse().filter((x) => x.user).slice(0, 6);
      if (!list.length) return empty("Команд пока нет", "Скажите или напишите Джарвису");
      return list.map((h) => `<div class="hist-item" style="padding:8px 0"><div class="meta"><span>${esc((h.time || "").slice(11, 16))}</span></div><div class="q ellipsis">${esc(h.user)}</div><div class="a ellipsis">${esc(h.reply || "")}</div></div>`).join("");
    });
    W("memory", "Память", "memory", "s", () => {
      const l = H().learning || {};
      return `<div class="gauges two">${gauge(100 - (l.repeat_mistake_rate ?? 0), "без повторов", "ошибки не повторяет", "#37e0a0")}<div class="stat-col"><b class="big">${num(l.lessons_learned ?? 0)}</b><span class="sub">уроков из ошибок</span><b class="mono">${num(l.corrections_detected ?? 0)}</b><span class="sub">ошибок замечено</span></div></div>
        ${kv("Отношения", esc(H().stage?.stage || "—"))}`;
    });
    W("docs", "Документы", "doc", "s", () => {
      const d = H().index || {};
      const f = STATE.docResult || [];
      return `<div class="sub">${d.built ? `Файлов в индексе: ${num(d.files)}` : "Документы ещё не изучены"}</div>
        <form class="add-line" data-form="docs"><input name="q" type="search" placeholder="Что найти в документах?" aria-label="Поиск по документам"><button class="btn sm" type="submit">Найти</button></form>
        ${f.map((x) => `<div class="kv"><span class="ellipsis" title="${esc(x.path)}">${esc(x.file)}${x.page ? ` · стр. ${x.page}` : ""}</span></div><div class="sub">${esc(x.text)}</div>`).join("")}`;
    });
    W("shield", "Безопасность", "shield", "s", () => {
      const s = STATE.shield;
      if (!s) return empty("Проверяю порты…");
      const un = s.ports.unusual || [];
      return `${kv("Слушающих портов", s.ports.listening.length)}${kv("Внешних подключений", s.ports.remote.length)}
        ${kv("Необычных открытых", un.length ? `<span class="warn">${un.length}</span>` : "нет", "")}
        ${kv("VPN", s.vpn.on ? "включён" : "выключен")}<div class="foot">${btn("Проверить", "shield_check", {}, "")}</div>`;
    });
    W("services", "Службы", "services", "s", () => {
      const list = H().services || [];
      return list.length ? list.map((s) => `<div class="kv"><span>${esc(s.name)}</span><b class="${s.on ? "ok" : "faint"}">${s.on ? "работает" : "остановлена"}</b></div>`).join("") : empty("Загружаю…");
    });
    W("macros", "Быстрые команды", "apps", "s", () => {
      const list = (STATE.macros?.items || []).slice(0, 4);
      if (!list.length) return empty("Команд пока нет", "Создайте в разделе «Команды»");
      return list.map((m) => `<div class="kv"><span class="ellipsis">«${esc(m.phrase)}»</span>${btn("Запуск", "macro_run", { id: m.id }, "primary")}</div>`).join("");
    });
    W("show", "Презентация", "show", "s", () => {
      const s = H().show || {};
      if (!s.active) return `<div class="sub">Джарвис рассказывает о себе на весь экран и сам листает слайды. Голосом: «самопрезентация».</div><div class="foot">${btn("Самопрезентация", "show_start", { deck: "about", auto: true }, "primary")}${btn("Отчёт", "show_start", { deck: "report" })}</div>`;
      return `<div class="sub">${esc(s.deck_name || "")} · слайд ${s.i + 1} из ${s.total} · ${esc((s.lang || "").toUpperCase())}${s.auto ? " · читает сам" : ""}</div><div class="kv"><span class="ellipsis">${esc(s.slide?.title || "")}</span></div>
        <div class="foot">${btn("◀", "show_step", { d: -1 })}${btn("▶", "show_step", { d: 1 }, "primary")}${btn("Окно", "show_open", {})}${btn("Стоп", "show_stop", {}, "danger")}</div>`;
    });
    W("clock", "Часы", "clock", "s", () => {
      const n = new Date();
      return `<div class="big">${n.toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" })}</div><div class="sub">${n.toLocaleDateString("ru-RU", { weekday: "long", day: "numeric", month: "long" })}</div>`;
    });
    W("lan", "Устройства в сети", "lan", "s", () => {
      const list = H().lan || [];
      return list.length ? list.map((d) => `<div class="kv"><span>${esc(d.name)}</span><b class="faint small">${esc(d.ip)}</b></div>`).join("") : empty("Список устройств пуст");
    });
    W("logs", "Журнал работы", "log", "m", () => {
      const lines = (H().logs || []).slice(-8).reverse();
      return lines.length ? `<div class="code" style="white-space:pre-wrap;max-height:200px;overflow:auto">${esc(lines.join("\n"))}</div>` : empty("Журнал пуст");
    });
    WIDGET_DEFS.forEach((w) => { w.compact = false; });
  }
  const S = () => STATE.state || {};

  /* ---------- layout editing ---------- */
  const widgetDef = (id) => WIDGET_DEFS.find((w) => w.id === id);
  const EDIT = { on: false };
  const SIZES = ["s", "m", "l"];
  function layoutItems() { return PREFS.layout.items; }
  function itemOf(id) { return layoutItems().find((i) => i.id === id); }
  function visibleItems() { return layoutItems().filter((i) => i.on !== false); }

  function widgetShell(item) {
    const def = widgetDef(item.id);
    const style = item.style || PREFS.look === "minimal" ? "style-minimal" : "";
    const compact = item.compact ? "compact" : "";
    const tools = EDIT.on ? `<div class="tools" role="toolbar" aria-label="Настройка виджета">
        ${iconBtn("left", "wmove", { id: item.id, d: "left" }, "Перенести влево")}${iconBtn("up", "wmove", { id: item.id, d: "up" }, "Выше")}${iconBtn("down", "wmove", { id: item.id, d: "down" }, "Ниже")}${iconBtn("right", "wmove", { id: item.id, d: "right" }, "Перенести вправо")}
        ${iconBtn("size", "wsize", { id: item.id }, "Размер: " + (item.size || "s"))}${iconBtn("paint", "wstyle", { id: item.id }, "Вид виджета")}${iconBtn("x", "whide", { id: item.id }, "Скрыть")}</div>` : "";
    const look = { solid: "Solid", minimal: "Minimal" }[item.style] || "Glass";
    return `<article class="w ${item.size || def.size} ${style} ${compact}" data-w="${item.id}" ${EDIT.on ? 'draggable="true"' : ""} aria-label="${esc(def.name)}">
      <div class="w-h"><span class="ico">${svg(def.icon)}</span><span class="ttl ellipsis">${esc(def.name)}</span>${EDIT.on ? "" : `<button type="button" class="w-tag" data-act="wstyle" data-args='${esc(JSON.stringify({ id: item.id }))}' title="Сменить вид виджета">Style: ${look}</button>`}${tools}</div>
      <div class="w-b" data-body></div></article>`;
  }
  /* Five ways to set the widgets around the core. Each one is a whole look, not only a colour. */
  const SKINS = [
    ["orbit", "Орбита", "HUD-панели с уголками вокруг глобуса"],
    ["datav", "Командный центр", "Табло: цифры сверху, тонкие рамки, бегущая строка"],
    ["ring", "Кольцо", "Виджеты по кругу вокруг ядра, линии к центру"],
    ["glass", "Стекло", "Мягкие стеклянные карточки и свечение"],
    ["terminal", "Терминал", "Окна консоли, моноширинный шрифт, развёртка"],
  ];
  const skin = () => (SKINS.some(([k]) => k === PREFS.skin) ? PREFS.skin : "orbit");
  function kpiHtml() {
    const h = H(), s = h.sys || {}, g = h.gpu || {}, tasks = (S().tasks || []).filter((t) => !t.done).length;
    const k = (label, v, unit = "") => `<div class="kpi"><span>${label}</span><b>${v}<small>${unit}</small></b></div>`;
    return k("Процессор", num(s.cpu), "%") + k("Память", num(s.ram_pct), "%") + k("Видео", g.util != null ? num(g.util) : "—", g.util != null ? "%" : "")
      + k("Дела", tasks) + k("Цели", (h.goals || []).length) + k("Навыки", num(h.skills));
  }
  function layoutRing() {
    const dash = $("#dash.skin-ring"); if (!dash) return;
    const pods = $$(".w", dash), n = pods.length; if (!n) return;
    const W = dash.clientWidth, Hh = dash.clientHeight, cx = W / 2, cy = Hh / 2;
    const core = $("#coreWrap", dash), coreR = core ? core.clientWidth / 2 : W * 0.18;
    const podW = pods[0].offsetWidth || 240, rx = W / 2 - podW / 2 - 8, minX = coreR + podW / 2 + 24;
    const svgEl = $("#ringLinks"); let lines = "";
    // two bowed columns, left and right of the core: evenly spaced, never closer to the core than its edge
    const left = Math.ceil(n / 2), right = n - left;
    pods.forEach((p, i) => {
      const side = i < left ? -1 : 1, k = side < 0 ? i : i - left, cnt = side < 0 ? left : right;
      const y = Hh * (cnt === 1 ? 0.5 : 0.12 + 0.76 * (k / (cnt - 1)));
      const dy = (y - cy) / (Hh * 0.62);
      const x = cx + side * Math.max(minX, rx * Math.sqrt(Math.max(0, 1 - dy * dy)));
      p.style.left = `${x}px`; p.style.top = `${y}px`;
      const a = Math.atan2(y - cy, x - cx);
      lines += `<line x1="${cx + Math.cos(a) * coreR * 0.92}" y1="${cy + Math.sin(a) * coreR * 0.92}" x2="${x - side * podW / 2}" y2="${y}"/><circle cx="${x - side * podW / 2}" cy="${y}" r="3"/>`;
    });
    if (svgEl) { svgEl.setAttribute("viewBox", `0 0 ${W} ${Hh}`); svgEl.innerHTML = lines; }
  }
  addEventListener("resize", () => layoutRing());
  /* Home frame (as in the earlier HUD): top bar, core in the middle with widgets on both sides, telemetry and command dock below. */
  function telHtml() {
    const h = H(), s = h.sys || {}, g = h.gpu || {}, c = h.cloud || {};
    const chip = (k, v, warn) => `<span class="hx-chip${warn ? " warn" : ""}"><i>${k}</i><b>${v}</b></span>`;
    return chip("ПРОЦ", `${num(s.cpu)}%`, (s.cpu || 0) > 85)
      + chip("ПАМЯТЬ", `${num(s.ram_pct)}%`, (s.ram_pct || 0) > 85)
      + chip("ВИДЕО", g.util != null ? `${num(g.util)}% · ${num(g.temp)}°C` : "—", (g.temp || 0) > 85)
      + chip("ОБЛАКО", c.enabled === false ? "выкл" : c.error ? "ошибка" : "вкл", !!c.error);
  }
  function paintDock() {
    const t = $("#hxTel"); if (t) t.innerHTML = telHtml();
    const k = $("#kpis"); if (k) k.innerHTML = kpiHtml();
    const tk = $("#tickerIn");
    if (tk && !tk.dataset.on) {             // the running line of the command centre: the latest commands and the state
      tk.dataset.on = "1";
      const items = (S().history || []).slice(-8).reverse().map((h) => `▸ ${esc((h.time || "").slice(11, 16))} ${esc(h.user || "")}`);
      tk.innerHTML = `<span>${[telHtml(), ...items].join("<i></i>")}</span><span aria-hidden="true">${[telHtml(), ...items].join("<i></i>")}</span>`;
    }
  }
  function coreHtml() {
    return `<div class="core-wrap" id="coreWrap">
           <div class="core-disc"><canvas id="orb" role="img" aria-label="Ядро Джарвиса. Нажмите, чтобы говорить"></canvas>
             <div class="core-label"><b>ДЖАРВИС</b><span id="stateTxt">запуск</span></div></div>
           <div class="talk" id="talk" aria-live="polite"><div class="you" id="you"></div><div id="him">${esc(STATE.lastReply || "Скажите «Джарвис» или напишите команду внизу.")}</div></div>
           <div class="feedback" id="fb"><button type="button" data-act="feedback" data-args='{"rating":1}' aria-label="Ответ верный">👍</button><button type="button" data-act="feedback" data-args='{"rating":-1}' aria-label="Ответ неверный">👎</button><span id="fbMsg"></span></div>
         </div>`;
  }
  function renderDashboardShell() {
    const mode = PREFS.layout.mode;
    const center = mode === "center", sk = skin();
    const list = visibleItems();
    const l = list.filter((i) => i.col !== "r"), r = list.filter((i) => i.col === "r");
    let cols;
    if (mode === "robot" && window.Robot) cols = window.Robot.html();
    else if (center && sk === "ring") cols = `<svg class="ring-links" id="ringLinks" aria-hidden="true"></svg>${coreHtml()}${list.slice(0, 8).map(widgetShell).join("")}`;
    else if (center) cols = `<div class="col-w" id="colL" data-col="l">${l.map(widgetShell).join("")}</div>${coreHtml()}<div class="col-w" id="colR" data-col="r">${r.map(widgetShell).join("")}</div>`;
    else if (mode === "focus") cols = coreHtml();          // only the core, large, in the middle
    else cols = `<div class="col-w" id="colL" data-col="l" style="grid-column:1/-1">${list.map(widgetShell).join("")}</div>`;
    const hudLike = center || mode === "robot" || mode === "focus";
    const modes = [["center", "Виджеты"], ["robot", "Робот"], ["grid", "Сетка"]];
    const toolbar = `<div class="dash-toolbar">
        ${hudLike ? `<div class="hud-title"><b>JARVIS PRIME OS <span>v3.3</span></b><small>Windows 11 · голосовой ассистент</small></div>` : ""}
        <span class="spacer"></span>
        ${center ? `<div class="seg skins" role="group" aria-label="Вид виджетов">${SKINS.map(([k, n, d]) => `<button type="button" data-act="skin" data-args='{"k":"${k}"}' aria-pressed="${sk === k}" title="${esc(d)}">${n}</button>`).join("")}</div>` : ""}
        <div class="seg" role="group" aria-label="Режим главной">${modes.map(([k, n]) => `<button type="button" data-act="mode" data-args='{"m":"${k}"}' aria-pressed="${mode === k}">${n}</button>`).join("")}</div>
        <button class="btn sm primary" data-act="studio" data-args='{"tab":"look"}'>${svg("paint")} Персонализация</button>
        ${mode === "robot" || mode === "focus" ? "" : `<button class="btn sm ${EDIT.on ? "primary" : ""}" data-act="edit" aria-pressed="${EDIT.on}" title="Переставлять виджеты прямо на главной">${svg("move")} ${EDIT.on ? "Готово" : "Переставить"}</button>`}
        ${center && EDIT.on ? `<button class="btn sm ghost" data-act="resetlayout" title="Сбросить порядок виджетов">Сброс</button>` : ""}
      </div>`;
    const kpi = center && sk === "datav" ? `<div class="kpis" id="kpis">${kpiHtml()}</div>` : "";
    const dock = hudLike ? `<footer class="hx-dock" aria-label="Телеметрия и команды">
        <div class="hx-tel" id="hxTel"></div>
        <form class="form-row hx-cmd" id="askForm" role="search"><div class="field grow"><input id="askIn" type="text" placeholder="Запрос к Джарвису или команда…" aria-label="Команда для Джарвиса" autocomplete="off"></div><button class="btn icon" type="button" id="btnMic" aria-label="Говорить">${svg("mic")}</button><button class="btn primary" type="submit">Отправить</button></form>
        <button class="btn stage-btn" data-act="show_open">${svg("show")} STAGE / ПРЕЗЕНТАЦИЯ</button>
      </footer>` : "";
    const ticker = center && sk === "datav" ? `<div class="ticker" aria-hidden="true"><div id="tickerIn"></div></div>` : "";
    if (mode !== "robot" && window.Robot) window.Robot.unmount();
    document.body.classList.toggle("home-hud", hudLike);
    $("#view").innerHTML = `<div class="hud skin-${center ? sk : mode} ${EDIT.on ? "edit" : ""}">${toolbar}${kpi}<div class="dash mode-${mode} ${center ? "skin-" + sk : ""}" id="dash">${cols}</div>${dock}${ticker}</div>`;
    $("#view").dataset.page = "home";
    if (center || mode === "focus") mountCore();
    if (mode === "robot" && window.Robot) window.Robot.mount();
    bindWidgetDnd();
    paintWidgets(true);
    requestAnimationFrame(layoutRing);
  }
  /* ---------- Персонализация: like a phone's widget gallery. Every change shows at once. ---------- */
  const STUDIO = { filter: "all" };
  const LAYOUTS = [
    ["center", "orbit", "Орбита", "HUD-панели с уголками вокруг ядра"], ["center", "datav", "Командный центр", "Табло цифр, тонкие рамки, бегущая строка"],
    ["center", "ring", "Кольцо", "Виджеты по дуге вокруг ядра"], ["center", "glass", "Стекло", "Мягкие стеклянные карточки"],
    ["center", "terminal", "Терминал", "Окна консоли и развёртка"], ["robot", "", "Робот", "Робот с эмоциями и вашим настроением"],
    ["grid", "", "Сетка", "Только виджеты, плотной сеткой"], ["focus", "", "Только ядро", "Большое ядро без виджетов"],
  ];
  const SHAPES = [["auto", "Как у цвета"], ["rings", "Кольца"], ["dots", "Точки"], ["grid", "Сетка"], ["shield", "Щит"], ["orbits", "Орбиты"], ["none", "Без фигуры"]];
  const WGROUPS = { "Компьютер": ["cpu", "programs", "top", "net", "battery", "sound", "display", "services", "lan", "logs"],
    "Дела и время": ["tasks", "goals", "focus", "calendar", "clock", "macros", "history"], "Связь и дом": ["messengers", "tv", "weather"],
    "Джарвис": ["brain", "memory", "docs", "shield", "show"] };
  function thumb(mode, k) {
    const panel = (n) => Array.from({ length: n }, () => "<i></i>").join("");
    if (mode === "robot") return `<div class="th th-robot"><b></b></div>`;
    if (mode === "focus") return `<div class="th th-focus"><b></b></div>`;
    if (mode === "grid") return `<div class="th th-grid">${panel(6)}</div>`;
    if (k === "ring") return `<div class="th th-ring"><b></b>${panel(6)}</div>`;
    return `<div class="th th-cols th-${k}"><span>${panel(3)}</span><b></b><span>${panel(3)}</span></div>`;
  }
  function renderStudio(tab = "look") {
    STUDIO.tab = tab;
    document.body.classList.add("home-hud");
    if (window.Robot) window.Robot.unmount();
    const mode = PREFS.layout.mode, sk = skin(), shape = PREFS.shape || "auto";
    const tabs = [["look", "Вид главной"], ["core", "Ядро и цвет"], ["widgets", "Виджеты"]];
    let main = "";
    if (tab === "look") {
      main = `<p class="sub">Выберите, как будет выглядеть главная. Можно менять в любой момент.</p><div class="layouts">${LAYOUTS.map(([m, k, n, d]) => {
        const on = mode === m && (!k || sk === k);
        return `<button type="button" class="lay-card" data-act="st_layout" data-args='${esc(JSON.stringify({ mode: m, skin: k }))}' aria-pressed="${on}">${thumb(m, k)}<b>${esc(n)}</b><span>${esc(d)}</span></button>`;
      }).join("")}</div>`;
    } else if (tab === "core") {
      main = `<h3>Ядро</h3><div class="opts">${[["globe", "Точечный глобус", "Земля из светящихся точек"], ["sphere", "Стеклянная сфера", "Сфера с волной голоса"]].map(([k, n, d]) => `<button type="button" class="opt-card" data-act="st_core" data-args='{"core":"${k}"}' aria-pressed="${(PREFS.core || "globe") === k}"><b>${n}</b><span>${d}</span></button>`).join("")}</div>
        <h3>Фигура вокруг ядра</h3><div class="chips">${SHAPES.map(([k, n]) => `<button type="button" class="chip-btn" data-act="st_shape" data-args='{"shape":"${k}"}' aria-pressed="${shape === k}">${n}</button>`).join("")}</div>
        <h3>Цвет</h3><div class="swatch-row">${PALETTES.map((p) => `<button type="button" class="sw" data-act="st_palette" data-args='{"id":"${p.id}"}' aria-pressed="${PREFS.palette === p.id}" style="--c:${p.a}"><i></i><span>${esc(p.name)}</span></button>`).join("")}</div>
        <p class="sub">Ядро слева показывает выбор сразу. Тонкая настройка (стиль карточек, плотность, анимация) — в разделе «Внешний вид».</p>`;
    } else {
      const items = layoutItems(), f = STUDIO.filter;
      const card = (id) => {
        const def = widgetDef(id), it = itemOf(id); if (!def || !it) return "";
        const on = it.on !== false;
        if ((f === "on" && !on) || (f === "off" && on)) return "";
        const seg = (act, key, opts) => `<div class="mini-seg">${opts.map(([v, n]) => `<button type="button" data-act="${act}" data-args='${esc(JSON.stringify({ id, [key]: v }))}' aria-pressed="${(it[key] || (key === "size" ? def.size : "l")) === v}">${n}</button>`).join("")}</div>`;
        return `<div class="wcard ${on ? "on" : ""}"><div class="wprev">${widgetShell({ ...it, style: it.style })}</div>
          <div class="wctl"><label class="row grow"><b class="ellipsis">${esc(def.name)}</b></label>${toggle(on, "st_on", { id }, (on ? "Убрать с главной: " : "Показать на главной: ") + def.name)}</div>
          ${on ? `<div class="wctl small">${seg("st_size", "size", [["s", "S"], ["m", "M"], ["l", "L"]])}${seg("st_side", "col", [["l", "Слева"], ["r", "Справа"]])}</div>` : ""}</div>`;
      };
      const shown = items.filter((i) => i.on !== false).length;
      main = `<div class="row wrap" style="gap:8px"><div class="seg">${[["all", "Все"], ["on", `На главной · ${shown}`], ["off", "Скрытые"]].map(([k, n]) => `<button type="button" data-act="st_filter" data-args='{"f":"${k}"}' aria-pressed="${f === k}">${n}</button>`).join("")}</div><span class="sub">Включите переключателем — виджет сразу появится на главной.</span></div>
        ${Object.entries(WGROUPS).map(([g, ids]) => { const cards = ids.map(card).join(""); return cards ? `<h3>${g}</h3><div class="gallery">${cards}</div>` : ""; }).join("")}`;
    }
    $("#view").innerHTML = `<div class="studio" id="studio">
        <header class="studio-head"><div><h2>Персонализация</h2><p class="sub">Всё меняется сразу. Нажмите «Готово», чтобы вернуться на главную.</p></div>
          <div class="seg" role="tablist">${tabs.map(([k, n]) => `<button type="button" role="tab" data-act="st_tab" data-args='{"tab":"${k}"}' aria-pressed="${tab === k}">${n}</button>`).join("")}</div>
          <button class="btn primary" data-act="studio_done">Готово</button></header>
        <div class="studio-body"><aside class="studio-preview"><div class="core-disc"><canvas id="orb" role="img" aria-label="Так будет выглядеть ядро"></canvas>
            <div class="core-label"><b>ДЖАРВИС</b><span id="stateTxt">предпросмотр</span></div></div>
            <div class="sub" style="text-align:center">${esc((LAYOUTS.find(([m, k]) => m === mode && (!k || k === sk)) || [, , "—"])[2])} · ${esc(palette(PREFS.palette).name)}</div></aside>
          <section class="studio-main">${main}</section></div></div>`;
    $("#view").dataset.page = "home";
    mountCore();
    paintWidgets(true);
  }
  function paintWidgets(force) {
    paintDock();
    $$("#dash .w[data-w], #studio .w[data-w]").forEach((el) => {
      const item = itemOf(el.dataset.w), def = widgetDef(el.dataset.w);
      if (!item || !def) return;
      const body = el.querySelector("[data-body]");
      let html = "";
      try { html = def.render(item); } catch (e) { html = `<div class="sub bad">Нет данных: ${esc(e.message)}</div>`; }
      if (!force && body.dataset.h === html) return;
      if (!force && body.contains(document.activeElement) && /INPUT|TEXTAREA|SELECT/.test(document.activeElement.tagName)) return;
      body.dataset.h = html;
      body.innerHTML = html;
    });
  }
  function bindWidgetDnd() {
    const dash = $("#dash"); if (!dash) return;
    let drag = null;
    dash.querySelectorAll(".w[draggable]").forEach((el) => {
      el.addEventListener("dragstart", (e) => { drag = el.dataset.w; el.classList.add("drag"); e.dataTransfer.effectAllowed = "move"; e.dataTransfer.setData("text/plain", drag); });
      el.addEventListener("dragend", () => { el.classList.remove("drag"); $$(".over", dash).forEach((x) => x.classList.remove("over")); drag = null; });
      el.addEventListener("dragover", (e) => { if (!drag || drag === el.dataset.w) return; e.preventDefault(); el.classList.add("over"); });
      el.addEventListener("dragleave", () => el.classList.remove("over"));
      el.addEventListener("drop", (e) => {
        e.preventDefault(); el.classList.remove("over");
        if (!drag || drag === el.dataset.w) return;
        moveBefore(drag, el.dataset.w, el.parentElement.dataset.col || "l");
      });
    });
    dash.querySelectorAll(".col-w").forEach((col) => {
      col.addEventListener("dragover", (e) => { if (drag && !col.querySelector(".w")) e.preventDefault(); });
      col.addEventListener("drop", (e) => { if (!drag) return; e.preventDefault(); moveToCol(drag, col.dataset.col || "l"); });
    });
  }
  function moveBefore(id, beforeId, col) {
    const items = layoutItems(), from = items.findIndex((i) => i.id === id);
    const [it] = items.splice(from, 1);
    it.col = col;
    const to = items.findIndex((i) => i.id === beforeId);
    items.splice(to < 0 ? items.length : to, 0, it);
    savePrefs(); renderDashboardShell();
  }
  function moveToCol(id, col) { const it = itemOf(id); if (it) { it.col = col; savePrefs(); renderDashboardShell(); } }

  /* ---------- core (mount + state) ---------- */
  function mountCore() {
    const c = $("#orb"); if (!c || !window.JarvisCore) return;
    JarvisCore.mount(c);
    applyLook();
    coreState();
  }
  function coreState() {
    if (!window.JarvisCore) return;
    const h = H();
    JarvisCore.set({ sys: h.sys || null, gpu: h.gpu || null, cloud: h.cloud || {}, lite: !!h.lite, game: !!h.game?.on });
    const txt = { starting: "запуск", listening: "жду «Джарвис»", recording: "слушаю", thinking: "думаю", speaking: "говорю", taping: "идёт запись", game: "игровой режим" };
    const st = $("#stateTxt"); if (st) st.textContent = (h.game?.on && STATUS === "listening") ? txt.game : txt[STATUS] || txt.listening;
    const mic = $("#btnMic"); if (mic) mic.setAttribute("aria-pressed", String(STATUS === "recording"));
  }
  let STATUS = "starting";
  function setStatus(s) { if (!s) return; STATUS = s; JarvisCore && JarvisCore.set({ status: s }); if (window.Robot) Robot.setStatus(s); coreState(); pillLink(); }
  function pillLink() {
    const c = STATE.hud?.cloud || {};
    const cp = $("#pillCloud"); if (cp) { cp.className = "status-pill " + (c.enabled === false ? "" : c.error ? "bad" : "on"); cp.querySelector("span").textContent = c.error ? "Облако: ошибка" : c.enabled === false ? "Без интернета" : "Облако подключено"; }
    const lp = $("#pillLink"); if (lp) { const ok = !!STATE.hud; lp.className = "status-pill " + (ok ? "on" : "bad"); lp.querySelector("span").textContent = ok ? "Джарвис на связи" : "нет связи"; }
  }

  /* ---------- polling and live events ---------- */
  async function pollHud() {
    if (document.hidden) return;
    try {
      const d = await api("/api/hud");
      STATE.hud = d; STATE.stage = d.stage;
      if (d.show && (d.show.active || SL.st?.active)) applyShow(d.show);   // started by voice or from Telegram: the slides appear
      pushHist("cpu", d.sys?.cpu); pushHist("down", d.net?.down ? d.net.down / 1048576 : 0);
      if (d.gpu) pushHist("gpu", d.gpu.util);
      coreState(); pillLink();
      if (location.hash === "" || location.hash === "#/") paintWidgets(false);
      if (STATE.live && STATE.live !== "home" && window.PAGES?.[STATE.live]?.onData) PAGES[STATE.live].onData(STATE.hud);
      if (d.first_run && !STATE.firstShown) { STATE.firstShown = true; openOnboarding(); }
    } catch { pillLink(); }
  }
  async function pollSlow() {
    if (document.hidden) return;
    const jobs = await Promise.allSettled([api("/api/v3"), api("/api/connections"), api("/api/remote"), api("/api/state"), api("/api/shield"), api("/api/calendar?days=1"), api("/api/macros")]);
    const [v3, conn, remote, state, shield, cal, macros] = jobs.map((j) => (j.status === "fulfilled" ? j.value : null));
    if (v3) STATE.v3 = v3; if (conn) STATE.conn = conn; if (remote) STATE.remote = remote;
    if (state) STATE.state = state; if (shield) STATE.shield = shield; if (cal) STATE.cal = cal; if (macros) STATE.macros = macros;
    if (location.hash === "" || location.hash === "#/") paintWidgets(false);
  }
  function connectWs() {
    let ws;
    try { ws = new WebSocket(`ws://${location.host}/ws`); } catch { return; }
    ws.onmessage = (e) => {
      let ev; try { ev = JSON.parse(e.data); } catch { return; }
      if (ev.type === "level") { STATE.micLevel = ev.v; JarvisCore && JarvisCore.set({ level: Math.min(1, ev.v / 1400) }); if (window.Robot) Robot.setLevel(Math.min(1, ev.v / 1400)); if (ev.s && ev.s !== STATUS) setStatus(ev.s); }
      else if (ev.type === "status") setStatus(ev.state);
      else if (ev.type === "message") { addExchange(ev); }
      else if (ev.type === "heard" && !ev.ok) { const y = $("#you"); if (y) y.textContent = "Не разобрал: " + ev.text; }
      else if (ev.type === "data" || ev.type === "settings" || ev.type === "v3" || ev.type === "remote" || ev.type === "connections") { pollSlow(); pollHud(); if (STATE.live && window.PAGES?.[STATE.live]?.onData) PAGES[STATE.live].onData(STATE.hud, true); }
      else if (ev.type === "enroll") toast(ev.state === "on" ? `Запоминаю голос: ${ev.seconds} из ${ev.need} с` : ev.ok ? "Голос запомнен" : "Мало речи, попробуйте ещё раз");
      else if (ev.type === "record") toast(ev.state === "on" ? "Идёт запись. Скажите «стоп»" : "Запись сохранена");
      else if (ev.type === "wizard") { openAnalysis && openAnalysis(); }
      else if (ev.type === "open") { location.hash = ev.panel === "history" ? "#/commands" : "#/settings"; }
      else if (ev.type === "reload") location.reload();
      else if (ev.type === "show") syncShow();
    };
    ws.onclose = () => { setStatus("starting"); setTimeout(connectWs, 2000); };
  }
  function addExchange(ev) {
    if (ev.role === "user") { const y = $("#you"); if (y) y.textContent = "Вы: " + ev.text; }
    else { STATE.lastReply = ev.text; const h = $("#him"); if (h) h.textContent = ev.text; if (window.Robot) window.Robot.onReply(ev.text); }
    if (STATE.live === "commands" && window.PAGES?.commands?.onData) PAGES.commands.onData(null, true);
    pollSlow();
  }

  /* ---------- conversation on the home screen ---------- */
  async function sendText(text) {
    if (!text) return;
    const y = $("#you"); if (y) y.textContent = "Вы: " + text;
    try {
      const r = await api("/api/command", "POST", { text, speak: false });
      const h = $("#him"); if (h && r.reply) h.textContent = r.reply;
    } catch (e) { toast("Не получилось: " + e.message); }
    pollHud();
  }

  /* ---------- actions (buttons inside widgets and pages) ---------- */
  const ACT = {
    async goal_mark({ id }) { await api("/api/hud/action", "POST", { kind: "goal_mark", id }); pollHud(); },
    async task_done({ id }) { await api(`/api/tasks/${id}`, "PATCH", { done: true }); toast("Отмечено выполненным"); pollSlow(); },
    async focus({ minutes }) { await api("/api/hud/action", "POST", { kind: "focus", minutes }); pollHud(); toast(minutes ? `Фокус на ${minutes} мин` : "Фокус остановлен"); },
    async mute() { await hudAct("mute", {}); pollHud(); },
    async volume(args) { await hudAct("volume", { level: args.level }); },
    async brightness(args) { await hudAct("brightness", { level: args.level }); },
    async open({ name }) { await hudAct("open", { name }); toast("Открываю " + name); setTimeout(pollHud, 1500); },
    async close({ name }) { await hudAct("close", { name }); toast("Закрываю " + name); setTimeout(pollHud, 1500); },
    async prog_close({ name }) {
      if (!(await ask({ title: `Закрыть ${name}?`, text: "Несохранённая работа в этой программе может пропасть.", yes: "Закрыть", danger: true }))) { paintWidgets(true); return; }
      await ACT.close({ name });
    },
    async kill({ pid, name }) {
      const ok = await ask({ title: `Завершить ${name}?`, text: "Несохранённая работа в этой программе пропадёт.", yes: "Завершить", danger: true });
      if (ok) { await hudAct("kill", { pid, name }); pollHud(); }
    },
    async tv({ what }) { if (what === "on" || what === "off") toast(what === "on" ? "Включаю телевизор…" : "Выключаю телевизор…"); await hudAct("tv", { what }); setTimeout(pollHud, 1500); },
    async shield_check() { try { STATE.shield = await api("/api/shield"); paintWidgets(false); toast("Проверил порты"); } catch (e) { toast(e.message); } },
    async macro_run({ id }) { await api(`/api/macros/${id}/run`, "POST"); toast("Запускаю"); },
    async feedback({ rating }) {
      try { const r = await api("/api/feedback", "POST", { rating }); const m = $("#fbMsg"); if (m) { m.textContent = r.message || ""; setTimeout(() => { if (m) m.textContent = ""; }, 2500); } }
      catch (e) { toast(e.message); }
    },
    async show_start({ deck = "about", auto = false, lang = "" } = {}) { await showOp("start", { deck, lang: lang || SL.st?.lang || "ru", auto }); },
    async show_step({ d }) { await showOp(d > 0 ? "next" : "prev"); },
    async show_stop() { await showOp("stop"); toast("Презентация закончена"); },
    show_open() { openStage(); },
    resetlayout() {
      const extra = WIDGET_DEFS.filter((w) => !DEFAULT_ITEMS.some((d) => d.id === w.id)).map((w) => ({ id: w.id, col: "r", size: w.size, on: false }));
      PREFS.layout.items = clone(DEFAULT_ITEMS).concat(extra);
      savePrefs(); renderDashboardShell(); toast("Порядок виджетов сброшен");
    },
    async wmove({ id, d }) { moveWidget(id, d); },
    wsize({ id }) { const it = itemOf(id); const i = SIZES.indexOf(it.size || "s"); it.size = SIZES[(i + 1) % 3]; savePrefs(); renderDashboardShell(); },
    wstyle({ id }) { const it = itemOf(id); const order = [undefined, "solid", "minimal"]; it.style = order[(order.indexOf(it.style) + 1) % 3]; savePrefs(); renderDashboardShell(); },
    whide({ id }) { itemOf(id).on = false; savePrefs(); renderDashboardShell(); toast("Скрыл. Вернуть: «Персонализация» → «Виджеты»"); },
    edit() { EDIT.on = !EDIT.on; renderDashboardShell(); },
    mode({ m }) { PREFS.layout.mode = m; savePrefs(); renderDashboardShell(); },
    skin({ k }) { PREFS.skin = k; if (PREFS.layout.mode !== "center") PREFS.layout.mode = "center"; savePrefs(); renderDashboardShell(); },
    addwidget() { renderStudio("widgets"); },
    studio({ tab = "look" } = {}) { EDIT.on = false; renderStudio(tab); },
    studio_done() { renderDashboardShell(); },
    st_tab({ tab }) { renderStudio(tab); },
    st_layout({ mode, skin: k }) { PREFS.layout.mode = mode; if (k) PREFS.skin = k; savePrefs(); renderStudio("look"); },
    st_core({ core }) { PREFS.core = core; savePrefs(); applyLook(); renderStudio("core"); },
    st_shape({ shape }) { PREFS.shape = shape; savePrefs(); applyLook(); renderStudio("core"); },
    st_palette({ id }) { PREFS.palette = id; savePrefs(); applyLook(); renderStudio("core"); },
    st_filter({ f }) { STUDIO.filter = f; renderStudio("widgets"); },
    st_on({ id }) { const it = itemOf(id); if (!it) return; it.on = it.on === false; if (it.on) it.col = it.col || "r"; savePrefs(); renderStudio("widgets"); },
    st_size({ id, size }) { const it = itemOf(id); if (it) { it.size = size; savePrefs(); renderStudio("widgets"); } },
    st_side({ id, col }) { const it = itemOf(id); if (it) { it.col = col; savePrefs(); renderStudio("widgets"); } },
  };
  async function hudAct(kind, body) {
    try {
      const r = await api("/api/hud/action", "POST", { kind, ...body });
      if (r.reply) toast(r.reply);
      return r;
    } catch (e) { toast(e.message); return null; }
  }
  function moveWidget(id, d) {
    const items = layoutItems(), idx = items.findIndex((i) => i.id === id), it = items[idx];
    if (d === "up" || d === "down") {
      const step = d === "up" ? -1 : 1;
      let j = idx + step; while (j >= 0 && j < items.length && items[j].col !== it.col) j += step;
      if (j >= 0 && j < items.length) { items.splice(idx, 1); items.splice(j, 0, it); }
    } else {
      it.col = d === "left" ? "l" : "r";
    }
    savePrefs(); renderDashboardShell();
  }


  /* ---------- widgets: range inputs and forms ---------- */
  document.addEventListener("input", (e) => {
    const t = e.target;
    if (t.matches("[data-range]")) { t.style.setProperty("--v", t.value + "%"); }
  });
  document.addEventListener("change", async (e) => {
    const t = e.target;
    if (t.matches("[data-range]")) {
      const kind = t.dataset.range, v = Number(t.value);
      await hudAct(kind === "volume" ? "volume" : "brightness", { level: v });
      pollHud();
    }
    if (t.matches("input.check[data-act]")) {
      const args = JSON.parse(t.dataset.args || "{}");
      try { await ACT.task_done(args); } catch (err) { toast(err.message); }
    }
  });
  document.addEventListener("submit", async (e) => {
    const f = e.target.closest("form[data-form]"); if (!f) {
      if (e.target.id === "askForm") { e.preventDefault(); const v = $("#askIn").value.trim(); if (v) { $("#askIn").value = ""; sendText(v); } }
      return;
    }
    e.preventDefault();
    const fd = Object.fromEntries(new FormData(f));
    try {
      if (f.dataset.form === "task") {
        if (!fd.text?.trim()) return;
        await api("/api/tasks", "POST", { text: fd.text.trim() });
        f.reset(); toast("Дело добавлено"); pollSlow();
      } else if (f.dataset.form === "docs") {
        const r = await api("/api/hud/action", "POST", { kind: "find", query: fd.q || "" });
        STATE.docResult = (r.items || []).map((x) => ({ file: x.name, path: x.path, text: x.dir || "", page: 0 }));
        paintWidgets(true);
      }
    } catch (err) { toast(err.message); }
  });
  document.addEventListener("click", async (e) => {
    const b = e.target.closest("[data-act]");
    if (!b || b.matches("input")) return;
    const name = b.dataset.act, args = JSON.parse(b.dataset.args || "{}");
    if (!ACT[name]) return;
    e.preventDefault();
    b.disabled = true;
    try { await ACT[name](args, b); }
    catch (err) { toast(err.message || "Не получилось"); }
    finally { b.disabled = false; }
  });
  $("#btnMic") && $("#btnMic").addEventListener("click", () => api("/api/listen", "POST").catch(() => {}));

  /* ---------- router and header ---------- */
  function setHeader(title, sub = "", actions = "") {
    $("#pgTitle").textContent = title; $("#pgSub").textContent = sub; $("#pgActions").innerHTML = actions;
    document.title = title + " · Джарвис";
  }
  function route() {
    const parts = (location.hash || "#/").replace(/^#\/?/, "").split("/");
    const page = parts[0] || "home", sub = parts[1] || "";
    $$(".nav a[data-page]").forEach((a) => { if (a.dataset.page === page) a.setAttribute("aria-current", "page"); else a.removeAttribute("aria-current"); });
    STATE.live = page;
    const view = $("#view");
    if (page === "home" || !window.PAGES || !PAGES[page]) {
      STATE.live = "home";
      setHeader("Главная", "Ядро и ваши виджеты. Вид меняется кнопкой «Персонализация».", "");
      view.innerHTML = ""; renderDashboardShell(); return;
    }
    const p = PAGES[page];
    document.body.classList.remove("home-hud");
    if (window.Robot) window.Robot.unmount();
    view.innerHTML = "";
    setHeader(p.title, p.sub || "", "");
    try { p.render(view, sub); } catch (err) { view.innerHTML = `<div class="callout bad"><div><b>Не открылся раздел</b>${esc(err.message)}</div></div>`; }
    view.scrollTop = 0;
  }
  window.addEventListener("hashchange", route);

  /* ---------- command search (Ctrl+K) ---------- */
  const CMDS = [
    ...[["home", "Главная"], ["tasks", "Дела"], ["goals", "Цели"], ["commands", "Команды"], ["memory", "Память"], ["show", "Презентация"], ["settings", "Настройки"], ["appearance", "Внешний вид"], ["help", "Инструкции"]].map(([p, n]) => ({ label: "Открыть: " + n, go: () => (location.hash = p === "home" ? "#/" : "#/" + p) })),
    { label: "Телевизор: включить", go: () => ACT.tv({ what: "on" }) },
    { label: "Телевизор: выключить", go: () => ACT.tv({ what: "off" }) },
    { label: "Включить фокус на 25 минут", go: () => ACT.focus({ minutes: 25 }) },
    { label: "Самопрезентация с голосом", go: () => ACT.show_start({ deck: "about", auto: true }) },
    { label: "Отчёт за месяц на весь экран", go: () => ACT.show_start({ deck: "report" }) },
    { label: "Проанализировать ноутбук", go: () => openAnalysis && openAnalysis() },
    { label: "Переставить виджеты на главной", go: () => { location.hash = "#/"; setTimeout(() => ACT.edit(), 50); } },
    { label: "Персонализация: вид главной, ядро, цвет", go: () => { location.hash = "#/"; setTimeout(() => renderStudio("look"), 60); } },
    { label: "Добавить или убрать виджеты", go: () => { location.hash = "#/"; setTimeout(() => renderStudio("widgets"), 60); } },
    { label: "Настроить голос", go: () => (location.hash = "#/settings/voice") },
    { label: "Подключить WhatsApp / Telegram / почту", go: () => (location.hash = "#/settings/messengers") },
  ];
  function openCmdk() {
    const box = $("#cmdk"), inp = $("#cmdkIn");
    box.hidden = false; inp.value = ""; renderHits(""); inp.focus();
  }
  function closeCmdk() { $("#cmdk").hidden = true; }
  function renderHits(q) {
    const s = q.trim().toLowerCase();
    const hits = CMDS.filter((c) => !s || c.label.toLowerCase().includes(s)).slice(0, 8);
    $("#cmdkHits").innerHTML = hits.map((c, i) => `<div class="hit ${i === 0 ? "sel" : ""}" data-i="${CMDS.indexOf(c)}">${svg("search")}<span>${esc(c.label)}</span></div>`).join("")
      + (q.trim() ? `<div class="hit" data-send="1">${svg("mic")}<span>Отправить Джарвису: «${esc(q.trim())}»</span></div>` : "");
  }
  $("#cmdkIn").addEventListener("input", (e) => renderHits(e.target.value));
  $("#cmdkIn").addEventListener("keydown", (e) => {
    if (e.key === "Escape") closeCmdk();
    if (e.key === "Enter") { e.preventDefault(); const first = $("#cmdkHits .hit"); first && first.click(); }
  });
  $("#cmdkHits").addEventListener("click", (e) => {
    const h = e.target.closest(".hit"); if (!h) return;
    const q = $("#cmdkIn").value.trim();
    closeCmdk();
    if (h.dataset.send) { location.hash = "#/"; setTimeout(() => sendText(q), 60); return; }
    CMDS[Number(h.dataset.i)].go();
  });
  $("#btnPalette").addEventListener("click", openCmdk);
  document.addEventListener("keydown", (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") { e.preventDefault(); openCmdk(); }
    if (e.key === "Escape" && !$("#cmdk").hidden) closeCmdk();
    if (!$("#stage").hidden) {
      if (e.key === "Escape") { e.preventDefault(); closeStage(); }
      else if (e.key === "ArrowRight" || e.key === "PageDown") { e.preventDefault(); showOp("next"); }
      else if (e.key === "ArrowLeft" || e.key === "PageUp") { e.preventDefault(); showOp("prev"); }
      else if (e.key === " " && !e.target.closest("button,input,textarea")) { e.preventDefault(); showOp(SL.st?.auto ? "pause" : "play"); }
    }
  });

  /* ---------- presentation on the whole screen ----------
   * The server keeps the position (deck, slide, language, auto reading). The screen only shows it and sends
   * button presses there, so the voice, the buttons and the slides always agree. */
  const SL = { st: null, key: "", timer: 0, busy: false };
  async function showOp(op, extra = {}) {
    if (SL.busy && op !== "stop") return;
    SL.busy = true;
    try { const r = await api("/api/hud/action", "POST", { kind: "show", op, ...extra }); if (r.show) applyShow(r.show); return r; }
    catch (e) { toast(e.message); }
    finally { SL.busy = false; }
  }
  async function syncShow() {
    try { applyShow(await api("/api/show")); } catch { /* the next poll tries again */ }
  }
  function applyShow(st) {
    SL.st = st;
    if (STATE.hud) STATE.hud.show = st;
    const stage = $("#stage");
    if (!st || !st.active) {
      if (!stage.hidden) { stage.hidden = true; if (document.fullscreenElement) document.exitFullscreen().catch(() => {}); }
      clearInterval(SL.timer); SL.timer = 0; SL.key = "";
      return;
    }
    if (stage.hidden) { stage.hidden = false; SL.content = ""; if (stage.querySelector(".stage-bg")) stageBg(); }
    if (!SL.timer) SL.timer = setInterval(() => { if (!document.hidden) syncShow(); }, 800);
    const key = `${st.deck}|${st.lang}|${st.i}|${st.auto}|${st.total}`;
    if (key !== SL.key) { SL.key = key; drawStage(); }
  }
  async function openStage(deck = "") {
    const cur = SL.st || STATE.hud?.show;
    if (cur?.active && (!deck || deck === cur.deck)) { applyShow(cur); }
    else { await showOp("start", { deck: deck || "about", lang: cur?.lang || "ru", auto: false }); }
    const st = $("#stage");
    if (!st.hidden && st.requestFullscreen && !document.fullscreenElement) st.requestFullscreen().catch(() => {});
  }
  /* One layout per kind of slide: the talk is not a wall of text, each idea has its own picture. */
  function slideBody(x, lang) {
    const chips = (a) => (a || []).length ? `<ul class="pts">${a.map((p, i) => `<li style="--d:${i}">${esc(p)}</li>`).join("")}</ul>` : "";
    const head = `<div class="kick">${esc(x.kicker || x.title || "")}</div><h2 class="bg">${esc(x.big || "")}</h2>`;
    const cards = (a) => `<div class="cards">${(a || []).map((c, i) => `<div class="card" style="--d:${i}"><span class="ci">${svg(c.i || "star")}</span><b>${esc(c.t)}</b><span>${esc(c.d)}</span></div>`).join("")}</div>`;
    const stats = (a) => `<div class="stats">${(a || []).map((c, i) => `<div class="statx" style="--d:${i}"><b data-count="${Number(c.v) || 0}">0</b><span>${esc(c.l)}</span></div>`).join("")}</div>`;
    switch (x.kind) {
      case "title": return `<div class="lay title"><div class="kick">${esc(x.kicker || "")}</div><h2 class="hero">${esc(x.big)}</h2><p class="lead">${esc(x.sub || "")}</p>${chips(x.points)}</div>`;
      case "problem": return `<div class="lay">${head}<div class="tiles">${(x.points || []).map((p, i) => `<div class="tile" style="--d:${i}"><i>${String(i + 1).padStart(2, "0")}</i>${esc(p)}<small>${lang === "ja" ? "数秒" : lang === "en" ? "seconds" : "секунды"}</small></div>`).join("")}</div><div class="sum">${lang === "ja" ? "＝ 毎日、何時間も" : lang === "en" ? "= hours, every day" : "= часы каждый день"}</div></div>`;
      case "quote": return `<div class="lay">${head}<div class="quote"><span class="mic">${svg("mic")}</span>${esc(x.sub || "")}<span class="wave"><i></i><i></i><i></i><i></i><i></i></span></div></div>`;
      case "features": case "emotions": return `<div class="lay">${head}${cards(x.items)}</div>`;
      case "pipeline": return `<div class="lay">${head}<div class="pipe">${(x.steps || []).map((p, i) => `<div class="node" style="--d:${i}"><b>${i + 1}</b><span>${esc(p)}</span><small>${esc((x.points || [])[i] || "")}</small></div>`).join(`<i class="arrow"></i>`)}</div></div>`;
      case "cycle": { const n = (x.cycle || []).length || 1; return `<div class="lay two">${head.replace("<h2", "<h2 data-split")}<div class="cycle-wrap"><div class="cycle">${(x.cycle || []).map((p, i) => `<div class="cnode" style="--a:${(i / n) * 360 - 90}deg;--d:${i}"><span>${esc(p)}</span></div>`).join("")}<div class="cspin"></div></div>${stats(x.stats)}</div></div>`; }
      case "security": return `<div class="lay">${head}<ul class="checks">${(x.points || []).map((p, i) => `<li style="--d:${i}"><span>${svg("shield")}</span>${esc(p)}</li>`).join("")}</ul></div>`;
      case "layers": return `<div class="lay">${head}<div class="layers">${(x.layers || []).map((p, i) => { const [a, b] = String(p).split(/\s·\s|・/); return `<div class="layer" style="--d:${i}"><b>${esc(a)}</b><span>${esc(b || "")}</span></div>`; }).join("")}</div></div>`;
      case "stats": return `<div class="lay">${head}${stats(x.stats)}</div>`;
      case "demo": return `<div class="lay">${head}<div class="phrases">${(x.phrases || []).map((p, i) => `<div class="phrase" style="--d:${i}"><span class="mic">${svg("mic")}</span>${esc(p)}</div>`).join("")}</div></div>`;
      case "end": return `<div class="lay title end"><div class="kick">${esc(x.kicker || "")}</div><h2 class="hero">${esc(x.big)}</h2><p class="lead">${esc(x.sub || "")}</p></div>`;
      default: return `<div class="lay">${head}${chips(x.points)}</div>`;      // the monthly report
    }
  }
  function drawStage() {
    const st = $("#stage"), s = SL.st || {}, x = s.slide || {}, slides = s.slides || [];
    st.lang = s.lang === "ja" ? "ja" : s.lang === "en" ? "en" : "ru";
    if (!st.querySelector(".stage-bg")) {
      st.innerHTML = `<canvas class="stage-bg" aria-hidden="true"></canvas><div class="stage-bar"><i></i></div><header></header><div class="body"></div><div class="caption" aria-live="polite"></div><footer></footer>`;
      stageBg();
    }
    st.querySelector("header").innerHTML = `
        <div class="seg" role="group" aria-label="Презентация"><button type="button" data-deck="about" aria-pressed="${s.deck === "about"}">О Джарвисе</button><button type="button" data-deck="report" aria-pressed="${s.deck === "report"}">Отчёт за месяц</button></div>
        <div class="seg" role="group" aria-label="Язык">${[["ru", "RU"], ["en", "EN"], ["ja", "JA"]].map(([k, n]) => `<button type="button" data-sl="${k}" aria-pressed="${s.lang === k}">${n}</button>`).join("")}</div>
        <span class="grow"></span><span class="brand-mini">JARVIS · ${(s.i || 0) + 1}/${s.total || 0}</span>
        <button class="btn" data-stage="audio" title="Сохранить всю презентацию одним MP3-файлом">Аудиофайл</button>
        <button class="btn" data-stage="close">Выйти</button>`;
    const contentKey = `${s.deck}|${s.lang}|${s.i}`;
    if (SL.content !== contentKey) {
      SL.content = contentKey; SL.slideAt = performance.now();
      const body = st.querySelector(".body");
      body.className = `body k-${x.kind || "plain"}`;
      body.innerHTML = slideBody(x, s.lang);
      body.querySelectorAll("[data-count]").forEach(countUp);
      const words = String(x.say || "").split(s.lang === "ja" ? /(?<=[、。！？])/ : /\s+/).filter(Boolean);
      st.querySelector(".caption").innerHTML = words.map((w) => `<span>${esc(w)}</span>`).join(s.lang === "ja" ? "" : " ");
      SL.words = words.length; SL.est = Math.max(3, String(x.say || "").length * (s.lang === "ja" ? 0.16 : 0.062));
      st.querySelector(".stage-bar i").style.width = `${((s.i || 0) + 1) / (s.total || 1) * 100}%`;
    }
    st.classList.toggle("auto", !!s.auto);
    st.querySelector("footer").innerHTML = `<button class="btn" data-stage="prev" ${s.i <= 0 ? "disabled" : ""}>Назад</button>
        <div class="dots" style="flex:1" role="group" aria-label="Слайды">${slides.map((sl, i) => `<button type="button" class="${i <= s.i ? "on" : ""}" data-go="${i}" aria-label="Слайд ${i + 1}: ${esc(sl.kicker || sl.title || "")}"></button>`).join("")}</div>
        <button class="btn" data-stage="say">Сказать вслух</button>
        <button class="btn ${s.auto ? "" : "primary"}" data-stage="auto" aria-pressed="${!!s.auto}">${s.auto ? "Пауза" : "Автопоказ с голосом"}</button>
        <button class="btn primary" data-stage="next" ${s.i >= (s.total || 1) - 1 ? "disabled" : ""}>Дальше</button>`;
  }
  function countUp(el) {
    const to = Number(el.dataset.count) || 0, t0 = performance.now(), dur = 1300;
    const step = (t) => { const k = Math.min(1, (t - t0) / dur), e = 1 - Math.pow(1 - k, 3); el.textContent = Math.round(to * e).toLocaleString("ru-RU"); if (k < 1) requestAnimationFrame(step); };
    requestAnimationFrame(step);
  }
  /* The background: the dotted Earth turning slowly, and the spoken words lighting up as they are said. */
  function stageBg() {
    const loop = (t) => {
      const st = $("#stage"); if (!st || st.hidden) { SL.bgRaf = 0; return; }
      SL.bgRaf = requestAnimationFrame(loop);
      const c = st.querySelector(".stage-bg"); if (!c) return;
      const w = Math.round(c.clientWidth * Math.min(1.5, devicePixelRatio || 1)), h = Math.round(c.clientHeight * Math.min(1.5, devicePixelRatio || 1));
      if (c.width !== w || c.height !== h) { c.width = w; c.height = h; }
      if (t - (SL.bgT || 0) > 40 && window.JarvisCore?.earth) { SL.bgT = t; JarvisCore.earth(c, t, palette(PREFS.palette).rgb); }
      if (SL.st?.auto && SL.words) {
        const k = Math.min(1, (performance.now() - SL.slideAt) / 1000 / SL.est), n = Math.floor(k * SL.words);
        const spans = st.querySelectorAll(".caption span");
        spans.forEach((sp, i) => sp.classList.toggle("on", i < n));
      }
    };
    if (!SL.bgRaf) SL.bgRaf = requestAnimationFrame(loop);
  }
  function closeStage() { showOp("stop"); }
  $("#stage").addEventListener("click", async (e) => {
    const b = e.target.closest("[data-stage],[data-sl],[data-deck],[data-go]"); if (!b) return;
    const s = SL.st || {};
    if (b.dataset.sl) return showOp("lang", { lang: b.dataset.sl });
    if (b.dataset.deck) return showOp("lang", { lang: s.lang || "ru", deck: b.dataset.deck });
    if (b.dataset.go) return showOp("go", { i: Number(b.dataset.go) });
    const a = b.dataset.stage;
    if (a === "close") return showOp("stop");
    if (a === "next") return showOp("next");
    if (a === "prev") return showOp("prev");
    if (a === "say") return showOp("say");
    if (a === "auto") return showOp(s.auto ? "pause" : "play");
    if (a === "audio") {
      toast("Готовлю аудиофайл, это займёт до минуты…");
      const r = await showOp("audio", { lang: s.lang || "ru", deck: s.deck || "about" });
      if (r?.file) { toast(r.reply); const link = document.createElement("a"); link.href = `/api/show/audio/${r.file}`; link.download = r.file; document.body.appendChild(link); link.click(); link.remove(); }
    }
  });

  /* ---------- onboarding and analysis (kept from the earlier version, in the new look) ---------- */
  function openOnboarding() {
    if (window.Onboarding) window.Onboarding.open(); else openAnalysis && openAnalysis();
  }
  function openAnalysis() { if (window.Analysis) window.Analysis.open(); }
  window.openStage = openStage; window.closeStage = closeStage;

  /* ---------- boot ---------- */
  function boot() {
    defineWidgets();
    loadPrefs();
    applyLook();
    route();
    connectWs();
    pollHud(); pollSlow();
    setInterval(() => { if (!document.hidden) pollHud(); }, 2500);
    setInterval(() => { if (!document.hidden) pollSlow(); }, 15000);
    setInterval(() => { if (!document.hidden) { const t = document.querySelectorAll("[data-left]"); t.forEach((e) => { const l = Number(e.dataset.left) - Date.now() / 1000; if (l > 0) e.textContent = dur(l); }); } }, 1000);
  }

  /* expose the pieces the pages need */
  window.JV = { $, $$, esc, api, toast, ask, dialog, clone, PREFS: () => PREFS, savePrefs, applyLook, STATE, H, S, PALETTES, palette, LOOKS, DENSITY, PRESETS, DEFAULT_PREFS, svg, ICON, num, dmy, hm, plural, hudAct, pollHud, pollSlow, route, openStage, sendText, renderDashboardShell, widgetDefs: () => WIDGET_DEFS, layoutItems, EDIT, ACT };
  if (document.readyState === "loading") window.addEventListener("DOMContentLoaded", boot);
  else boot();
})();
