/* Jarvis home: the core and 30 widgets. Data: GET /api/hud. Buttons: POST /api/hud/action (never a voice command). */
"use strict";
let LV = 0, LV_T = 0, LAST = 0;
let D = null;                                           // last snapshot
const H = { cpu: [], ram: [], gpu: [], up: [], down: [], ping: [], bat: [], cpuAll: [] };
const U = { card: false, find: { q: "", items: null }, note: { q: "", items: null }, day: null, lang: "ru", cards: null, addCard: false };
const hEl = (id) => document.getElementById(id);
const hE = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const hDay = (d = new Date()) => d.toLocaleDateString("sv-SE");
const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
const plur = (n, a, b, c) => (n % 10 === 1 && n % 100 !== 11 ? a : n % 10 >= 2 && n % 10 <= 4 && (n % 100 < 10 || n % 100 >= 20) ? b : c);

/* ---------- saved layout ---------- */
const CORE_L = ["goals", "focus", "programs", "pc", "net", "battery"], CORE_R = ["tv", "study", "weather", "brain", "sound", "history"];
const DEF = () => ({ v: 2, view: "core", left: [...CORE_L], right: [...CORE_R], order: [], hidden: {}, style: {}, size: {}, pins: [],
  orbit: false, dnd: true, tiles: false, theme: "cyber", accent: "arctic", cols: "6" });
let C = DEF();
try { const x = JSON.parse(localStorage.getItem("hud2") || "null"); if (x && x.v === 2) C = { ...DEF(), ...x }; } catch { /* private window */ }
const save = () => { try { localStorage.setItem("hud2", JSON.stringify(C)); } catch { /* private window */ } };
const STYLES = [["glass", "Glass"], ["matrix", "Matrix"], ["minimal", "Minimal"], ["ring", "Кольцо"]];
const THEMES = [["cyber", "Cyber-HUD"], ["glass", "Glass"], ["solid", "Solid Dark"], ["minimal", "Minimal"]];
const PALETTES = [
  { id: "arctic", name: "Arctic Cyan", bg: "#030508", a: "#00f5ff", rgb: "0,245,255", sub: "Серебристо-циановый, стекло" },
  { id: "solar", name: "Solar Magma", bg: "#030406", a: "#ff7a1a", rgb: "255,122,26", sub: "Янтарно-огненный, сетка" },
  { id: "emerald", name: "Emerald Matrix", bg: "#030706", a: "#10b981", rgb: "16,185,129", sub: "Изумрудный, монитор" },
  { id: "crimson", name: "Crimson Sentinel", bg: "#050304", a: "#ff2a55", rgb: "255,42,85", sub: "Рубиново-красный, щит" },
  { id: "violet", name: "Violet Astrolabe", bg: "#05040a", a: "#8b5cf6", rgb: "139,92,246", sub: "Фиолетовый, орбиты" },
];
const OLD_ACC = { cyan: "arctic", amber: "solar", green: "emerald", violet: "violet", rose: "crimson", white: "arctic" };
const palette = (id) => PALETTES.find((p) => p.id === id) || PALETTES[0];
function applyPalette() {
  const p = palette(C.accent), st = document.body.style;
  st.setProperty("--hx-a", p.a); st.setProperty("--hx-a-rgb", p.rgb); st.setProperty("--hx-bg", p.bg);
  accRGB = p.rgb;
}

