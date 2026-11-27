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
  const DEFAULT_PREFS = { palette: "arctic", look: "glass", density: "cozy", anim: true, radius: 16, fs: 14,
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
    if (window.JarvisCore) { JarvisCore.setShape(p.shape, p.rgb); }
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

  /* ---------- widgets ---------- */
  const H = () => STATE.hud || {};
  const btn = (label, act, args = {}, cls = "") => `<button class="btn sm ${cls}" data-act="${act}" data-args='${esc(JSON.stringify(args))}'>${label}</button>`;
  const iconBtn = (name, act, args = {}, label = "") => `<button class="btn sm icon ghost" data-act="${act}" data-args='${esc(JSON.stringify(args))}' aria-label="${esc(label)}" title="${esc(label)}">${svg(name)}</button>`;

  function defineWidgets() {
    const W = (id, name, icon, size, render, extra = {}) => WIDGET_DEFS.push({ id, name, icon, size, render, ...extra });
    W("cpu", "Нагрузка ПК", "cpu", "m", () => {
      const h = H(), s = h.sys || {}, g = h.gpu;
      return `<div class="row" style="align-items:flex-end;gap:14px"><div class="big">${num(s.cpu)}<small>%</small></div><div class="sub" style="padding-bottom:4px">процессор<br>${num(s.cores)} ядер</div></div>
        ${sparkline(STATE.hist.cpu)}
        ${kv("Память", `${num(s.ram_used, 1)} из ${num(s.ram_total, 1)} ГБ`)} ${bar(s.ram_pct, (s.ram_pct || 0) > 85 ? "warn" : "")}
        ${kv("Видеокарта", g ? `${num(g.util)}% · ${num(g.temp)}°C` : "нет данных")} ${bar(g ? g.util : 0)}`;
    });
    W("goals", "Цели", "goal", "s", () => {
      const goals = (H().goals || []).slice(0, 4);
      if (!goals.length) return empty("Целей пока нет", "Добавьте в разделе «Цели»");
      return goals.map((g) => {
        const today = Number((g.log || {})[ymd()] || 0), per = g.per_day || 1, p = clamp((today / per) * 100, 0, 100);
        return `<div class="col"><div class="row"><span class="grow ellipsis">${esc(g.title)}</span>${btn("+1", "goal_mark", { id: g.id }, "")}</div>${bar(p, p >= 100 ? "ok" : "")}<div class="sub">${today} из ${per} сегодня</div></div>`;
      }).join("");
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
      const running = list.filter((p) => p.running).slice(0, 5), others = list.filter((p) => !p.running).slice(0, 4);
      return `<div class="sub">Запущено: ${running.length}</div>` + (running.map((p) => `<div class="kv"><span class="ellipsis">${esc(p.name)}</span><b class="faint small">${p.memory_mb} МБ</b>${btn("Закрыть", "close", { name: p.name })}</div>`).join("") || `<div class="sub">Ничего не запущено.</div>`)
        + `<div class="sub" style="margin-top:6px">Открыть</div><div class="pills">${others.map((p) => `<button class="chip" data-act="open" data-args='${esc(JSON.stringify({ name: p.name }))}'>${esc(p.name)}</button>`).join("")}</div>`;
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
      return `<div class="big">${num(l.lessons_learned ?? 0)}<small>уроков</small></div>
        ${kv("Повторных ошибок", num(l.repeat_mistake_rate ?? 0, 1) + "%")}${kv("Отношения", esc(H().stage?.stage || "—"))}${kv("Фактов о вас", num(STATE.facts ?? "—"))}`;
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
      if (!s.active) return `<div class="sub">Доклад за месяц из ваших дел, целей и команд. Можно сказать голосом: «начни доклад».</div><div class="foot">${btn("Начать", "show_start", {}, "primary")}</div>`;
      return `<div class="sub">Слайд ${s.i + 1} из ${s.total} · ${esc(s.lang)}</div><div class="kv"><span class="ellipsis">${esc(s.slide?.title || "")}</span></div>
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
    return `<article class="w ${item.size || def.size} ${style} ${compact}" data-w="${item.id}" ${EDIT.on ? 'draggable="true"' : ""} aria-label="${esc(def.name)}">
      <div class="w-h"><span class="ico">${svg(def.icon)}</span><span class="ttl ellipsis">${esc(def.name)}</span>${tools}</div>
      <div class="w-b" data-body></div></article>`;
  }
  function renderDashboardShell() {
    const mode = PREFS.layout.mode;
    const center = mode === "center";
    const list = visibleItems();
    const l = list.filter((i) => i.col !== "r"), r = list.filter((i) => i.col === "r");
    const cols = center
      ? `<div class="col-w" id="colL" data-col="l">${l.map(widgetShell).join("")}</div>
         <div class="core-wrap" id="coreWrap">
           <div class="core-disc"><canvas id="orb" role="img" aria-label="Ядро Джарвиса. Нажмите, чтобы говорить"></canvas>
             <div class="core-label"><b>ДЖАРВИС</b><span id="stateTxt">запуск</span></div></div>
           <div class="talk" id="talk" aria-live="polite"><div class="you" id="you"></div><div id="him">Подождите, Джарвис запускается.</div></div>
           <div class="feedback" id="fb"><button type="button" data-act="feedback" data-args='{"rating":1}' aria-label="Ответ верный">👍</button><button type="button" data-act="feedback" data-args='{"rating":-1}' aria-label="Ответ неверный">👎</button><span id="fbMsg"></span></div>
           <form class="form-row" id="askForm" style="width:100%;max-width:520px"><div class="field grow"><input id="askIn" type="text" placeholder="Напишите команду или скажите «Джарвис»" aria-label="Команда для Джарвиса" autocomplete="off"></div><button class="btn primary" type="submit">Отправить</button><button class="btn icon" type="button" id="btnMic" aria-label="Говорить">${svg("mic")}</button></form>
         </div>
         <div class="col-w" id="colR" data-col="r">${r.map(widgetShell).join("")}</div>`
      : `<div class="col-w" id="colL" data-col="l" style="grid-column:1/-1">${list.map(widgetShell).join("")}</div>`;
    const toolbar = `<div class="dash-toolbar">
        <div class="seg" role="group" aria-label="Вид главной"><button type="button" data-act="mode" data-args='{"m":"center"}' aria-pressed="${mode === "center"}">Ядро и виджеты</button><button type="button" data-act="mode" data-args='{"m":"grid"}' aria-pressed="${mode === "grid"}">Сетка</button><button type="button" data-act="mode" data-args='{"m":"focus"}' aria-pressed="${mode === "focus"}">Только ядро</button></div>
        <span class="spacer"></span>
        <button class="btn ${EDIT.on ? "primary" : ""}" data-act="edit" aria-pressed="${EDIT.on}">${svg("move")} ${EDIT.on ? "Готово" : "Настроить виджеты"}</button>
        <button class="btn" data-act="addwidget">${svg("plus")} Добавить виджет</button>
      </div>`;
    $("#view").innerHTML = `<div class="${EDIT.on ? "edit " : ""}">${toolbar}<div class="dash mode-${mode}" id="dash">${cols}</div></div>`;
    $("#view").dataset.page = "home";
    if (center) mountCore();
    bindWidgetDnd();
    paintWidgets(true);
  }
  function paintWidgets(force) {
    $$("#dash .w[data-w]").forEach((el) => {
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
  function setStatus(s) { if (!s) return; STATUS = s; JarvisCore && JarvisCore.set({ status: s }); coreState(); pillLink(); }
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
      if (ev.type === "level") { JarvisCore && JarvisCore.set({ level: Math.min(1, ev.v / 1400) }); if (ev.s && ev.s !== STATUS) setStatus(ev.s); }
      else if (ev.type === "status") setStatus(ev.state);
      else if (ev.type === "message") { addExchange(ev); }
      else if (ev.type === "heard" && !ev.ok) { const y = $("#you"); if (y) y.textContent = "Не разобрал: " + ev.text; }
      else if (ev.type === "data" || ev.type === "settings" || ev.type === "v3" || ev.type === "remote" || ev.type === "connections") { pollSlow(); pollHud(); if (STATE.live && window.PAGES?.[STATE.live]?.onData) PAGES[STATE.live].onData(STATE.hud, true); }
      else if (ev.type === "enroll") toast(ev.state === "on" ? `Запоминаю голос: ${ev.seconds} из ${ev.need} с` : ev.ok ? "Голос запомнен" : "Мало речи, попробуйте ещё раз");
      else if (ev.type === "record") toast(ev.state === "on" ? "Идёт запись. Скажите «стоп»" : "Запись сохранена");
      else if (ev.type === "wizard") { openAnalysis && openAnalysis(); }
      else if (ev.type === "open") { location.hash = ev.panel === "history" ? "#/commands" : "#/settings"; }
      else if (ev.type === "reload") location.reload();
    };
    ws.onclose = () => { setStatus("starting"); setTimeout(connectWs, 2000); };
  }
  function addExchange(ev) {
    if (ev.role === "user") { const y = $("#you"); if (y) y.textContent = "Вы: " + ev.text; }
    else { const h = $("#him"); if (h) h.textContent = ev.text; }
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
    async show_start() { await hudAct("show", { op: "start", lang: "ru" }); pollHud(); openStage("deck"); },
    async show_step({ d }) { await hudAct("show", { op: d > 0 ? "next" : "prev" }); pollHud(); },
    async show_stop() { await hudAct("show", { op: "stop" }); pollHud(); toast("Презентация закончена"); },
    show_open() { openStage("deck"); },
    async wmove({ id, d }) { moveWidget(id, d); },
    wsize({ id }) { const it = itemOf(id); const i = SIZES.indexOf(it.size || "s"); it.size = SIZES[(i + 1) % 3]; savePrefs(); renderDashboardShell(); },
    wstyle({ id }) { const it = itemOf(id); const order = [undefined, "solid", "minimal"]; it.style = order[(order.indexOf(it.style) + 1) % 3]; savePrefs(); renderDashboardShell(); },
    whide({ id }) { itemOf(id).on = false; savePrefs(); renderDashboardShell(); toast("Скрыл. Вернуть: «Настроить виджеты» → «Добавить»"); },
    edit() { EDIT.on = !EDIT.on; renderDashboardShell(); },
    mode({ m }) { PREFS.layout.mode = m; savePrefs(); renderDashboardShell(); },
    addwidget() { openAddWidget(); },
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
  function openAddWidget() {
    const hidden = layoutItems().filter((i) => i.on === false);
    const list = WIDGET_DEFS.map((w) => {
      const it = itemOf(w.id), on = it && it.on !== false;
      return `<label class="item"><span class="ico" style="width:26px;height:26px;border-radius:8px;background:rgba(var(--accent-rgb),.12);color:var(--accent);display:grid;place-items:center">${svg(w.icon)}</span><span class="grow"><b style="font-weight:550">${esc(w.name)}</b></span><label class="switch"><input type="checkbox" data-addw="${w.id}" ${on ? "checked" : ""} aria-label="${esc(w.name)}"><span></span></label></label>`;
    }).join("");
    const d = dialog(`<p>Включайте и выключайте виджеты. Порядок и место меняются кнопками на самих виджетах.</p><div class="list" id="addList">${list}</div>`, "Виджеты");
    d.addEventListener("change", (e) => {
      const t = e.target; if (!t.dataset.addw) return;
      const it = itemOf(t.dataset.addw); if (!it) return;
      it.on = t.checked; if (t.checked) it.col = it.col || "r";
      savePrefs(); renderDashboardShell();
    });
    void hidden;
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
      setHeader("Главная", "Ядро и ваши виджеты. Настройте любой виджет кнопкой «Настроить виджеты».", "");
      view.innerHTML = ""; renderDashboardShell(); return;
    }
    const p = PAGES[page];
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
    { label: "Начать презентацию", go: () => ACT.show_start() },
    { label: "Проанализировать ноутбук", go: () => openAnalysis && openAnalysis() },
    { label: "Настроить виджеты", go: () => { location.hash = "#/"; setTimeout(() => ACT.edit(), 50); } },
    { label: "Добавить виджет", go: () => { location.hash = "#/"; setTimeout(openAddWidget, 60); } },
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
    if (e.key === "Escape" && !$("#stage").hidden) closeStage();
    if (!$("#stage").hidden && (e.key === "ArrowRight" || e.key === "ArrowLeft")) ACT.show_step({ d: e.key === "ArrowRight" ? 1 : -1 });
  });

  /* ---------- presentation on the whole screen ---------- */
  const SL = { slides: [], i: 0, lang: "ru", mode: "deck", closedKey: "" };
  async function openStage(mode = "deck") {
    SL.mode = mode;
    const st = $("#stage"); st.hidden = false;
    try { const r = await api("/api/hud/action", "POST", { kind: "deck", lang: SL.lang }); SL.slides = r.slides || []; SL.i = (STATE.hud?.show?.i) || 0; }
    catch (e) { toast(e.message); }
    drawStage();
    st.requestFullscreen && st.requestFullscreen().catch(() => {});
  }
  function drawStage() {
    const st = $("#stage"), x = SL.slides[SL.i] || {};
    st.innerHTML = `<header><div class="seg" role="group" aria-label="Язык">${[["ru", "RU"], ["en", "EN"], ["ja", "JA"]].map(([k, n]) => `<button type="button" data-sl="${k}" aria-pressed="${SL.lang === k}">${n}</button>`).join("")}</div><span class="grow"></span><button class="btn" data-stage="close">Выйти</button></header>
      <div class="body"><div class="ti">${esc(x.title || "")}</div><div class="bg">${esc(x.big || "")}</div><div class="su">${esc(x.say || "")}</div></div>
      <footer><button class="btn" data-stage="prev">Назад</button><div class="dots" style="flex:1">${SL.slides.map((_, i) => `<i class="${i <= SL.i ? "on" : ""}"></i>`).join("")}</div><button class="btn" data-stage="say">Сказать вслух</button><button class="btn primary" data-stage="next">Дальше</button></footer>`;
  }
  function closeStage() { $("#stage").hidden = true; if (document.fullscreenElement) document.exitFullscreen(); }
  $("#stage").addEventListener("click", async (e) => {
    const b = e.target.closest("[data-stage],[data-sl]"); if (!b) return;
    if (b.dataset.sl) { SL.lang = b.dataset.sl; await openStage("deck"); return; }
    const a = b.dataset.stage;
    if (a === "close") closeStage();
    if (a === "next") { SL.i = Math.min(SL.slides.length - 1, SL.i + 1); drawStage(); }
    if (a === "prev") { SL.i = Math.max(0, SL.i - 1); drawStage(); }
    if (a === "say" && SL.slides[SL.i]) api("/api/say", "POST", { text: SL.slides[SL.i].say, lang: SL.lang }).catch(() => {});
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