/* ---------- small pieces ---------- */
const P = {
  up: '<path d="m6 15 6-6 6 6"/>', down: '<path d="m6 9 6 6 6-6"/>', left: '<path d="m15 6-6 6 6 6"/>', right: '<path d="m9 6 6 6-6 6"/>',
  power: '<path d="M12 3v8"/><path d="M6.5 7a8 8 0 1 0 11 0"/>', plus: '<path d="M12 5v14M5 12h14"/>', minus: '<path d="M5 12h14"/>',
  mute: '<path d="M4 10v4h4l5 4V6L8 10z"/><path d="m17 9 4 6M21 9l-4 6"/>', vol: '<path d="M4 10v4h4l5 4V6L8 10z"/><path d="M16.5 9a4 4 0 0 1 0 6"/>',
  home: '<path d="M4 11 12 4l8 7v9H4z"/>', back: '<path d="M9 7 4 12l5 5"/><path d="M4 12h11a5 5 0 0 1 0 10"/>', play: '<path d="M8 5v14l11-7z"/>', pause: '<path d="M8 5v14M16 5v14"/>',
  x: '<path d="M6 6l12 12M18 6 6 18"/>', size: '<path d="M14 4h6v6M10 20H4v-6M20 4l-7 7M4 20l7-7"/>', src: '<path d="M4 12h11M11 8l4 4-4 4"/><path d="M15 4h5v16h-5"/>',
  sun: '<circle cx="12" cy="12" r="4"/><path d="M12 2v3M12 19v3M2 12h3M19 12h3M5 5l2 2M17 17l2 2M5 19l2-2M17 7l2-2"/>', cloud: '<path d="M7 18h10a4 4 0 0 0 .5-8A6 6 0 0 0 6 9.5 4.3 4.3 0 0 0 7 18z"/>',
  rain: '<path d="M7 14h10a4 4 0 0 0 .5-8A6 6 0 0 0 6 5.5 4.3 4.3 0 0 0 7 14z"/><path d="m8 18-1 3M12 18l-1 3M16 18l-1 3"/>', snow: '<path d="M12 3v18M4 7.5l16 9M20 7.5l-16 9"/>',
  storm: '<path d="M7 13h10a4 4 0 0 0 .5-8A6 6 0 0 0 6 4.5 4.3 4.3 0 0 0 7 13z"/><path d="m12 13-3 5h4l-2 4"/>', fog: '<path d="M4 8h16M6 12h12M4 16h16"/>',
};
const ic = (n) => `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${P[n] || ""}</svg>`;
/** button: text, action, arguments, class */
const B = (t, a, arg = {}, cls = "", label = "") => `<button type="button" class="b ${cls}" data-a="${a}" data-v="${hE(JSON.stringify(arg))}"${label ? ` aria-label="${hE(label)}" title="${hE(label)}"` : ""}>${t}</button>`;
const bar = (p, cls = "") => `<span class="bar ${cls}"><i style="width:${clamp(p || 0, 0, 100)}%"></i></span>`;
const lvl = (p) => (p >= 90 ? "bad" : p >= 75 ? "warn" : "");
const R = (x, m = "", pre = "") => `<div class="r">${pre}<span class="x">${x}</span>${m !== "" ? `<span class="m">${m}</span>` : ""}</div>`;
const dot = (on) => `<i class="dot ${on ? "on" : ""}"></i>`;
const none = (t) => `<div class="empty2">${t}</div>`;
const wait = none("Читаю данные…");
const hm = (min) => (min >= 60 ? `${Math.floor(min / 60)} ч ${Math.round(min % 60)} мин` : `${Math.round(min)} мин`);
const dur = (s) => { s = Math.max(0, Math.round(s)); const h = Math.floor(s / 3600), m = Math.floor(s % 3600 / 60); return h ? `${h}:${String(m).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}` : `${m}:${String(s % 60).padStart(2, "0")}`; };
const rate = (b) => (b >= 1048576 ? (b / 1048576).toFixed(1) + " МБ/с" : Math.round(b / 1024) + " КБ/с");
const gbt = (b) => (b / 1073741824 >= 1 ? (b / 1073741824).toFixed(1) + " ГБ" : Math.round(b / 1048576) + " МБ");
const icoOf = (p) => (p.icon ? `<img class="ico" src="/api/hud/icon/${p.icon}" alt="">` : `<span class="ico l">${hE(p.name[0])}</span>`);
function spark(vals, color = "var(--hx-a)", max = 100) {
  if (vals.length < 2) return '<svg class="sp" viewBox="0 0 100 34"></svg>';
  const top = Math.max(max, ...vals, 1), st = 100 / (vals.length - 1);
  const pts = vals.map((v, i) => `${(i * st).toFixed(1)} ${(32 - v / top * 30).toFixed(1)}`).join("L");
  return `<svg class="sp" viewBox="0 0 100 34" preserveAspectRatio="none" aria-hidden="true"><path d="M0 34L${pts}L100 34Z" fill="${color}" opacity=".13"/><path d="M${pts}" fill="none" stroke="${color}" stroke-width="1.6" stroke-linejoin="round"/></svg>`;
}
const openT = () => (D.tasks || []).filter((t) => !t.done).sort((a, b) => (a.due || "9999").localeCompare(b.due || "9999"));
const doneToday = () => (D.tasks || []).filter((t) => t.done && String(t.done_at || "").slice(0, 10) === hDay());
const dueTxt = (d) => { if (!d) return ""; const x = new Date(d), n = new Date(); const day = hDay(x); const t = x.toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" }); return day === hDay(n) ? t : x.toLocaleDateString("ru-RU", { day: "numeric", month: "short" }) + " " + t; };
const taskRow = (t) => `<label class="r"><input type="checkbox" class="ck" data-done="${hE(t.id)}" aria-label="Выполнено: ${hE(t.text)}"><span class="x" title="${hE(t.text)}">${hE(t.text)}</span>${t.due ? `<span class="m ${new Date(t.due) < new Date() ? "bad" : ""}">${dueTxt(t.due)}</span>` : ""}</label>`;
const form = (kind, ph, btn = "+", label = "") => `<form data-f="${kind}"><input type="text" name="q" placeholder="${hE(ph)}" aria-label="${hE(label || ph)}" autocomplete="off" maxlength="160"><button class="b" aria-label="Добавить">${btn}</button></form>`;
const last7 = () => [...Array(7)].map((_, i) => { const d = new Date(); d.setDate(d.getDate() - 6 + i); return d; });
const goalToday = (g) => Number((g.log || {})[hDay()] || 0);
const goalPct = (g) => (g.per_day ? clamp(goalToday(g) / g.per_day * 100, 0, 100) : goalToday(g) ? 100 : 0);
const weekMark = (g) => last7().filter((d) => (g.log || {})[hDay(d)]).length;
function events() {
  const out = openT().filter((t) => t.due).map((t) => ({ at: t.due, text: t.text, id: t.id }));
  (D.reminders || []).forEach((r) => out.push({ at: r.at, text: r.text, rem: true }));
  return out.sort((a, b) => a.at.localeCompare(b.at));
}
const hist = () => (D.history || []).slice().reverse();
const progs = () => D.programs || [];
const running = () => progs().filter((p) => p.running);
const btHead = () => (D.bt || []).find((d) => /sound|bud|head|r60|ear|науш/i.test(d.name)) || (D.bt || [])[0];
const tvOn = () => D.tv && D.tv.online && D.tv.power === "on";
const focusLeft = () => Math.max(0, (D.focus?.until || 0) - Date.now() / 1000);
let focusTotal = 0;

/* ---------- 30 widgets. full = Glass, rows = Matrix, big = Minimal and Ring {v,u,line,pct}, act = main buttons ---------- */
const W = [
  ["goals", "Цели и Rule of 3", {
    full() {
      const three = openT().slice(0, 3), dn = doneToday().length;
      return `<div class="sub">Три главных дела · сделано сегодня: <b class="acc">${dn}</b></div>` + (three.map(taskRow).join("") || none("Дел нет. Впишите первое ниже."))
        + (D.goals || []).slice(0, 4).map((g) => `<div class="r"><span class="x" title="${hE(g.title)}">${hE(g.title)}</span>${bar(goalPct(g))}<span class="m">${goalToday(g)}${g.per_day ? "/" + g.per_day : ""}</span>${B("+1", "goal_mark", { id: g.id }, "s", "Шаг по цели " + g.title)}</div>`).join("") + form("task", "Новое дело");
    },
    rows: () => [["Открытых дел", openT().length], ["Сделано сегодня", doneToday().length], ["Целей", (D.goals || []).length], ...openT().slice(0, 3).map((t, i) => ["#" + (i + 1), t.text])],
    big: () => { const dn = doneToday().length, all = dn + Math.min(3, openT().length); return { v: dn, u: "/ " + (all || 3), line: openT()[0]?.text || "Дел на сегодня нет", pct: all ? dn / all * 100 : 0 }; },
  }],
  ["habits", "Матрица привычек 7×7", {
    full() {
      const gs = (D.goals || []).slice(0, 7), days = last7();
      if (!gs.length) return none("Привычка — это цель, которую вы отмечаете каждый день. Добавьте первую, например «Японский».") + form("goal", "Новая привычка");
      return `<div class="grid7"><span></span>${days.map((d) => `<span class="dim" style="text-align:center">${"ВПВСЧПС"[d.getDay()]}</span>`).join("")}`
        + gs.map((g) => `<span class="x" style="white-space:nowrap;overflow:hidden;text-overflow:ellipsis" title="${hE(g.title)}">${hE(g.title)}</span>` + days.map((d) => { const k = hDay(d), v = Number((g.log || {})[k] || 0), ok = v && (!g.per_day || v >= g.per_day); return `<button type="button" class="cell ${ok ? "on" : v ? "part" : ""}" data-a="goal_mark" data-v="${hE(JSON.stringify({ id: g.id, day: k, value: ok ? 0 : g.per_day || 1 }))}" aria-label="${hE(g.title)}, ${k}${ok ? ", отмечено" : ""}"></button>`; }).join("")).join("") + "</div>" + (gs.length < 7 ? form("goal", "Новая привычка") : "");
    },
    rows: () => (D.goals || []).slice(0, 7).map((g) => [g.title, weekMark(g) + " / 7"]),
    big: () => { const gs = (D.goals || []).slice(0, 7), n = gs.reduce((a, g) => a + weekMark(g), 0), all = gs.length * 7; return { v: n, u: all ? "/ " + all : "", line: gs.length ? "отметок за 7 дней" : "Привычек пока нет", pct: all ? n / all * 100 : 0 }; },
  }],
  ["deadlines", "Дедлайны", {
    full() {
      const ev = events(), days = [...Array(7)].map((_, i) => { const d = new Date(); d.setDate(d.getDate() + i); return d; });
      return `<div class="week">${days.map((d) => { const k = hDay(d), has = ev.some((e) => e.at.slice(0, 10) === k); return `<button type="button" class="${k === hDay() ? "today" : ""} ${has ? "has" : ""} ${U.day === k ? "sel" : ""}" data-a="ui_day" data-v="${hE(JSON.stringify({ day: k }))}" aria-label="${k}">${d.toLocaleDateString("ru-RU", { weekday: "short" })}<b>${d.getDate()}</b><i></i></button>`; }).join("")}</div>`
        + (ev.filter((e) => !U.day || e.at.slice(0, 10) === U.day).slice(0, 6).map((e) => R(hE(e.text), `<span class="${new Date(e.at) < new Date() ? "bad" : ""}">${dueTxt(e.at)}</span>`, dot(e.rem))).join("") || none(U.day ? "На этот день сроков нет." : "Сроков нет. Скажите «добавь дело … завтра в 10».")) + (U.day ? form("task_day", "Дело на " + U.day.slice(8) + "." + U.day.slice(5, 7)) : "");
    },
    rows: () => events().slice(0, 6).map((e) => [e.text, dueTxt(e.at)]),
    big: () => { const e = events().find((x) => new Date(x.at) > new Date()), over = events().filter((x) => !x.rem && new Date(x.at) < new Date()).length; if (!e) return { v: over || "0", u: over ? "просрочено" : "", line: over ? "дел с прошедшим сроком" : "Ближайших сроков нет", pct: 0 }; const h = (new Date(e.at) - Date.now()) / 3600000; return { v: h < 24 ? Math.round(h) : Math.round(h / 24), u: h < 24 ? "ч" : "дн", line: e.text, pct: clamp(100 - h / 168 * 100, 2, 100) }; },
  }],
  ["calendar", "Календарь задач", {
    full() {
      const n = new Date(), first = new Date(n.getFullYear(), n.getMonth(), 1), s = new Date(first); s.setDate(1 - (first.getDay() + 6) % 7);
      const ev = events(); let cells = "";
      for (let i = 0; i < 42; i++) { const d = new Date(s); d.setDate(s.getDate() + i); if (i >= 35 && d.getMonth() !== n.getMonth()) break; const k = hDay(d); cells += `<button type="button" class="${d.getMonth() !== n.getMonth() ? "out" : ""} ${k === hDay() ? "today" : ""} ${ev.some((e) => e.at.slice(0, 10) === k) ? "has" : ""} ${U.day === k ? "sel" : ""}" data-a="ui_day" data-v="${hE(JSON.stringify({ day: k }))}" aria-label="${k}">${d.getDate()}<i></i></button>`; }
      return `<div class="month">${["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"].map((x) => `<span>${x}</span>`).join("")}${cells}</div>` + (U.day ? ev.filter((e) => e.at.slice(0, 10) === U.day).map((e) => R(hE(e.text), dueTxt(e.at))).join("") + form("task_day", "Дело на " + U.day.slice(8) + "." + U.day.slice(5, 7)) : "");
    },
    rows: () => [["Сегодня", new Date().toLocaleDateString("ru-RU", { day: "numeric", month: "long" })], ["Событий впереди", events().length], ...events().slice(0, 4).map((e) => [e.text, dueTxt(e.at)])],
    big: () => { const n = new Date(), m = new Date(n.getFullYear(), n.getMonth() + 1, 0).getDate(); return { v: n.getDate(), u: n.toLocaleDateString("ru-RU", { month: "short" }), line: n.toLocaleDateString("ru-RU", { weekday: "long" }) + " · событий: " + events().length, pct: n.getDate() / m * 100 }; },
  }],
  ["focus", "Фокус дня", {
    full() {
      const on = focusLeft() > 0, t = openT()[0];
      return `<div class="bigrow"><b data-left="${D.focus?.until || 0}">${on ? dur(focusLeft()) : "25:00"}</b><span class="sub">${on ? "закрыто отвлечений: " + (D.focus.closed || 0) : "фокус-щит закрывает YouTube, TikTok, Steam"}</span></div>`
        + R(t ? hE(t.text) : '<span class="dim">Главного дела нет</span>', t ? dueTxt(t.due) : "") + `<div class="bs f" style="margin-top:auto">${on ? B("Остановить", "focus", { minutes: 0 }, "d") : [25, 50, 90].map((m) => B(m + " мин", "focus", { minutes: m }, m === 25 ? "p" : "")).join("")}</div>`;
    },
    rows: () => [["Щит", focusLeft() > 0 ? "включён" : "выключен"], ["Осталось", focusLeft() > 0 ? dur(focusLeft()) : "—"], ["Закрыто", D.focus?.closed || 0], ["Главное дело", openT()[0]?.text || "—"]],
    big: () => { const l = focusLeft(); return { v: l > 0 ? Math.ceil(l / 60) : 25, u: "мин", line: l > 0 ? "осталось в фокусе" : openT()[0]?.text || "Нажмите, чтобы начать", pct: l > 0 ? l / Math.max(focusTotal, l, 1500) * 100 : 0 }; },
    act: () => (focusLeft() > 0 ? B("Стоп", "focus", { minutes: 0 }, "d") : B("Начать 25", "focus", { minutes: 25 }, "p")),
  }],
  ["projects", "Проекты и OKR", {
    full() {
      const ps = D.index?.projects || [];
      return (D.goals || []).slice(0, 3).map((g) => `<div class="r"><span class="x">${hE(g.title)}</span>${bar(weekMark(g) / 7 * 100)}<span class="m">${weekMark(g)}/7</span></div>`).join("")
        + (ps.map((p) => `<div class="r"><span class="x" title="${hE(p.path)}">${hE(p.name)}</span>${B("Папка", "project", { path: p.path }, "s", "Открыть папку " + p.name)}</div>`).join("") || none("Проекты появятся после изучения файлов (виджет 10)."));
    },
    rows: () => [["Проектов на ПК", D.index?.projects_n ?? 0], ...(D.index?.projects || []).slice(0, 5).map((p) => [p.name, p.path.slice(0, 2)])],
    big: () => { const gs = D.goals || [], n = gs.reduce((a, g) => a + weekMark(g), 0); return { v: D.index?.projects_n ?? 0, u: "", line: "проектов на компьютере", pct: gs.length ? n / gs.length / 7 * 100 : 0 }; },
  }],
  ["programs", "Программы ПК", {
    full: () => (D.programs ? progs().map((p) => `<div class="r prog">${icoOf(p)}<span class="x" title="${hE(p.name)}">${hE(p.name)}</span>${p.running ? `<span class="m ok">${p.memory_mb} МБ</span>${B("Закрыть", "close", { name: p.name }, "s")}` : B("Открыть", "open", { name: p.name }, "s")}<button type="button" class="star ${C.pins.includes(p.name) ? "on" : ""}" data-a="ui_pin" data-v="${hE(JSON.stringify({ name: p.name }))}" aria-label="В быстрый запуск: ${hE(p.name)}">★</button></div>`).join("") : wait),
    rows: () => [["Всего программ", progs().length], ["Запущено", running().length], ...running().slice(0, 5).map((p) => [p.name, p.memory_mb + " МБ"])],
    big: () => ({ v: running().length, u: "/ " + progs().length, line: running().slice(0, 3).map((p) => p.name).join(", ") || "Ничего не запущено", pct: progs().length ? running().length / progs().length * 100 : 0 }),
  }],
  ["tasks", "Диспетчер задач", {
    full: () => (D.top ? D.top.map((p) => `<div class="r"><span class="x" title="${hE(p.name)}">${hE(p.name.replace(/\.exe$/i, ""))}${p.count > 1 ? ` <span class="dim">×${p.count}</span>` : ""}</span><span class="m">${p.cpu}%</span><span class="m">${p.mem} МБ</span>${p.safe ? B("Убить", "kill", { pid: p.pid, name: p.name }, "s d", "Завершить " + p.name) : ""}</div>`).join("") : wait),
    rows: () => (D.top || []).slice(0, 7).map((p) => [p.name, `${p.cpu}% ${p.mem} МБ`]),
    big: () => { const p = (D.top || []).slice().sort((a, b) => b.mem - a.mem)[0]; return { v: D.sys.procs, u: "процессов", line: p ? `больше всех: ${p.name}, ${p.mem} МБ` : "", pct: D.sys.ram_pct }; },
    act: () => B("Диспетчер Windows", "settings", { page: "taskmgr" }),
  }],
  ["launch", "Быстрый запуск", {
    full() { const pin = C.pins.map((n) => progs().find((p) => p.name === n)).filter(Boolean), list = pin.length ? pin : progs().slice(0, 12); return D.programs ? `<div class="apps">${list.map((p) => `<button type="button" data-a="open" data-v="${hE(JSON.stringify({ name: p.name }))}" aria-label="Открыть ${hE(p.name)}">${icoOf(p)}<span>${hE(p.name)}</span>${p.running ? dot(true) : ""}</button>`).join("")}</div>` + (pin.length ? "" : '<div class="sub dim">Отметьте ★ в «Программы ПК», чтобы собрать свой набор.</div>') : wait; },
    rows: () => (C.pins.length ? C.pins : progs().slice(0, 6).map((p) => p.name)).slice(0, 7).map((n) => [n, progs().find((p) => p.name === n)?.running ? "запущена" : "—"]),
    big: () => { const n = C.pins.length || Math.min(12, progs().length); return { v: n, u: "", line: "программ в быстром запуске", pct: n ? running().length / n * 100 : 0 }; },
    act: () => (C.pins.length ? C.pins : progs().slice(0, 2).map((p) => p.name)).slice(0, 2).map((n) => B(hE(n), "open", { name: n })).join(""),
  }],
  ["files", "Файловый индекс", {
    full() {
      const x = D.index || {};
      return `<form data-f="find" style="margin:0"><input type="search" name="q" value="${hE(U.find.q)}" placeholder="Имя файла" aria-label="Найти файл" autocomplete="off"><button class="b p">Найти</button></form>`
        + (U.find.items ? U.find.items.map((f) => `<div class="r"><span class="x" title="${hE(f.path)}">${hE(f.name)}</span>${B("Показать", "reveal", { path: f.path }, "s", "Показать в папке " + f.name)}</div>`).join("") || none("Ничего не нашёл.") : `<div class="sub">${x.built ? `В индексе ${x.files.toLocaleString("ru-RU")} файлов · ${new Date(x.at).toLocaleDateString("ru-RU")}` : "Имена файлов ещё не изучены."}</div>`)
        + `<div class="bs" style="margin-top:auto">${x.running ? '<span class="sub acc">Изучаю файлы…</span>' : B(x.built ? "Обновить индекс" : "Изучить файлы", "ui_index", {}, "s")}</div>`;
    },
    rows: () => [["Файлов", (D.index?.files || 0).toLocaleString("ru-RU")], ["Проектов", D.index?.projects_n || 0], ["Обновлён", D.index?.at ? new Date(D.index.at).toLocaleString("ru-RU", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" }) : "—"], ["Сейчас", D.index?.running ? "изучаю" : "готов"]],
    big: () => ({ v: D.index?.files >= 1000 ? (D.index.files / 1000).toFixed(1) : D.index?.files || 0, u: D.index?.files >= 1000 ? "тыс." : "", line: "файлов можно найти по имени", pct: D.index?.built ? 100 : 0 }),
    act: () => B("Обновить", "ui_index"),
  }],
  ["logs", "Терминал логов", {
    full: () => (D.logs ? `<div class="log">${D.logs.slice().reverse().map((l) => `<div class="${/ERROR|Traceback|Error/.test(l) ? "e" : /WARN/.test(l) ? "w" : ""}">${hE(l)}</div>`).join("")}</div>` : wait),
    rows: () => [["Строк", (D.logs || []).length], ["Ошибок", (D.logs || []).filter((l) => /ERROR/.test(l)).length], ["Последняя", (D.logs || []).at(-1)?.slice(0, 8) || "—"], ["Событие", (D.logs || []).at(-1)?.slice(9) || "—"]],
    big: () => { const n = (D.logs || []).filter((l) => /ERROR/.test(l)).length, all = (D.logs || []).length || 1; return { v: n, u: plur(n, "ошибка", "ошибки", "ошибок"), line: (D.logs || []).at(-1)?.slice(9) || "", pct: 100 - n / all * 100 }; },
  }],
  ["services", "Службы Windows", {
    full: () => (D.services ? D.services.map((s) => R(hE(s.name), s.on ? "работает" : "стоит", dot(s.on))).join("") + `<div class="bs" style="margin-top:auto">${B("Анализ ноутбука", "ui_doctor", {}, "s")}</div>` : wait),
    rows: () => (D.services || []).slice(0, 8).map((s) => [s.name, s.on ? "RUN" : "STOP"]),
    big: () => { const a = D.services || [], n = a.filter((s) => s.on).length; return { v: n, u: "/ " + a.length, line: a.filter((s) => !s.on).map((s) => s.name).join(", ") ? "стоят: " + a.filter((s) => !s.on).map((s) => s.name).join(", ") : "всё работает", pct: a.length ? n / a.length * 100 : 0 }; },
    act: () => B("Анализ", "ui_doctor"),
  }],
  ["pc", "Загрузка ПК", {
    full: () => [["Процессор", H.cpu, D.sys.cpu, "%", "var(--hx-a)"], ["Память", H.ram, D.sys.ram_pct, "%", "#a78bff"], ["Видеокарта", H.gpu, D.gpu?.util, "%", "#37e0a0"]].map(([n, h, v, u, c]) => `<div><div class="r"><span class="x sub">${n}</span><span class="m" style="color:${c}">${v == null ? "—" : Math.round(v) + u}</span></div>${spark(h, c)}</div>`).join("") + `<div class="sub">${D.sys.ram_used} из ${D.sys.ram_total} ГБ${D.gpu ? ` · ${D.gpu.temp}°C` : ""} · ${D.sys.procs} процессов</div>`,
    rows: () => [["CPU", D.sys.cpu + "%"], ["RAM", `${D.sys.ram_used}/${D.sys.ram_total} ГБ`], ["GPU", D.gpu ? D.gpu.util + "%" : "—"], ["VRAM", D.gpu ? `${D.gpu.used}/${D.gpu.total} МБ` : "—"], ["GPU t", D.gpu ? D.gpu.temp + "°C" : "—"], ["Работает", hm(D.sys.uptime / 60)]],
    big: () => ({ v: Math.round(D.sys.cpu), u: "%", line: `память ${Math.round(D.sys.ram_pct)}% · GPU ${D.gpu?.util ?? "—"}%`, pct: D.sys.cpu }),
  }],
  ["net", "Сеть и интернет", {
    full: () => `<div class="bigrow"><b>${D.ping == null ? "—" : D.ping}</b><span class="sub">мс до 1.1.1.1</span></div><div class="r"><span class="x sub">Приём</span><span class="m acc">${rate(D.net.down)}</span></div>${spark(H.down, "var(--hx-a)", 1)}<div class="r"><span class="x sub">Отдача</span><span class="m" style="color:#a78bff">${rate(D.net.up)}</span></div>${spark(H.up, "#a78bff", 1)}` + R("Wi-Fi", D.wifi?.ssid ? `${hE(D.wifi.ssid)} · ${D.wifi.signal}%` : "—") + R("VPN", D.wifi?.vpn?.length ? hE(D.wifi.vpn[0]) : "выключен"),
    rows: () => [["Пинг", D.ping == null ? "нет связи" : D.ping + " мс"], ["Приём", rate(D.net.down)], ["Отдача", rate(D.net.up)], ["Wi-Fi", D.wifi?.ssid || "—"], ["Сигнал", D.wifi?.signal != null ? D.wifi.signal + "%" : "—"], ["VPN", D.wifi?.vpn?.[0] || "выкл"], ["Всего", gbt(D.net.total_down)]],
    big: () => ({ v: D.ping ?? "—", u: D.ping == null ? "" : "мс", line: `${D.wifi?.ssid || "Wi-Fi"} · ↓ ${rate(D.net.down)}`, pct: D.wifi?.signal || 0 }),
    act: () => B("Настройки сети", "settings", { page: "wifi" }),
  }],
  ["disk", "Хранилище", {
    full: () => ((D.disks || []).map((d) => `<div><div class="r"><span class="x">Диск ${hE(d.name)}</span><span class="m">свободно ${d.free} ГБ</span></div>${bar(d.pct, lvl(d.pct))}<div class="sub">${d.used} из ${d.total} ГБ · ${Math.round(d.pct)}%</div></div>`).join("") || wait) + `<div class="bs" style="margin-top:auto">${B("Память Windows", "settings", { page: "storage" }, "s")}</div>`,
    rows: () => (D.disks || []).flatMap((d) => [[d.name + " занято", d.used + " ГБ"], [d.name + " свободно", d.free + " ГБ"]]),
    big: () => { const d = (D.disks || []).slice().sort((a, b) => b.pct - a.pct)[0] || { pct: 0, free: 0, name: "" }; return { v: d.free, u: "ГБ", line: "свободно на " + d.name, pct: d.pct }; },
    act: () => B("Память Windows", "settings", { page: "storage" }),
  }],
  ["sound", "Звук и микрофон", {
    full: () => { const a = D.audio; return a ? `<div class="r"><button type="button" class="b sq ${a.mute ? "d" : ""}" data-a="mute" data-v="{}" aria-label="${a.mute ? "Включить звук" : "Выключить звук"}">${ic(a.mute ? "mute" : "vol")}</button><input type="range" min="0" max="100" value="${a.volume}" style="--v:${a.volume}%" data-range="volume" aria-label="Громкость"><span class="m">${a.mute ? "тихо" : a.volume + "%"}</span></div>` + R(hE(a.speaker || "Динамики"), "", "") + `<div class="r"><span class="sub">Микрофон</span><span class="vu" data-vu>${"<i></i>".repeat(18)}</span></div><div class="sub" title="${hE(a.mic)}">${hE(a.mic.split("(")[0] || "нет")}</div><div class="bs" style="margin-top:auto">${B("Говорить", "ui_listen", {}, "s p")}${B("Настройки звука", "settings", { page: "sound" }, "s")}</div>` : wait; },
    rows: () => [["Громкость", D.audio ? D.audio.volume + "%" : "—"], ["Звук", D.audio?.mute ? "выключен" : "включён"], ["Выход", D.audio?.speaker || "—"], ["Вход", D.audio?.mic || "—"], ["Джарвис", STATE_TEXT[STATUS] || "—"]],
    big: () => ({ v: D.audio?.mute ? "0" : D.audio?.volume ?? "—", u: "%", line: D.audio?.speaker || "", pct: D.audio?.mute ? 0 : D.audio?.volume || 0 }),
    act: () => B(ic("minus"), "vol_step", { d: -10 }, "sq", "Тише") + B(ic("plus"), "vol_step", { d: 10 }, "sq", "Громче") + B(ic("mute"), "mute", {}, "sq", "Выключить или включить звук"),
  }],
  ["battery", "Питание и батарея", {
    full: () => { const b = D.battery; return b ? `<div class="bigrow"><b class="${b.pct <= 20 && !b.plugged ? "bad" : ""}">${b.pct}%</b><span class="sub">${b.plugged ? "заряжается от сети" : b.left ? "хватит на " + hm(b.left / 60) : "от батареи"}</span></div>${bar(b.pct, b.pct <= 20 ? "bad" : b.pct <= 40 ? "warn" : "")}${spark(H.bat)}` + R("Экономия Prime", D.prime?.saver ? "включена" : "выключена") + `<div class="bs" style="margin-top:auto">${B("Питание Windows", "settings", { page: "power" }, "s")}</div>` : none("Батареи нет."); },
    rows: () => [["Заряд", D.battery ? D.battery.pct + "%" : "—"], ["Сеть", D.battery?.plugged ? "подключена" : "нет"], ["Осталось", D.battery?.left ? hm(D.battery.left / 60) : "—"], ["Без перезагрузки", hm(D.sys.uptime / 60)]],
    big: () => ({ v: D.battery?.pct ?? "—", u: "%", line: D.battery?.plugged ? "от сети" : D.battery?.left ? "ещё " + hm(D.battery.left / 60) : "от батареи", pct: D.battery?.pct || 0 }),
  }],
  ["screen", "Экраны и видео", {
    full: () => ((D.screens || []).map((s, i) => R(`Экран ${i + 1}${s.primary ? " · главный" : ""}`, `${s.w}×${s.h} · ${s.hz} Гц`)).join("") || wait) + (D.brightness != null ? `<div class="r"><span class="sub">Яркость</span><input type="range" min="5" max="100" value="${D.brightness}" style="--v:${D.brightness}%" data-range="brightness" aria-label="Яркость экрана"><span class="m">${D.brightness}%</span></div>` : '<div class="sub dim">Яркость этого экрана не управляется.</div>') + (D.gpu ? R(hE(D.gpu.name), `${(D.gpu.used / 1024).toFixed(1)} / ${(D.gpu.total / 1024).toFixed(0)} ГБ`) : "") + `<div class="bs" style="margin-top:auto">${B("Настройки экрана", "settings", { page: "display" }, "s")}</div>`,
    rows: () => [...(D.screens || []).map((s, i) => ["Экран " + (i + 1), `${s.w}×${s.h}@${s.hz}`]), ["Яркость", D.brightness != null ? D.brightness + "%" : "—"], ["GPU", D.gpu?.name || "—"], ["Видеопамять", D.gpu ? `${D.gpu.used} МБ` : "—"]],
    big: () => ({ v: D.brightness ?? (D.screens || []).length, u: D.brightness != null ? "%" : "экр.", line: (D.screens || []).map((s) => `${s.w}×${s.h}`).join(", ") + " · яркость", pct: D.brightness || 0 }),
    act: () => B(ic("minus"), "bri_step", { d: -15 }, "sq", "Темнее") + B(ic("plus"), "bri_step", { d: 15 }, "sq", "Ярче"),
  }],
  ["tv", "Samsung TV", {
    full() {
      const t = D.tv; if (!t) return wait;
      const k = (n, w, l) => `<button type="button" class="b" data-a="tv" data-v="${hE(JSON.stringify({ what: w }))}" aria-label="${l}" title="${l}">${n}</button>`;
      return `<div class="r">${dot(tvOn())}<span class="x">${tvOn() ? "Включён" : t.online ? "Ожидание" : "Не отвечает"}</span>${tvOn() ? B("Выключить", "tv", { what: "off" }, "s d") : B("Включить", "tv", { what: "on" }, "s p")}</div>`
        + `<div class="remote">${k("Vol −", "down", "Тише")}${k("Vol +", "up", "Громче")}${k("Ch −", "ch_down", "Канал вниз")}${k("Ch +", "ch_up", "Канал вверх")}${k(ic("left"), "left", "Курсор влево")}${k(ic("up"), "arrow_up", "Курсор вверх")}${k(ic("down"), "arrow_down", "Курсор вниз")}${k(ic("right"), "right", "Курсор вправо")}${k(ic("mute"), "mute", "Без звука")}${k(ic("home"), "home", "Домой")}${k(ic("back"), "back", "Назад")}${k("OK", "ok", "Выбрать")}${k(ic("play"), "play", "Играть")}${k(ic("pause"), "pause", "Пауза")}${k(ic("src"), "source", "Источник")}${k("YouTube", "youtube", "YouTube на телевизоре")}</div>`;
    },
    rows: () => [["Питание", tvOn() ? "ON" : "OFF"], ["Сеть", D.tv?.online ? "отвечает" : "нет"], ["Модель", D.tv?.model || "—"], ["Адрес", D.tv?.ip || "—"]],
    big: () => ({ v: tvOn() ? "Вкл" : "Выкл", u: "", line: D.tv?.model || (D.tv?.online ? "в режиме ожидания" : "не отвечает в сети"), pct: tvOn() ? 100 : D.tv?.online ? 15 : 0 }),
    act: () => (tvOn() ? B("Выкл", "tv", { what: "off" }, "d") + B("YouTube", "tv", { what: "youtube" }) : B("Включить", "tv", { what: "on" }, "p")),
  }],
  ["lan", "Сеть устройств", {
    full: () => (D.lan ? D.lan.map((d) => R(hE(d.name), d.ip, dot(true))).join("") : wait),
    rows: () => (D.lan || []).map((d) => [d.name, d.ip]),
    big: () => ({ v: (D.lan || []).length, u: "", line: "устройств видно в домашней сети", pct: clamp((D.lan || []).length * 10, 0, 100) }),
  }],
  ["light", "Умный свет", {
    full: () => `<div class="r">${dot(false)}<span class="x">Лампы не подключены</span></div><div class="sub">Нужен Home Assistant в домашней сети. Пока сцены меняют яркость экрана.</div><div class="bs f" style="margin-top:auto">${B("Ярко", "brightness", { level: 100 })}${B("Вечер", "brightness", { level: 45 })}${B("Ночь", "brightness", { level: 12 })}</div>`,
    rows: () => [["Лампы", "не подключены"], ["Сцена экрана", D.brightness == null ? "—" : D.brightness >= 80 ? "ярко" : D.brightness >= 30 ? "вечер" : "ночь"], ["Яркость", D.brightness != null ? D.brightness + "%" : "—"]],
    big: () => ({ v: D.brightness ?? "—", u: "%", line: "свет экрана · ламп нет", pct: D.brightness || 0 }),
    act: () => B("Ярко", "brightness", { level: 100 }) + B("Ночь", "brightness", { level: 12 }),
  }],
  ["bt", "Наушники BLE", {
    full: () => (D.bt ? D.bt.map((d) => `<div><div class="r">${dot(d.connected)}<span class="x">${hE(d.name)}</span><span class="m">${d.connected ? (d.battery ? d.battery + "%" : "подключены") : "не подключены"}</span></div>${d.battery ? bar(d.battery, d.battery <= 20 ? "bad" : "") : ""}</div>`).join("") || none("Сопряжённых устройств нет.") : wait) + `<div class="bs" style="margin-top:auto">${B("Bluetooth", "settings", { page: "bluetooth" }, "s")}</div>`,
    rows: () => (D.bt || []).map((d) => [d.name, d.connected ? (d.battery ? d.battery + "%" : "ON") : "OFF"]),
    big: () => { const h = btHead(); return { v: h?.battery ?? (h?.connected ? "Вкл" : "Нет"), u: h?.battery ? "%" : "", line: h ? h.name + (h.connected ? "" : " · не подключены") : "нет устройств", pct: h?.battery || (h?.connected ? 100 : 0) }; },
    act: () => B("Bluetooth", "settings", { page: "bluetooth" }),
  }],
  ["clock", "Часы и телефон", {
    full: () => `<div class="clock"><span data-clock></span><small data-sec></small></div><div class="sub">${new Date().toLocaleDateString("ru-RU", { weekday: "long", day: "numeric", month: "long" })}</div>` + R("Телефон через Telegram", D.bots?.telegram?.running ? "работает" : "выключен", dot(D.bots?.telegram?.running)) + R("Напоминаний", (D.reminders || []).length) + `<div class="bs" style="margin-top:auto">${B("Связь с телефоном", "settings", { page: "phone" }, "s")}${D.bots?.telegram?.running ? "" : B("Бот", "ui_keys", {}, "s")}</div>`,
    rows: () => [["Время", new Date().toLocaleTimeString("ru-RU")], ["Дата", new Date().toLocaleDateString("ru-RU")], ["Бот", D.bots?.telegram?.running ? "работает" : "выключен"], ["Напоминаний", (D.reminders || []).length]],
    big: () => { const n = new Date(); return { v: n.toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" }), u: "", line: n.toLocaleDateString("ru-RU", { weekday: "long", day: "numeric", month: "long" }), pct: (n.getHours() * 60 + n.getMinutes()) / 14.4 }; },
  }],
  ["weather", "Погода", {
    full: () => { const w = D.weather; return w && w.temp != null ? `<div class="bigrow"><b>${w.temp}°</b><span class="sub">${hE(w.city)} · ${hE(w.text)}</span></div><div class="wx">${w.days.map((d) => `<div>${new Date(d.date).toLocaleDateString("ru-RU", { weekday: "short" })}${ic(d.icon)}<b>${d.max}°</b>${d.min}°</div>`).join("")}</div><div class="sub">ветер ${w.wind} км/ч · влажность ${w.hum}%${w.rain != null ? ` · дождь ${w.rain}%` : ""}</div>` : none(w?.error || "Погода ещё не загрузилась."); },
    rows: () => { const w = D.weather || {}; return [["Город", w.city || "—"], ["Сейчас", w.temp != null ? w.temp + "°" : "—"], ["Небо", w.text || "—"], ["Ветер", w.wind != null ? w.wind + " км/ч" : "—"], ["Влажность", w.hum != null ? w.hum + "%" : "—"], ["Дождь", w.rain != null ? w.rain + "%" : "—"]]; },
    big: () => ({ v: D.weather?.temp ?? "—", u: "°", line: D.weather ? `${D.weather.city}, ${D.weather.text || ""}` : "", pct: D.weather?.rain || 0 }),
  }],
  ["brain", "Агент-мозг", {
    full: () => { const c = D.cloud || {}, on = (n) => (D.services || []).find((s) => s.name === n)?.on; return R("Groq · речь и ответы", c.groq ? "ключ есть" : "нет ключа", dot(c.groq)) + R("Gemini · зрение и инструменты", c.gemini ? "ключ есть" : "нет ключа", dot(c.gemini)) + R("Ollama · без интернета", on("Ollama") ? "работает" : "выключена", dot(on("Ollama"))) + R("Prime", D.prime?.on ? hE(D.prime.engine) : "не запущен", dot(D.prime?.on)) + R("Навыков", D.skills) + R("Уроков", D.learning?.lessons_learned ?? 0) + R("Повторных ошибок", D.learning ? D.learning.repeat_mistake_rate + "%" : "—") + R("Запросов к облаку", c.calls ?? 0) + (c.ms ? R("Последний ответ", c.ms + " мс") : "") + (c.error ? `<div class="sub bad wrap">${hE(c.error)}</div>` : ""); },
    rows: () => { const c = D.cloud || {}; return [["Groq", c.groq ? "OK" : "нет"], ["Gemini", c.gemini ? "OK" : "нет"], ["Prime", D.prime?.on ? D.prime.engine : "OFF"], ["Навыков", D.skills], ["Запросов", c.calls ?? 0], ["Ответ", c.ms ? c.ms + " мс" : "—"], ["Бюджет Prime", D.prime?.budget_left_usd != null ? "$" + D.prime.budget_left_usd : "—"]]; },
    big: () => { const c = D.cloud || {}, n = [c.groq, c.gemini, D.prime?.on, (D.services || []).find((s) => s.name === "Ollama")?.on].filter(Boolean).length; return { v: D.skills, u: "навыка", line: `движков готово: ${n} из 4`, pct: n / 4 * 100 }; },
  }],
  ["study", "Учёба N2 и поиск", {
    full() {
      const k = U.cards || D.cards || {}, c = k.card;
      if (k.off) return none("Prime не запущен: карточки хранятся в нём.");
      const f = U.addCard ? `<form data-f="card"><input type="text" name="q" placeholder="слово" aria-label="Слово"><input type="text" name="b" placeholder="чтение — перевод" aria-label="Перевод"><button class="b p">OK</button></form>` : "";
      if (!k.total) return none("Карточек пока нет.") + `<div class="bs">${B("Набор N2, 40 слов", "card_deck", {}, "p")}${B("Своя карточка", "ui_addcard")}</div>` + f;
      return `<div class="r"><span class="x sub">К повторению: <b class="acc">${k.due}</b> из ${k.total}</span>${B("+", "ui_addcard", {}, "s", "Своя карточка")}</div>` + (c ? `<button type="button" class="flash" data-a="ui_flip" data-v="{}" aria-label="Перевернуть карточку"><b>${hE(U.card ? c.back.split(" — ")[0] : c.front)}</b><span>${U.card ? hE(c.back.split(" — ")[1] || "") : "нажмите, чтобы проверить"}</span></button><div class="bs f">${B("Повторить", "card_review", { id: c.id, quality: 1 }, "d")}${B("Знаю", "card_review", { id: c.id, quality: 4 }, "p")}</div>` : none("На сегодня всё повторено.")) + f
        + (U.addCard ? "" : `<form data-f="note"><input type="search" name="q" value="${hE(U.note.q)}" placeholder="Найти в заметках" aria-label="Найти в заметках"><button class="b">Найти</button></form>`) + (U.note.items ? U.note.items.map((t) => `<div class="sub wrap">${hE(t)}</div>`).join("") || none("В заметках нет.") : "");
    },
    rows: () => { const k = U.cards || D.cards || {}; return [["Карточек", k.total ?? 0], ["К повторению", k.due ?? 0], ["Слово", k.card?.front || "—"], ["Интервал", k.card ? k.card.interval + " дн" : "—"], ["Заметок", D.notes ?? 0]]; },
    big: () => { const k = U.cards || D.cards || {}; return { v: k.card?.front || k.due || 0, u: "", line: k.total ? `к повторению ${k.due} из ${k.total}` : "карточек пока нет", pct: k.total ? (k.total - k.due) / k.total * 100 : 0 }; },
    act: () => { const c = (U.cards || D.cards || {}).card; return c ? B("Повторить", "card_review", { id: c.id, quality: 1 }) + B("Знаю", "card_review", { id: c.id, quality: 4 }, "p") : (U.cards || D.cards || {}).total ? "" : B("Набор N2", "card_deck", {}, "p"); },
  }],
  ["bots", "Боты Telegram и WA", {
    full: () => { const t = D.bots?.telegram || {}, w = D.bots?.whatsapp || {}; return D.bots ? R("Telegram" + (t.username ? " @" + hE(t.username) : ""), t.running ? "работает" : t.has_token ? "не работает" : "нет токена", dot(t.running)) + (t.error ? `<div class="sub bad wrap">${hE(t.error)}</div>` : !t.running && t.has_token ? '<div class="sub warn wrap">Telegram не принял токен. Вставьте новый в настройках.</div>' : "") + R("Владелец", t.owner ? "задан" : "не задан") + R("WhatsApp", w.enabled ? hE(w.state || "запуск") : "выключен", dot(w.state === "connected")) + `<div class="bs" style="margin-top:auto">${B("Токен Telegram", "ui_keys", {}, "s p")}${B("WhatsApp", "ui_conn", {}, "s")}</div>` : wait; },
    rows: () => { const t = D.bots?.telegram || {}, w = D.bots?.whatsapp || {}; return [["Telegram", t.running ? "ON" : "OFF"], ["Токен", t.has_token ? "сохранён" : "нет"], ["Владелец", t.owner ? "задан" : "нет"], ["WhatsApp", w.enabled ? w.state || "—" : "OFF"]]; },
    big: () => { const n = (D.bots?.telegram?.running ? 1 : 0) + (D.bots?.whatsapp?.state === "connected" ? 1 : 0); return { v: n, u: "/ 2", line: n ? "ботов работает" : "боты не работают", pct: n * 50 }; },
    act: () => B("Настроить", "ui_keys"),
  }],
  ["activity", "Активность и ключи", {
    full: () => { const a = D.activity || { apps: [] }, max = Math.max(1, ...a.apps.map((x) => x.min)), s = D.bots?.secrets || {}; return `<div class="r"><span class="x sub">Сегодня: <b class="acc">${hm(a.total || 0)}</b></span>${B(a.on ? "Не считать" : "Считать", "activity", { on: !a.on }, "s")}</div>` + a.apps.slice(0, 4).map((x) => `<div class="r"><span class="x">${hE(x.name)}</span>${bar(x.min / max * 100)}<span class="m">${x.min} мин</span></div>`).join("") + `<div class="r" style="margin-top:auto"><span class="x sub">Ключи в Windows</span>${Object.entries(s).map(([k, v]) => `<span class="m ${v ? "ok" : ""}">${k}</span>`).join("")}</div>`; },
    rows: () => [["Сегодня", hm(D.activity?.total || 0)], ...(D.activity?.apps || []).slice(0, 3).map((x) => [x.name, x.min + " мин"]), ...Object.entries(D.bots?.secrets || {}).map(([k, v]) => ["Ключ " + k, v ? "есть" : "нет"])],
    big: () => { const m = D.activity?.total || 0; return { v: m >= 60 ? (m / 60).toFixed(1) : m, u: m >= 60 ? "ч" : "мин", line: D.activity?.apps?.[0] ? "больше всего: " + D.activity.apps[0].name : "за компьютером сегодня", pct: clamp(m / 480 * 100, 0, 100) }; },
  }],
  ["history", "История команд", {
    full: () => hist().slice(0, 8).map((h) => `<div class="r"><span class="x" title="${hE(h.reply)}">${hE(h.user)}</span><span class="m">${hE(h.time.slice(11, 16))}</span>${B("↻", "ui_repeat", { text: h.user }, "s", "Повторить: " + h.user)}</div>`).join("") || none("Команд пока нет."),
    rows: () => hist().slice(0, 7).map((h) => [h.user, h.skill || h.engine || "—"]),
    big: () => { const n = hist().filter((h) => h.time.slice(0, 10) === hDay()).length, all = hist().length || 1; return { v: n, u: "", line: hist()[0] ? "последняя: " + hist()[0].user : "команд нет", pct: n / all * 100 }; },
  }],
  ["show", "Шоумен", {
    full: () => `<div class="sub wrap">Отчёт за месяц из ваших дел, целей и команд. Слайды, крупные субтитры и голос.</div><div class="bs">${[["ru", "Русский"], ["en", "English"], ["ja", "日本語"]].map(([k, n]) => `<button type="button" class="b ${U.lang === k ? "p" : ""}" data-a="ui_lang" data-v='{"lang":"${k}"}'>${n}</button>`).join("")}</div><div class="bs f" style="margin-top:auto">${B("Начать показ", "ui_stage", { mode: "deck" }, "p")}${B("Субтитры", "ui_stage", { mode: "live" })}</div>`,
    rows: () => [["Язык", U.lang], ["Дел закрыто", (D.tasks || []).filter((t) => t.done && String(t.done_at || "").slice(0, 7) === hDay().slice(0, 7)).length], ["Целей", (D.goals || []).length], ["Режим", "слайды, субтитры"]],
    big: () => ({ v: U.lang.toUpperCase(), u: "", line: "отчёт за месяц готов к показу", pct: new Date().getDate() / 30 * 100 }),
    act: () => B("Начать", "ui_stage", { mode: "deck" }, "p"),
  }],
].map(([id, title, f], i) => ({ id, title, n: String(i + 1).padStart(2, "0"), ...f }));
const WB = Object.fromEntries(W.map((w) => [w.id, w]));

/* ---------- drawing a widget ---------- */
function body(w, style) {
  if (!D) return wait;
  try {
    const act = w.act ? w.act() : "", acts = act ? `<div class="bs">${act}</div>` : "";
    if (style === "matrix") { const rows = w.rows(); return `<table class="mx"><tbody>${rows.map(([k, v]) => `<tr><td>${hE(k)}</td><td title="${hE(v)}">${hE(v)}</td></tr>`).join("") || '<tr><td>пусто</td><td>—</td></tr>'}</tbody></table>${acts}`; }
    if (style === "minimal") { const b = w.big(); return `<div class="mini"><b>${hE(b.v)}${b.u ? `<small>${hE(b.u)}</small>` : ""}</b><span>${hE(b.line)}</span></div>${acts}`; }
    if (style === "ring") { const b = w.big(), L = 2 * Math.PI * 44, p = clamp(b.pct || 0, 0, 100); return `<div class="gauge"><svg viewBox="0 0 110 110"><circle class="k" cx="55" cy="55" r="52"/><circle cx="55" cy="55" r="44"/>${p ? `<circle class="v" cx="55" cy="55" r="44" stroke-dasharray="${L}" stroke-dashoffset="${L * (1 - p / 100)}"/>` : ""}</svg><div><b>${hE(b.v)}</b><small>${hE(b.u || Math.round(p) + "%")}</small></div></div><div class="cap" title="${hE(b.line)}">${hE(b.line)}</div>${acts}`; }
    return w.full();
  } catch (e) { console.warn("widget", w.id, e); return none("Нет данных от этого источника."); }
}
const styleOf = (id) => (C.view === "core" && C.orbit ? (C.style[id] && C.style[id] !== "glass" ? C.style[id] : "minimal") : C.style[id] || "glass");
const BIG_DEFAULT = { calendar: "w", programs: "w", logs: "w", tv: "w", pc: "l", study: "w", net: "w" };
const sizeOf = (id) => C.size[id] || (C.tiles ? BIG_DEFAULT[id] || "" : "");
function card(id, zone) {
  const w = WB[id], el = document.createElement("article");
  el.className = "hx-w"; el.dataset.id = id; el.dataset.zone = zone; el.setAttribute("aria-label", w.title);
  el.innerHTML = `<div class="hx-h"><span class="n">[${w.n}]</span><span class="t" title="${hE(w.title)}">${hE(w.title)}</span><span class="tools"><select data-style aria-label="Вид виджета ${hE(w.title)}">${STYLES.map(([k, n]) => `<option value="${k}">${n}</option>`).join("")}</select><button type="button" class="hx-ib" data-a="ui_size" data-v='{"id":"${id}"}' aria-label="Размер" title="Размер">${ic("size")}</button><button type="button" class="hx-ib" data-a="ui_hide" data-v='{"id":"${id}"}' aria-label="Скрыть ${hE(w.title)}" title="Скрыть">${ic("x")}</button></span></div><div class="hx-c"></div>`;
  const head = el.firstChild;
  head.addEventListener("pointerdown", (e) => { el.draggable = C.dnd && !e.target.closest("select,button"); });
  return el;
}
let HOLD = null;                                         // a widget being used right now is not redrawn
function paint(el, force) {
  const id = el.dataset.id, st = styleOf(id), c = el.lastChild, sel = el.querySelector("select[data-style]");
  const cls = `hx-w st-${st} ${sizeOf(id) ? "s-" + sizeOf(id) : ""}`;
  if (el.dataset.cls !== cls) { el.className = cls; el.dataset.cls = cls; }
  if (document.activeElement !== sel) sel.value = st;
  const f = document.activeElement;
  if (!force && (HOLD === id || (f && c.contains(f) && /INPUT|TEXTAREA|SELECT/.test(f.tagName) && f.type !== "checkbox"))) return;
  const html = body(WB[id], st);
  if (el._h === html) return;
  const focusKey = f && c.contains(f) ? f.dataset.a + "|" + f.dataset.v : null, top = c.scrollTop;
  el._h = html; c.innerHTML = html; c.scrollTop = top;
  if (focusKey) [...c.querySelectorAll("[data-a]")].find((x) => x.dataset.a + "|" + x.dataset.v === focusKey)?.focus({ preventScroll: true });
  tick();
}
const matrixOrder = () => { const known = C.order.filter((i) => WB[i]); return [...known, ...W.map((w) => w.id).filter((i) => !known.includes(i))].filter((i) => !C.hidden[i]); };
function fill(box, ids, zone) {
  const have = new Map([...box.children].filter((x) => x.dataset.id).map((x) => [x.dataset.id, x]));
  [...have].forEach(([id, el]) => { if (!ids.includes(id)) el.remove(); });
  ids.forEach((id, i) => { const el = have.get(id) || card(id, zone), at = box.children[i]; if (at !== el) box.insertBefore(el, at || null); });
}
function layout() {
  document.body.dataset.hud = C.theme; applyPalette(); document.body.classList.toggle("dnd", C.dnd);
  const core = C.view === "core";
  hEl("hxCore").hidden = !core; hEl("hxMatrix").hidden = core; hEl("hxCore").style.display = core ? "" : "none"; hEl("hxMatrix").style.display = core ? "none" : "";
  hEl("hxCore").classList.toggle("orbit", C.orbit);
  if (core) { fill(hEl("hxL"), C.left.filter((i) => WB[i]), "left"); fill(hEl("hxR"), C.right.filter((i) => WB[i]), "right"); orbitPos(); }
  else { const m = hEl("hxMatrix"); m.dataset.fit = C.cols === "auto" ? "auto" : ""; m.style.setProperty("--cols", C.cols === "auto" ? 6 : C.cols); fill(m, matrixOrder(), "matrix"); }
  document.querySelectorAll("[data-view]").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.view === C.view)));
  hEl("hxCols").textContent = C.cols === "auto" ? "Сетка: авто" : `Сетка ${C.cols}×${Math.ceil(matrixOrder().length / C.cols)}`;
  hEl("hxCols").hidden = core;
  hEl("hxCols").style.display = core ? "none" : "";
  hEl("hxMCount").textContent = `Матрица · ${matrixOrder().length}`;
  hEl("hxDesign").textContent = "Стиль: " + THEMES.find(([k]) => k === C.theme)[1];
  paintAll(true); con(); fitAll();
}
function orbitPos() {
  const box = hEl("hxCore"), svg = hEl("hxLinks");
  if (!C.orbit) { svg.innerHTML = ""; box.querySelectorAll(".hx-w").forEach((e) => { e.style.display = ""; }); return; }
  const r = box.getBoundingClientRect(), all = [...box.querySelectorAll(".hx-w")], n = all.length; if (!r.width) return;
  const L = [...hEl("hxL").children], Rr = [...hEl("hxR").children], rx = r.width / 2 - 104, ry = (r.height / 2 - 60) / .883, cx = r.width / 2, cy = r.height / 2;
  let lines = `<ellipse cx="${cx}" cy="${cy}" rx="${rx}" ry="${ry}"/>`;
  const put = (all0, side) => all0.forEach((el, i) => {
    const els = all0.slice(0, 6); el.style.display = i < 6 ? "" : "none"; if (i >= 6) return;
    const k = els.length === 1 ? .5 : i / (els.length - 1), a = (-62 + 124 * k) * Math.PI / 180;
    const x = cx + side * Math.cos(a) * rx, y = cy + Math.sin(a) * ry;
    el.style.setProperty("--ox", x + "px"); el.style.setProperty("--oy", y + "px");
    lines += `<line x1="${cx}" y1="${cy}" x2="${x}" y2="${y}"/>`;
  });
  put(L, -1); put(Rr, 1);
  svg.setAttribute("viewBox", `0 0 ${r.width} ${r.height}`); svg.innerHTML = lines;
}
const paintAll = (force) => document.querySelectorAll(C.view === "core" ? "#hxCore .hx-w" : "#hxMatrix .hx-w").forEach((el) => paint(el, force));

/* ---------- actions ---------- */
async function act(kind, arg = {}) {
  let r;
  try { r = await (await fetch("/api/hud/action", { method: "POST", headers: { "Content-Type": "application/json", "X-Jarvis": "1" }, body: JSON.stringify({ ...arg, kind }) })).json(); }
  catch { toast("Джарвис не ответил"); return null; }
  if (r.reply) toast(r.reply);
  return r;
}
function ask(title, text, yes, html = "") {
  return new Promise((res) => {
    const d = hEl("hxDlg");
    d.innerHTML = `<h3>${hE(title)}</h3>${text ? `<p>${hE(text)}</p>` : ""}${html}<div class="bs"><button class="hx-b" value="no">Отмена</button>${yes ? `<button class="hx-b pri" value="yes">${hE(yes)}</button>` : ""}</div>`;
    d.querySelectorAll("button[value]").forEach((b) => { b.onclick = () => d.close(b.value); });
    d.onclose = () => res(d.returnValue === "yes"); d.returnValue = ""; d.showModal();
  });
}
const soon = (ms = 350) => setTimeout(() => poll(true), ms);
const UI = {
  ui_day: ({ day }) => { U.day = U.day === day ? null : day; paintAll(); },
  ui_flip: () => { U.card = !U.card; paintAll(); },
  ui_addcard: () => { U.addCard = !U.addCard; paintAll(); },
  ui_lang: ({ lang }) => { U.lang = lang; paintAll(); },
  ui_pin: ({ name }) => { C.pins = C.pins.includes(name) ? C.pins.filter((x) => x !== name) : [...C.pins, name]; save(); paintAll(); },
  ui_listen: () => api("/api/listen", "POST"),
  ui_keys: () => { location.hash = "#settings/keys"; },
  ui_conn: () => { location.hash = "#settings/connections"; },
  ui_repeat: ({ text }) => send(text),
  ui_stage: ({ mode }) => stage(mode),
  ui_size: ({ id }) => { const s = sizeOf(id); C.size[id] = s === "" ? "w" : s === "w" ? "l" : s === "l" ? "n" : ""; if (C.size[id] === "n" || C.size[id] === "") { if (C.tiles && BIG_DEFAULT[id]) C.size[id] = "n"; else delete C.size[id]; } save(); paintAll(true); },
  ui_hide: ({ id }, el) => { const c = el.closest(".hx-w"), z = c.dataset.zone; c.classList.add("bye"); setTimeout(() => { if (z === "matrix") C.hidden[id] = true; else C[z] = C[z].filter((x) => x !== id); save(); layout(); toast(`«${WB[id].title}» скрыт. Вернуть: кнопка «Виджеты»`); }, 220); },
  ui_index: async () => { if (await ask("Изучить имена файлов?", "Джарвис запишет имена и пути файлов на этом компьютере. Содержимое файлов он не читает. Данные остаются на ноутбуке.", "Изучить")) { const r = await api("/api/pc-index", "POST", { confirm: true }); toast(r.message || "Изучаю"); soon(); } },
  ui_doctor: () => wizardOpen(),
  vol_step: ({ d }) => act("volume", { level: clamp((D.audio?.volume ?? 30) + d, 0, 100) }).then(() => { if (D.audio) D.audio.volume = clamp(D.audio.volume + d, 0, 100); paintAll(); }),
  bri_step: ({ d }) => { const v = clamp((D.brightness ?? 50) + d, 5, 100); act("brightness", { level: v }).then(() => { D.brightness = v; paintAll(); }); },
  kill: async (a) => { if (await ask(`Завершить ${a.name}?`, "Несохранённая работа в этой программе пропадёт.", "Завершить")) { await act("kill", a); soon(900); } },
  close: async (a) => { await act("close", a); soon(1500); },
  open: async (a) => { await act("open", a); soon(2500); },
  card_review: async (a) => { const r = await act("card_review", a); U.card = false; if (r?.cards) U.cards = r.cards; paintAll(); },
  card_deck: async () => { const r = await act("card_deck"); if (r?.cards) U.cards = r.cards; paintAll(); },
  focus: async (a) => { focusTotal = (a.minutes || 0) * 60; await act("focus", a); poll(true); },
  brightness: async (a) => { await act("brightness", a); D.brightness = a.level; paintAll(); },
  tv: async (a) => { if (a.what === "on" || a.what === "off") toast(a.what === "on" ? "Включаю телевизор…" : "Выключаю телевизор…"); await act("tv", a); soon(1500); },
};
const FORMS = {
  task: async (f) => { await api("/api/tasks", "POST", { text: f.q }); toast("Дело добавлено"); },
  task_day: async (f) => { await api("/api/tasks", "POST", { text: f.q, due: U.day + "T09:00" }); toast("Дело добавлено на " + U.day); },
  goal: (f) => act("goal_add", { title: f.q }),
  find: async (f) => { const r = await act("find", { query: f.q }); U.find = { q: f.q, items: r?.items || [] }; },
  note: async (f) => { const r = await act("note_find", { query: f.q }); U.note = { q: f.q, items: r?.notes || [] }; },
  card: async (f) => { const r = await act("card_add", { front: f.q, back: f.b }); if (r?.cards) U.cards = r.cards; U.addCard = false; },
};

/* ---------- data ---------- */
let polling = null, firstShown = false;
const onHome = () => !hEl("page-home").hidden;
function push(k, v, n = 60) { if (v == null || Number.isNaN(v)) return; H[k].push(v); if (H[k].length > n) H[k].shift(); }
/** One request at a time. A call made while one is running starts a fresh request after it, so a change is seen at once. */
async function poll(fresh) {
  if (document.hidden || !onHome()) return;
  if (polling) { if (!fresh) return polling; await polling; }
  polling = load(); await polling; polling = null;
}
async function load() {
  try {
    const d = await (await fetch("/api/hud")).json();
    D = d; GAME = !!d.game?.on; U.cards = null;
    followShow(d.show);
    push("cpu", d.sys.cpu); push("ram", d.sys.ram_pct); push("gpu", d.gpu?.util); push("up", d.net.up); push("down", d.net.down); push("bat", d.battery?.pct, 240);
    paintAll(); telemetry();
    if (d.first_run && !firstShown) { firstShown = true; onbOpen(); }
  } catch { hEl("hxTel").innerHTML = '<span class="bad">нет связи с Джарвисом</span>'; }
}
function telemetry() {
  const c = D.cloud || {}, ol = (D.services || []).find((s) => s.name === "Ollama")?.on;
  hEl("hxMode").innerHTML = `<small>Hybrid</small><span><i class="${c.groq ? (c.error ? "bad" : "on") : ""}"></i>Groq</span><span><i class="${c.gemini ? "on" : ""}"></i>Gemini</span><span><i class="${ol ? "on" : ""}"></i>Ollama</span>`;
  const b = D.battery, n = (D.services || []).filter((s) => s.own && s.on).length;
  hEl("hxTel").innerHTML = `<span>${b ? (b.plugged ? "⚡ " : "") + `<b>${b.pct}%</b>` : ""}</span><span>пинг <b>${D.ping ?? "—"}</b></span><span>голос <b class="${D.voice_enrolled ? "ok" : "warn"}">${D.voice_enrolled ? "мой" : "любой"}</b></span><span>режим <b>${GAME ? "игра" : focusLeft() > 0 ? "фокус" : "обычный"}</b></span><span>службы <b>${n}/3</b></span>`;
}
function tick() {                                        // once a second, without redrawing widgets
  const n = new Date();
  document.querySelectorAll("[data-clock]").forEach((e) => { e.textContent = n.toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" }); });
  document.querySelectorAll("[data-sec]").forEach((e) => { e.textContent = String(n.getSeconds()).padStart(2, "0"); });
  document.querySelectorAll("[data-left]").forEach((e) => { const l = Number(e.dataset.left) - Date.now() / 1000; if (l > 0) e.textContent = dur(l); });
}

/* ---------- constructor ---------- */
function con() {
  const z = (id) => (C.left.includes(id) ? "left" : C.right.includes(id) ? "right" : "");
  hEl("conBody").innerHTML = `
    <label class="tg"><span>Виджеты на орбите<small>Компактно, кольцом вокруг круга, до 6 с каждой стороны</small></span><input type="checkbox" class="sw" data-c="orbit" ${C.orbit ? "checked" : ""}></label>
    <label class="tg"><span>Порядок и перетаскивание<small>Тяните виджет за заголовок</small></span><input type="checkbox" class="sw" data-c="dnd" ${C.dnd ? "checked" : ""}></label>
    <label class="tg"><span>Плитки<small>Важные виджеты крупнее остальных</small></span><input type="checkbox" class="sw" data-c="tiles" ${C.tiles ? "checked" : ""}></label>
    <h4>Тема</h4><div class="opts">${THEMES.map(([k, n]) => `<button type="button" class="hx-b" data-theme-k="${k}" aria-pressed="${C.theme === k}">${n}</button>`).join("")}</div>
    <h4>Цвет</h4><div class="sws">${PALETTES.map((p) => `<button type="button" style="background-color:${p.a}" data-acc="${p.id}" aria-label="${p.name}: ${p.sub}" title="${p.name}" aria-pressed="${C.accent === p.id}"></button>`).join("")}</div>
    <h4>Вид сразу для всех</h4><div class="opts">${STYLES.map(([k, n]) => `<button type="button" class="hx-b" data-all="${k}">${n}</button>`).join("")}</div>
    <h4>30 виджетов</h4><div class="hx-cap"><span></span><span></span><span>у круга</span><span>матр.</span></div>
    ${W.map((w) => `<div class="hx-row"><span class="n">${w.n}</span><span class="t" title="${hE(w.title)}">${hE(w.title)}</span><select data-zone-of="${w.id}" aria-label="${hE(w.title)}: место у круга"><option value="">нет</option><option value="left" ${z(w.id) === "left" ? "selected" : ""}>слева</option><option value="right" ${z(w.id) === "right" ? "selected" : ""}>справа</option></select><input type="checkbox" class="sw" data-vis="${w.id}" aria-label="${hE(w.title)} в матрице" ${C.hidden[w.id] ? "" : "checked"}></div>`).join("")}
    <h4>Раскладка</h4><div class="bs"><button type="button" class="hx-b" data-io="export">Экспорт</button><button type="button" class="hx-b" data-io="import">Импорт</button><button type="button" class="hx-b" data-io="reset">Сбросить порядок</button></div>`;
}
async function resetAll() {
  if (!await ask("Сбросить раскладку?", "Порядок, размеры, виды и тема вернутся к начальным. Дела, цели и карточки не изменятся.", "Сбросить")) return;
  const pins = C.pins; C = { ...DEF(), pins, view: C.view }; save(); layout(); toast("Раскладка сброшена");
}
function exportCfg() { const a = document.createElement("a"); a.href = URL.createObjectURL(new Blob([JSON.stringify(C, null, 1)], { type: "application/json" })); a.download = "jarvis-hud.json"; a.click(); setTimeout(() => URL.revokeObjectURL(a.href), 4000); }
function importCfg() {
  const i = document.createElement("input"); i.type = "file"; i.accept = ".json,application/json";
  i.onchange = async () => {
    try {
      const x = JSON.parse(await i.files[0].text()), ids = (a) => (Array.isArray(a) ? [...new Set(a)].filter((k) => WB[k]) : []);
      if (x.v !== 2) throw new Error();
      const only = (o, ok) => Object.fromEntries(Object.entries(o && typeof o === "object" ? o : {}).filter(([k, v]) => WB[k] && ok(v)));
      C = { ...DEF(), left: ids(x.left), right: ids(x.right).filter((k) => !ids(x.left).includes(k)), order: ids(x.order), hidden: only(x.hidden, (v) => v === true), style: only(x.style, (v) => STYLES.some(([k]) => k === v)), size: only(x.size, (v) => ["w", "l", "n"].includes(v)),
        pins: (Array.isArray(x.pins) ? x.pins : []).map(String).slice(0, 40), orbit: !!x.orbit, dnd: x.dnd !== false, tiles: !!x.tiles, view: x.view === "matrix" ? "matrix" : "core",
        theme: THEMES.some(([k]) => k === x.theme) ? x.theme : "cyber", accent: PALETTES.some((p) => p.id === x.accent) ? x.accent : (OLD_ACC[x.accent] || "arctic"), cols: ["6", "5", "4", "auto"].includes(x.cols) ? x.cols : "6" };
      save(); layout(); toast("Раскладка загружена");
    } catch { toast("Это не файл раскладки Джарвиса"); }
  };
  i.click();
}

/* ---------- events ---------- */
function bind() {
  const page = hEl("page-home");
  page.addEventListener("click", (e) => {
    const b = e.target.closest("[data-a]"); if (!b) return;
    const a = b.dataset.a, arg = JSON.parse(b.dataset.v || "{}");
    if (UI[a]) UI[a](arg, b); else act(a, arg).then(() => poll(true));
  });
  page.addEventListener("submit", async (e) => {
    const f = e.target.closest("form[data-f]"); if (!f) return; e.preventDefault();
    const v = Object.fromEntries([...new FormData(f)].map(([k, x]) => [k, String(x).trim()])); if (!v.q) return;
    document.activeElement?.blur?.();
    await FORMS[f.dataset.f](v); f.reset(); await poll(true); paintAll(true);
  });
  page.addEventListener("change", async (e) => {
    const t = e.target;
    if (t.matches("[data-style]")) { C.style[t.closest(".hx-w").dataset.id] = t.value; save(); t.blur(); paintAll(true); }
    else if (t.matches("[data-done]")) { await api("/api/tasks/" + t.dataset.done, "PATCH", { done: true }); toast("Отмечено выполненным"); poll(true); }
    else if (t.matches("[data-range]")) { const k = t.dataset.range, v = Number(t.value); HOLD = null; await act(k, { level: v }); if (k === "volume" && D.audio) { D.audio.volume = v; D.audio.mute = false; } if (k === "brightness") D.brightness = v; t.blur(); paintAll(); }
    else if (t.matches("[data-c]")) { C[t.dataset.c] = t.checked; save(); layout(); }
    else if (t.matches("[data-vis]")) { if (t.checked) delete C.hidden[t.dataset.vis]; else C.hidden[t.dataset.vis] = true; save(); layout(); }
    else if (t.matches("[data-zone-of]")) { const id = t.dataset.zoneOf; C.left = C.left.filter((x) => x !== id); C.right = C.right.filter((x) => x !== id); if (t.value) C[t.value].push(id); save(); layout(); }
  });
  page.addEventListener("input", (e) => { const t = e.target; if (t.matches("[data-range]")) { t.style.setProperty("--v", t.value + "%"); const m = t.nextElementSibling; if (m) m.textContent = t.value + "%"; } });
  page.addEventListener("pointerdown", (e) => { const w = e.target.closest(".hx-w"); if (w && e.target.closest(".hx-c")) HOLD = w.dataset.id; });
  addEventListener("pointerup", () => setTimeout(() => { HOLD = null; }, 60)); addEventListener("pointercancel", () => { HOLD = null; });
  /* drag and drop: inside a column, between columns, inside the matrix */
  let dragId = null, dragZone = null;
  const clear = () => page.querySelectorAll(".over").forEach((x) => x.classList.remove("over"));
  page.addEventListener("dragstart", (e) => { const w = e.target.closest?.(".hx-w"); if (!w || !C.dnd) return; dragId = w.dataset.id; dragZone = w.dataset.zone; e.dataTransfer.effectAllowed = "move"; e.dataTransfer.setData("text/plain", dragId); setTimeout(() => w.classList.add("drag"), 0); });
  page.addEventListener("dragend", (e) => { e.target.closest?.(".hx-w")?.classList.remove("drag"); if (e.target.closest?.(".hx-w")) e.target.closest(".hx-w").draggable = false; clear(); dragId = null; });
  page.addEventListener("dragover", (e) => { if (!dragId) return; const w = e.target.closest(".hx-w"), col = e.target.closest("#hxL,#hxR,#hxMatrix"); if (!w && !col) return; e.preventDefault(); clear(); if (w && w.dataset.id !== dragId) w.classList.add("over"); });
  page.addEventListener("drop", (e) => {
    if (!dragId) return; e.preventDefault(); clear();
    const w = e.target.closest(".hx-w"), col = e.target.closest("#hxL,#hxR,#hxMatrix"); if (!w && !col) return;
    const to = w ? w.dataset.zone : col.id === "hxL" ? "left" : col.id === "hxR" ? "right" : "matrix";
    if ((to === "matrix") !== (dragZone === "matrix")) return;
    const list = to === "matrix" ? matrixOrder() : C[to].slice(), from = list.indexOf(dragId), at = w ? list.indexOf(w.dataset.id) : list.length;
    if (w && w.dataset.id === dragId) return;
    if (from >= 0) list.splice(from, 1);
    list.splice(clamp(at, 0, list.length), 0, dragId);
    if (to === "matrix") C.order = [...list, ...W.map((x) => x.id).filter((i) => C.hidden[i])]; else { C.left = C.left.filter((x) => x !== dragId); C.right = C.right.filter((x) => x !== dragId); C[to] = list; }
    save(); layout();
  });
  /* header, constructor, dock */
  document.querySelectorAll("[data-view]").forEach((b) => { b.onclick = () => { C.view = b.dataset.view; save(); layout(); }; });
  hEl("hxCols").onclick = () => { const o = ["6", "5", "4", "auto"]; C.cols = o[(o.indexOf(C.cols) + 1) % 4]; save(); layout(); };
  hEl("hxDesign").onclick = () => { const i = THEMES.findIndex(([k]) => k === C.theme); C.theme = THEMES[(i + 1) % THEMES.length][0]; save(); layout(); };
  const tog = (open) => { hEl("hxCon").hidden = !open; hEl("hxWid").setAttribute("aria-pressed", String(open)); };
  hEl("hxWid").onclick = () => tog(hEl("hxCon").hidden);
  hEl("conClose").onclick = () => tog(false);
  hEl("hxReset").onclick = resetAll; hEl("hxImport").onclick = importCfg;
  hEl("hxCon").addEventListener("click", (e) => {
    const t = e.target.closest("button"); if (!t) return;
    if (t.dataset.themeK) { C.theme = t.dataset.themeK; save(); layout(); }
    else if (t.dataset.acc) { C.accent = t.dataset.acc; save(); layout(); }
    else if (t.dataset.all) { W.forEach((w) => { C.style[w.id] = t.dataset.all; }); save(); layout(); }
    else if (t.dataset.io) ({ export: exportCfg, import: importCfg, reset: resetAll })[t.dataset.io]();
  });
  page.addEventListener("click", async (e) => {
    const b = e.target.closest("[data-fb]"); if (!b) return;
    try {
      const r = await (await fetch("/api/feedback", { method: "POST", headers: { "Content-Type": "application/json", "X-Jarvis": "1" }, body: JSON.stringify({ rating: Number(b.dataset.fb) }) })).json();
      hEl("fbMsg").textContent = r.message || ""; setTimeout(() => { hEl("fbMsg").textContent = ""; }, 2500);
    } catch { hEl("fbMsg").textContent = "нет связи"; }
  });
  hEl("cmdForm").addEventListener("submit", async (e) => { e.preventDefault(); const t = hEl("cmd").value.trim(); if (!t) return; hEl("cmd").value = ""; await send(t); });
  hEl("mic").onclick = () => api("/api/listen", "POST");
  hEl("orb").onclick = () => api("/api/listen", "POST");
  hEl("orb").onkeydown = (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); api("/api/listen", "POST"); } };
  hEl("btnStage").onclick = () => stage("deck");
  addEventListener("resize", () => { fitAll(); orbitPos(); });
  addEventListener("hashchange", homeClass);
  document.addEventListener("visibilitychange", () => { if (!document.hidden) poll(); });
  addEventListener("keydown", (e) => { if (e.key === "Escape" && !hEl("hxCon").hidden && hEl("hxStage").hidden) tog(false); });
}
function homeClass() { const on = onHome(); document.body.classList.toggle("on-home", on); if (on) { fitAll(); orbitPos(); poll(); } }
async function send(text) {
  showExchange("user", text);
  const r = await api("/api/command", "POST", { text, speak: false });
  if (r && r.reply) showExchange("jarvis", r.reply);
  loadState(); poll(true);
}

/* ---------- stage: slides with voice, or live subtitles ---------- */
const ST = { mode: "deck", slides: [], i: 0, auto: null, voice: true, closedKey: "", voiceOpened: false };
/* the presentation said by voice: the screen opens it, follows the slide, and stays closed if the owner closed it */
function followShow(show) {
  if (!show || !show.active) {                       // ended by voice: close what the voice opened
    if (ST.voiceOpened && !hEl("hxStage").hidden) { stageStop(); hEl("hxStage").hidden = true; }
    ST.voiceOpened = false; ST.closedKey = "";
    return;
  }
  const key = show.lang + ":" + show.total;
  const stageOpen = !hEl("hxStage").hidden;
  if (!stageOpen) {
    if (ST.closedKey === key) return;
    U.lang = show.lang; ST.voiceOpened = true;
    stage("deck").then(() => { ST.i = show.i; stageDraw(); });
  } else if (ST.mode === "deck" && show.lang !== U.lang) {     // language changed by voice: rebuild the slides
    U.lang = show.lang;
    stage("deck").then(() => { ST.i = show.i; stageDraw(); });
  } else if (ST.mode === "deck" && show.i !== ST.i) {
    ST.i = show.i; stageDraw();
  }
}
async function stage(mode) {
  ST.mode = mode; ST.i = 0; stageStop(); hEl("hxStage").hidden = false;
  hEl("hxStage").requestFullscreen?.().catch(() => {});
  if (mode === "deck") { const r = await act("deck", { lang: U.lang }); ST.slides = r?.slides || []; }
  stageDraw();
}
function stageStop() { clearTimeout(ST.auto); ST.auto = null; }
function stageDraw() {
  const s = hEl("hxStage"), deck = ST.mode === "deck", x = ST.slides[ST.i] || {};
  s.classList.toggle("live", !deck);
  const last = HISTORY.slice().reverse().find((m) => m.role !== "user"), you = HISTORY.slice().reverse().find((m) => m.role === "user");
  hEl("stTi").textContent = deck ? x.title || "" : STATE_TEXT[STATUS] || "";
  hEl("stBg").textContent = deck ? x.big || "" : last?.text || "Говорите. Здесь появятся слова Джарвиса.";
  hEl("stSu").textContent = deck ? x.say || "" : you ? "Вы: " + you.text : "";
  hEl("stDots").innerHTML = deck ? ST.slides.map((_, i) => `<i class="${i <= ST.i ? "on" : ""}"></i>`).join("") : "";
  ["stPrev", "stNext", "stPlay", "stVoice"].forEach((k) => { hEl(k).style.display = deck ? "" : "none"; });
  hEl("stPlay").textContent = ST.auto ? "Пауза" : "Показ с голосом"; hEl("stVoice").setAttribute("aria-pressed", String(ST.voice));
  document.querySelectorAll("#hxStage [data-sl]").forEach((b) => { b.style.display = deck ? "" : "none"; b.setAttribute("aria-pressed", String(b.dataset.sl === U.lang)); });
  document.querySelectorAll("#hxStage [data-sm]").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.sm === ST.mode)));
}
function stageGo(d) { ST.i = clamp(ST.i + d, 0, ST.slides.length - 1); stageDraw(); }
function stagePlay() {
  const x = ST.slides[ST.i]; if (!x) return;
  if (ST.voice) api("/api/say", "POST", { text: x.say, lang: U.lang });
  ST.auto = setTimeout(() => { if (ST.i < ST.slides.length - 1) { stageGo(1); stagePlay(); } else { stageStop(); stageDraw(); } }, 3500 + x.say.length * (U.lang === "ja" ? 190 : 75));
  stageDraw();
}
function stageClose() {
  stageStop(); if (ST.mode === "deck") api("/api/stop", "POST");
  if (D && D.show && D.show.active) ST.closedKey = D.show.lang + ":" + D.show.total;
  hEl("hxStage").hidden = true; if (document.fullscreenElement) document.exitFullscreen();
}
function bindStage() {
  hEl("stPrev").onclick = () => { stageStop(); stageGo(-1); }; hEl("stNext").onclick = () => { stageStop(); stageGo(1); };
  hEl("stPlay").onclick = () => { if (ST.auto) { stageStop(); api("/api/stop", "POST"); stageDraw(); } else stagePlay(); };
  hEl("stVoice").onclick = () => { ST.voice = !ST.voice; stageDraw(); };
  hEl("stClose").onclick = stageClose;
  document.querySelectorAll("#hxStage [data-sl]").forEach((b) => { b.onclick = () => { U.lang = b.dataset.sl; stage("deck"); }; });
  document.querySelectorAll("#hxStage [data-sm]").forEach((b) => { b.onclick = () => stage(b.dataset.sm); });
  addEventListener("keydown", (e) => { if (hEl("hxStage").hidden) return; if (e.key === "ArrowRight") stageGo(1); if (e.key === "ArrowLeft") stageGo(-1); if (e.key === "Escape") stageClose(); });
}

/* ---------- the core ---------- */
const REDUCE = matchMedia("(prefers-reduced-motion: reduce)").matches;
/* Each palette has its own geometry on top of the shared core (the palette picks the shape, not only the colour) */
const GLOBE_DOTS = Array.from({ length: 260 }, (_, i) => {
  const y = 1 - (2 * (i + 0.5)) / 260, r = Math.sqrt(1 - y * y), th = i * 2.399963;
  return [r * Math.cos(th), y, r * Math.sin(th)];
});
function drawGlobeStyle(g, c, R0, s, A) {
  const id = palette(C.accent).id;
  if (id === "solar") {                                  // dotted globe: points on a sphere, turning
    const Rg = R0 * .505, ca = Math.cos(s * .22), sa = Math.sin(s * .22), tilt = .28, ct = Math.cos(tilt), st = Math.sin(tilt);
    for (const [x0, y0, z0] of GLOBE_DOTS) {
      const x1 = x0 * ca + z0 * sa, z1 = -x0 * sa + z0 * ca;               // turn around the vertical axis
      const y2 = y0 * ct - z1 * st, z2 = y0 * st + z1 * ct;                  // tilt
      const front = (z2 + 1) / 2, rad = (R0 * .0068) * (.55 + front);
      g.fillStyle = `rgba(${A},${.18 + front * .72})`;
      g.beginPath(); g.arc(c + x1 * Rg, c + y2 * Rg, rad, 0, 7); g.fill();
    }
  } else if (id === "emerald") {                         // grid: meridians and parallels plus a scan line
    const Rg = R0 * .52; g.lineWidth = Math.max(1, R0 / 380);
    for (let k = 0; k < 6; k++) {
      const a = k * Math.PI / 6 + s * .18;
      g.strokeStyle = `rgba(${A},${.13 + .1 * Math.cos(a)})`;
      g.beginPath(); g.ellipse(c, c, Rg * Math.abs(Math.cos(a)), Rg, 0, 0, 7); g.stroke();
    }
    for (let j = -2; j <= 2; j++) {
      const yy = c + Math.sin(j * .4) * Rg, rr = Math.cos(j * .4) * Rg;
      g.strokeStyle = `rgba(${A},.14)`; g.beginPath(); g.ellipse(c, yy, rr, rr * .18, 0, 0, 7); g.stroke();
    }
    const sy = c - Rg + ((s * .35) % 1) * 2 * Rg, half = Math.sqrt(Math.max(0, Rg * Rg - (sy - c) * (sy - c)));
    const scan = g.createLinearGradient(0, sy - 6, 0, sy + 6);
    scan.addColorStop(0, `rgba(${A},0)`); scan.addColorStop(.5, `rgba(${A},.55)`); scan.addColorStop(1, `rgba(${A},0)`);
    g.fillStyle = scan; g.fillRect(c - half, sy - 6, half * 2, 12);
  } else if (id === "crimson") {                         // shield: six segments with gaps, turning slowly
    const r = R0 * .605, gap = .16;
    for (let k = 0; k < 6; k++) {
      const a0 = k * Math.PI / 3 + s * .12 + gap / 2;
      g.strokeStyle = k % 2 ? `rgba(${A},.85)` : `rgba(255,170,0,.8)`;
      g.lineWidth = R0 * .012; g.lineCap = "butt";
      g.beginPath(); g.arc(c, c, r, a0, a0 + Math.PI / 3 - gap); g.stroke();
    }
    g.lineWidth = Math.max(1, R0 / 420); g.strokeStyle = `rgba(${A},.35)`;
    g.setLineDash([3, 6]); g.beginPath(); g.arc(c, c, R0 * .625, -s * .4, -s * .4 + Math.PI * 2 * .9); g.stroke(); g.setLineDash([]);
  } else if (id === "violet") {                          // orbits: three tilted rings with satellites
    for (let k = 0; k < 3; k++) {
      const tilt = k * Math.PI / 3 + .35, ra = R0 * (.66 + k * .03), rb = ra * (.36 + .1 * k);
      g.strokeStyle = `rgba(${A},.22)`; g.lineWidth = Math.max(1, R0 / 420);
      g.beginPath(); g.ellipse(c, c, ra, rb, tilt, 0, 7); g.stroke();
      const a = s * (.9 + k * .35) + k;
      const x = Math.cos(a) * ra, y = Math.sin(a) * rb;
      const px = c + x * Math.cos(tilt) - y * Math.sin(tilt), py = c + x * Math.sin(tilt) + y * Math.cos(tilt);
      g.fillStyle = k === 1 ? "rgba(245,158,11,.95)" : `rgba(${A},.95)`;
      g.beginPath(); g.arc(px, py, R0 * .014, 0, 7); g.fill();
    }
  }
}
const N = 160, noise = [...Array(N)].map((_, i) => .5 + .5 * Math.sin(i * 1.7) * Math.cos(i * .61));
let accRGB = "0,245,255", textCache = {};
function fit(c, cap = 1.5) { const d = Math.min(cap, devicePixelRatio || 1), r = c.getBoundingClientRect(); if (r.width && (c.width !== Math.round(r.width * d) || c.height !== Math.round(r.height * d))) { c.width = Math.round(r.width * d); c.height = Math.round(r.height * d); return true; } return false; }
function fitAll() { const o = hEl("orb"); if (!o) return; accRGB = getComputedStyle(document.body).getPropertyValue("--hx-a-rgb").trim() || accRGB; fit(o); if (fit(hEl("hudStars"), 1) || true) stars(); }
function stars() {
  const c = hEl("hudStars"); if (!c.width) return;
  const x = c.getContext("2d"); x.clearRect(0, 0, c.width, c.height);
  let s = 11; const rnd = () => (s = s * 16807 % 2147483647) / 2147483647;
  for (let i = 0; i < 170; i++) { x.fillStyle = `rgba(${rnd() > .8 ? "255,255,255" : accRGB},${.06 + rnd() * .34})`; x.beginPath(); x.arc(rnd() * c.width, rnd() * c.height, rnd() * 1.1 + .2, 0, 7); x.fill(); }
  const cx = c.width / 2, cy = c.height * .46; x.lineWidth = 1;
  [.34, .46, .6].forEach((k, i) => { x.strokeStyle = `rgba(${accRGB},${.07 - i * .015})`; x.beginPath(); x.ellipse(cx, cy, c.width * k, c.height * k * .8, -.08, 0, 7); x.stroke(); });
}
function arcText(g, text, cx, cy, r, a0, size) {
  g.font = `500 ${size}px "JetBrains Mono",monospace`; g.textAlign = "center"; g.textBaseline = "middle";
  const step = size * .86 / r;
  for (let i = 0; i < text.length; i++) { const a = a0 + i * step; g.save(); g.translate(cx + Math.cos(a) * r, cy + Math.sin(a) * r); g.rotate(a + Math.PI / 2); g.fillText(text[i], 0, 0); g.restore(); }
}
let lastFrame = 0;
function frame(t) {
  requestAnimationFrame(frame);
  if (document.hidden || !D && t < 300) return;
  const orb = hEl("orb");
  if (hEl("page-home").hidden || C.view !== "core" || !hEl("hxStage").hidden) return;
  const busy = STATUS !== "listening" && STATUS !== "starting" && STATUS !== "game" || LV > .12 || LV_T > .15;
  if (t - lastFrame < (GAME ? 480 : D?.lite ? 110 : busy ? 24 : 48)) return;
  lastFrame = t;
  const W0 = orb.width, g = orb.getContext("2d"); if (!W0) { fit(orb); return; }
  const c = W0 / 2, R0 = W0 / 2, s = REDUCE ? 0 : t / 1000, A = accRGB;
  const want = STATUS === "speaking" ? .42 + .28 * Math.abs(Math.sin(s * 7.3) * Math.sin(s * 3.1)) : STATUS === "thinking" ? .18 + .06 * Math.sin(s * 5) : STATUS === "recording" ? Math.max(.1, LV_T) : Math.min(.35, LV_T * .6);
  LV += (want - LV) * .18;
  g.clearRect(0, 0, W0, W0);
  const halo = g.createRadialGradient(c, c, R0 * .3, c, c, R0); halo.addColorStop(0, `rgba(${A},${.17 + LV * .25})`); halo.addColorStop(1, `rgba(${A},0)`);
  g.fillStyle = halo; g.fillRect(0, 0, W0, W0);
  // 1. circular waveform
  g.lineCap = "round"; g.lineWidth = Math.max(1, W0 / 420);
  for (let i = 0; i < N; i++) {
    const a = i / N * Math.PI * 2 - Math.PI / 2, k = noise[(i + Math.floor(s * 9)) % N] * .6 + noise[(i * 3 + Math.floor(s * 14)) % N] * .4;
    const len = R0 * (.012 + k * (.018 + LV * .11)), r1 = R0 * .87;
    g.strokeStyle = `rgba(${A},${.3 + k * .4 + LV * .3})`; g.beginPath(); g.moveTo(c + Math.cos(a) * r1, c + Math.sin(a) * r1); g.lineTo(c + Math.cos(a) * (r1 + len), c + Math.sin(a) * (r1 + len)); g.stroke();
  }
  // 2. ticks
  for (let i = 0; i < 72; i++) { const a = i / 72 * Math.PI * 2 + s * .05, big = i % 6 === 0; g.strokeStyle = `rgba(${A},${big ? .7 : .22})`; g.lineWidth = big ? 1.6 : 1; const r1 = R0 * .835, r2 = R0 * (big ? .805 : .82); g.beginPath(); g.moveTo(c + Math.cos(a) * r1, c + Math.sin(a) * r1); g.lineTo(c + Math.cos(a) * r2, c + Math.sin(a) * r2); g.stroke(); }
  // 3. rotating text
  const cl = D?.cloud || {}, good = D && !cl.error && D.sys.cpu < 92, txt = (D ? (cl.groq || cl.gemini ? "CLOUD HYBRID" : "LOCAL MODE") : "CONNECTING") + " · SYSTEM STATUS: " + (good ? "OPTIMAL" : D ? "ATTENTION" : "…");
  const sz = Math.max(8, R0 * .04); g.fillStyle = good ? `rgba(${A},.82)` : "rgba(255,176,32,.9)";
  arcText(g, txt, c, c, R0 * .752, s * .07 - 2.4, sz); arcText(g, txt, c, c, R0 * .752, s * .07 - 2.4 + Math.PI, sz);
  // 4. real load: CPU, RAM, GPU as three arcs
  const arcs = D ? [[D.sys.cpu, `rgb(${A})`, "CPU"], [D.sys.ram_pct, "#a78bff", "RAM"], [D.gpu ? D.gpu.util : 0, "#37e0a0", "GPU"]] : [];
  arcs.forEach(([v, col, nm], i) => {
    const a0 = -Math.PI / 2 + i * Math.PI * 2 / 3 + .12, span = Math.PI * 2 / 3 - .24, r = R0 * .672; g.lineWidth = R0 * .022; g.lineCap = "butt";
    g.strokeStyle = "rgba(255,255,255,.07)"; g.beginPath(); g.arc(c, c, r, a0, a0 + span); g.stroke();
    g.strokeStyle = col; g.beginPath(); g.arc(c, c, r, a0, a0 + span * clamp(v, 0, 100) / 100); g.stroke();
    g.fillStyle = "rgba(255,255,255,.85)"; arcText(g, nm + " " + Math.round(v) + "%", c, c, R0 * .625, a0 + .03, Math.max(9, R0 * .038));
  });
  // 5. metal ring
  const m = g.createConicGradient(s * .25, c, c); ["#1a222c", "#8fa2b5", "#202a35", "#0c1219", "#c9d7e4", "#1a222c"].forEach((q, i) => m.addColorStop(i / 5, q));
  g.strokeStyle = m; g.lineWidth = R0 * .03; g.beginPath(); g.arc(c, c, R0 * .565, 0, 7); g.stroke();
  g.strokeStyle = `rgba(${A},${.55 + LV * .4})`; g.lineWidth = 1.4; g.beginPath(); g.arc(c, c, R0 * .543, 0, 7); g.stroke();
  // 6. glass sphere with two sine waves
  const Rs = R0 * .53, ball = g.createRadialGradient(c - Rs * .35, c - Rs * .45, Rs * .05, c, c, Rs);
  ball.addColorStop(0, "#1c2b38"); ball.addColorStop(.45, "#0a121a"); ball.addColorStop(1, "#020407");
  g.save(); g.beginPath(); g.arc(c, c, Rs, 0, 7); g.clip(); g.fillStyle = ball; g.fillRect(c - Rs, c - Rs, Rs * 2, Rs * 2);
  const low = g.createRadialGradient(c, c + Rs * .9, 0, c, c + Rs * .9, Rs * 1.1); low.addColorStop(0, `rgba(${A},${.26 + LV * .35})`); low.addColorStop(1, `rgba(${A},0)`); g.fillStyle = low; g.fillRect(c - Rs, c - Rs, Rs * 2, Rs * 2);
  [[`rgba(${A},.95)`, 2.1, 1.6, 0], ["rgba(167,139,255,.75)", 2.9, -1.2, 1.4]].forEach(([col, fr, sp, ph]) => {
    g.strokeStyle = col; g.lineWidth = Math.max(1.3, R0 * .0075); g.beginPath();
    for (let x = -1; x <= 1.001; x += .03) { const y = Math.sin(x * Math.PI * fr + s * sp * 2 + ph) * Rs * (.05 + LV * .34) * Math.cos(x * Math.PI / 2); const px = c + x * Rs, py = c + Rs * .44 + y; x === -1 ? g.moveTo(px, py) : g.lineTo(px, py); }
    g.stroke();
  });
  g.save(); g.translate(c - Rs * .12, c - Rs * .78); g.scale(1, .46); const hi = g.createRadialGradient(0, 0, 0, 0, 0, Rs * .8); hi.addColorStop(0, "rgba(225,248,255,.3)"); hi.addColorStop(.6, "rgba(225,248,255,.07)"); hi.addColorStop(1, "rgba(225,248,255,0)"); g.fillStyle = hi; g.fillRect(-Rs, -Rs, Rs * 2, Rs * 2); g.restore();
  const rim = g.createRadialGradient(c, c, Rs * .86, c, c, Rs); rim.addColorStop(0, `rgba(${A},0)`); rim.addColorStop(1, `rgba(${A},.22)`); g.fillStyle = rim; g.fillRect(c - Rs, c - Rs, Rs * 2, Rs * 2);
  g.restore();
  if (!D?.lite) drawGlobeStyle(g, c, R0, s, A);
  // microphone bars in the sound widget
  const vu = document.querySelectorAll("[data-vu]"); vu.forEach((v) => [...v.children].forEach((b, i) => b.classList.toggle("on", LV_T * 18 > i)));
}

/* ---------- used by the rest of the page ---------- */
const STATE_TEXT = { starting: "Запуск", listening: "Жду «Джарвис»", recording: "Слушаю", thinking: "Думаю", speaking: "Говорю", taping: "Идёт запись", game: "Игровой режим" };
function setStatus(s) {
  STATUS = s || STATUS;
  hEl("stateTxt").textContent = GAME && STATUS === "listening" ? STATE_TEXT.game : STATE_TEXT[STATUS] || STATE_TEXT.listening;
  const m = hEl("mic"); m.classList.toggle("recording", STATUS === "recording"); m.setAttribute("aria-pressed", String(STATUS === "recording"));
  if (!hEl("hxStage").hidden && ST.mode === "live") stageDraw();
}
function showExchange(role, text) {
  if (role === "user") hEl("you").textContent = "Вы: " + text; else hEl("him").textContent = text;
  if (!hEl("hxStage").hidden && ST.mode === "live") setTimeout(stageDraw, 0);
}
let homeT = null;
function renderHome() { clearTimeout(homeT); homeT = setTimeout(() => poll(true), 400); }
function hudStart() {
  bind(); bindStage(); wizardBind(); layout(); homeClass();
  requestAnimationFrame(frame);
  setInterval(tick, 1000);
  let n = 0; setInterval(() => { n++; if (!GAME || n % 4 === 0) poll(); }, 2500);
}
