/* Jarvis — the other pages: tasks, goals, commands, memory, presentation, appearance, settings, first run, analysis. */
(function () {
  "use strict";
  const { $, $$, esc, api, toast, ask, dialog, clone, PREFS, savePrefs, applyLook, STATE, palette, PALETTES, LOOKS, DENSITY, PRESETS, DEFAULT_PREFS, svg, num, dmy, hm, plural, hudAct, pollHud, pollSlow, route, renderDashboardShell } = JV;

  /* small builders */
  const kvr = (k, v) => `<div class="item"><span class="grow">${esc(k)}</span><b>${v}</b></div>`;
  const row = (label, hint, control) => `<div class="setting"><div class="lbl-wrap"><b>${esc(label)}</b>${hint ? `<small>${hint}</small>` : ""}</div><div class="ctrl">${control}</div></div>`;
  const sw = (section, key, on, label) => `<label class="switch"><input type="checkbox" data-set="${section}|${key}|bool" ${on ? "checked" : ""} aria-label="${esc(label)}"><span></span></label>`;
  const seg = (items, value, attrs) => `<div class="seg" role="group">${items.map(([k, n]) => `<button type="button" aria-pressed="${value === k}" ${attrs}="${k}">${esc(n)}</button>`).join("")}</div>`;
  const section = (id, title, desc, body) => `<section class="section" id="${id}" aria-labelledby="${id}-h"><header><h2 id="${id}-h">${esc(title)}</h2>${desc ? `<p>${desc}</p>` : ""}</header>${body}</section>`;
  const panel = (title, desc, body, extra = "") => `<div class="panel"><div class="panel-h"><div><h3>${esc(title)}</h3>${desc ? `<p>${desc}</p>` : ""}</div>${extra}</div>${body}</div>`;
  const callout = (kind, title, text) => `<div class="callout ${kind}">${svg(kind === "warn" ? "shield" : "gear", "")}<div><b>${esc(title)}</b>${text}</div></div>`;
  const busy = async (b, fn) => { b.disabled = true; try { return await fn(); } finally { b.disabled = false; } };

  /* a generic setting writer: every <input data-set="section|key|type"> saves itself */
  document.addEventListener("change", async (e) => {
    const t = e.target;
    if (!t.dataset.set) return;
    const [section, key, type] = t.dataset.set.split("|");
    let value = t.type === "checkbox" ? t.checked : t.value;
    if (type === "num") value = Number(value);
    try { await api("/api/settings", "POST", { section, key, value }); toast("Сохранено"); pollSlow(); }
    catch (err) { toast("Не сохранилось: " + err.message); }
  });
  document.addEventListener("input", (e) => { const t = e.target; if (t.type === "range" && t.dataset.set) t.style.setProperty("--v", t.value + "%"); });

  /* ---------- Tasks ---------- */
  const TASKS = {
    title: "Дела", sub: "Что нужно сделать. Срок — по желанию, напомню заранее.",
    render(el) { draw(el); },
    onData(_, force) { if (force || STATE.live === "tasks") draw($("#view")); },
  };
  function draw(el) {
    const st = STATE.state || {};
    const open = (st.tasks || []).filter((t) => !t.done).sort((a, b) => (a.due || "9").localeCompare(b.due || "9"));
    const done = (st.tasks || []).filter((t) => t.done).slice(-8).reverse();
    const rem = (st.reminders || []);
    el.innerHTML = `<div class="grid-2" style="grid-template-columns:minmax(0,1.4fr) minmax(0,1fr)">
      ${panel("Открытые дела", `${open.length} ${plural(open.length, "дело", "дела", "дел")} в работе`, `
        <form class="form-row" id="taskForm" style="margin-bottom:12px">
          <div class="field grow"><label for="taskText">Новое дело</label><input id="taskText" type="text" maxlength="160" placeholder="Например: позвонить маме"></div>
          <div class="field" style="flex:0 1 190px"><label for="taskDue">Срок (необязательно)</label><input id="taskDue" type="datetime-local"></div>
          <button class="btn primary" type="submit">Добавить</button>
        </form>
        <div class="list">${open.map((t) => `<div class="task-row">
            <input class="check" type="checkbox" data-done="${esc(t.id)}" aria-label="Сделано: ${esc(t.text)}">
            <div><div class="t">${esc(t.text)}</div>${t.due ? `<div class="due ${new Date(t.due) < new Date() ? "over" : ""}">${new Date(t.due) < new Date() ? "просрочено · " : ""}${dmy(t.due)}</div>` : ""}</div>
            <button class="btn sm icon ghost" data-del="${esc(t.id)}" aria-label="Удалить дело">${svg("x")}</button></div>`).join("") || `<div class="empty"><b>Дел нет</b>Добавьте первое или скажите «Джарвис, добавь дело …»</div>`}</div>`)}
      <div class="stack">
        ${panel("Напоминания", "Скажите «Джарвис, напомни через 10 минут …»", `<div class="list">${rem.map((r, i) => `<div class="item"><div class="grow"><div class="t">${esc(r.text)}</div><div class="m">${dmy(r.at)}</div></div><button class="btn sm ghost" data-delrem="${i}">Удалить</button></div>`).join("") || `<div class="empty">Напоминаний нет</div>`}</div>`)}
        ${panel("Сделано недавно", "", `<div class="list">${done.map((t) => `<div class="item"><span class="grow ellipsis muted">${esc(t.text)}</span><span class="faint small">${dmy(t.done_at)}</span></div>`).join("") || `<div class="empty">Пока пусто</div>`}</div>`)}
      </div></div>`;
    el.querySelector("#taskForm").addEventListener("submit", async (e) => {
      e.preventDefault();
      const text = $("#taskText").value.trim(), due = $("#taskDue").value;
      if (!text) return;
      try { await api("/api/tasks", "POST", { text, due: due ? due + ":00" : null }); toast("Дело добавлено"); await pollSlow(); draw(el); }
      catch (err) { toast(err.message); }
    });
    el.querySelectorAll("[data-done]").forEach((c) => c.addEventListener("change", async () => { await api(`/api/tasks/${c.dataset.done}`, "PATCH", { done: true }); toast("Отмечено"); await pollSlow(); draw(el); }));
    el.querySelectorAll("[data-del]").forEach((b) => b.addEventListener("click", async () => { if (await ask({ title: "Удалить дело?", text: "Дело пропадёт из списка.", yes: "Удалить", danger: true })) { await api(`/api/tasks/${b.dataset.del}`, "DELETE"); await pollSlow(); draw(el); } }));
    el.querySelectorAll("[data-delrem]").forEach((b) => b.addEventListener("click", async () => { await api(`/api/reminders/${b.dataset.delrem}`, "DELETE"); await pollSlow(); draw(el); }));
  }

  /* ---------- Goals ---------- */
  const GOALS = {
    title: "Цели", sub: "Маленькие шаги каждый день. Джарвис напомнит утром и вечером.",
    async render(el) { await draw(el); },
    onData(_, force) { if (force && STATE.live === "goals") draw($("#view")); },
  };
  async function draw(el) {
    let g = { goals: [], limits: [], usage: {} };
    try { g = await api("/api/goals"); } catch (e) { toast(e.message); }
    const goals = g.goals || [];
    el.innerHTML = `<div class="grid-2" style="grid-template-columns:minmax(0,1.3fr) minmax(0,1fr)">
      ${panel("Мои цели", "Отмечайте шаги кнопкой «+1» или голосом: «сделал шаг по цели …»", `
        <form class="form-row" id="goalForm" style="margin-bottom:12px">
          <div class="field grow"><label for="gTitle">Цель</label><input id="gTitle" type="text" maxlength="120" placeholder="Например: выучить японский"></div>
          <div class="field" style="flex:0 0 110px"><label for="gStep">Шаг в день</label><input id="gStep" type="number" min="1" max="999" placeholder="50"></div>
          <button class="btn primary" type="submit">Добавить</button></form>
        <div class="list">${goals.map((x) => {
          const today = Number((x.log || {})[ymd()] || 0), per = x.per_day || 0, p = per ? Math.min(100, Math.round(100 * today / per)) : today ? 100 : 0;
          return `<div class="goal"><div class="between"><b>${esc(x.title)}</b><span class="row"><button class="btn sm" data-tick="${esc(x.id)}">+1 шаг</button><button class="btn sm icon ghost" data-gdel="${esc(x.id)}" aria-label="Удалить цель">${svg("x")}</button></span></div>
            <div class="bar ${p >= 100 ? "ok" : ""}"><i style="width:${p}%"></i></div><div class="sub">сегодня ${today}${per ? ` из ${per}` : ""}</div></div>`;
        }).join("") || `<div class="empty"><b>Целей пока нет</b>Например: «Японский, 50 слов в день»</div>`}</div>`)}
      ${panel("Лимиты времени", "Джарвис предупредит за 5 минут до конца и попросит закрыть программу", `
        <form class="form-row" id="limitForm" style="margin-bottom:12px">
          <div class="field grow"><label for="lApp">Программа</label><input id="lApp" type="text" placeholder="YouTube, Steam…"></div>
          <div class="field" style="flex:0 0 110px"><label for="lMin">Минут в день</label><input id="lMin" type="number" min="5" placeholder="60"></div>
          <button class="btn primary" type="submit">Ограничить</button></form>
        <div class="list">${(g.limits || []).map((x) => { const used = ((g.usage || {})[x.app] || 0) / 60, p = Math.min(100, Math.round(100 * used / x.minutes)); return `<div class="goal"><div class="between"><b>${esc(x.app)}</b><span class="faint small">${Math.round(used)} из ${x.minutes} мин</span></div><div class="bar ${p >= 100 ? "bad" : p >= 80 ? "warn" : ""}"><i style="width:${p}%"></i></div></div>`; }).join("") || `<div class="empty"><b>Ограничений нет</b>Например: «YouTube, 60 минут»</div>`}</div>`)}</div>`;
    el.querySelector("#goalForm").addEventListener("submit", async (e) => {
      e.preventDefault(); const t = $("#gTitle").value.trim(), n = $("#gStep").value;
      if (!t) return;
      await hudAct("goal_add", { title: t, per_day: n ? Number(n) : null }); await draw(el);
    });
    el.querySelector("#limitForm").addEventListener("submit", async (e) => {
      e.preventDefault(); const a = $("#lApp").value.trim(), m = $("#lMin").value || "60";
      if (!a) return;
      await api("/api/command", "POST", { text: `ограничь ${a} ${m} минут в день` }); toast("Ограничение добавлено"); await draw(el);
    });
    el.querySelectorAll("[data-tick]").forEach((b) => b.addEventListener("click", async () => { await hudAct("goal_mark", { id: b.dataset.tick }); await draw(el); pollHud(); }));
    el.querySelectorAll("[data-gdel]").forEach((b) => b.addEventListener("click", async () => { if (await ask({ title: "Удалить цель?", text: "Вся история шагов по этой цели пропадёт.", yes: "Удалить", danger: true })) { await hudAct("goal_delete", { id: b.dataset.gdel }); await draw(el); } }));
  }
  const ymd = (d = new Date()) => d.toLocaleDateString("sv-SE");

  /* ---------- Commands ---------- */
  const COMMANDS = {
    title: "Команды", sub: "Цепочки из нескольких команд запускаются одной фразой или кнопкой.",
    async render(el, sub) { await draw(el, sub || "macros"); },
    onData(_, force) { if (force && STATE.live === "commands") draw($("#view"), "history"); },
  };
  async function draw(el, tab) {
    let macros = STATE.macros || { items: [] };
    try { macros = await api("/api/macros"); STATE.macros = macros; } catch { /* keep the last list */ }
    const hist = (STATE.state?.history || []).slice().reverse();
    el.innerHTML = `<div class="dash-toolbar"><div class="seg" role="tablist"><button type="button" role="tab" data-tab="macros" aria-pressed="${tab === "macros"}">Цепочки</button><button type="button" role="tab" data-tab="history" aria-pressed="${tab === "history"}">История</button></div><span class="spacer"></span><form class="form-row" id="cmdForm" style="flex:0 1 420px"><input type="search" id="cmdIn" placeholder="Быстро: напишите команду Джарвису" aria-label="Команда" style="height:36px"><button class="btn" type="submit">Отправить</button></form></div>
      ${tab === "macros" ? `<div class="grid-2"><div class="stack">${(macros.items || []).map((m) => `<div class="cmd-card"><div class="grow"><b style="font-size:15px">«${esc(m.phrase)}»</b><p>${(m.actions || []).map((a) => esc(a.value)).join(" → ")}</p></div><button class="btn primary" data-run="${esc(m.id)}">Запустить</button><button class="btn sm icon ghost" data-mdel="${esc(m.id)}" aria-label="Удалить">${svg("x")}</button></div>`).join("") || `<div class="empty"><b>Цепочек пока нет</b>Создайте справа или скажите «Джарвис, запомни команду …»</div>`}</div>
        ${panel("Новая цепочка", "Одна команда в строке. Например: «открой ютуб», «громкость 30», «напомни через 25 минут перерыв»", `<form id="macroForm" class="col"><div class="field"><label for="mPhrase">Фраза для запуска</label><input id="mPhrase" type="text" maxlength="60" placeholder="например: вечер дома" required></div><div class="field"><label for="mSteps">Команды</label><textarea id="mSteps" rows="5" placeholder="включи фокус на 25 минут&#10;включи музыку для работы" required></textarea></div><div><button class="btn primary" type="submit">Сохранить цепочку</button></div></form>`)}</div>`
      : `<div class="panel"><div class="list">${hist.map((h) => `<div class="hist-item"><div class="meta"><span>${esc(h.time || "")}</span><span class="chip">${esc(h.skill || h.tools || "ответ")}</span></div><div class="q">${esc(h.user || "")}</div><div class="a">${esc(h.reply || "")}</div><div class="row" style="gap:6px"><button class="btn sm ghost" data-again="${esc(h.user || "")}">Повторить</button></div></div>`).join("") || `<div class="empty"><b>История пуста</b>Здесь появится каждая команда и ответ</div>`}</div></div>`}`;
    el.querySelectorAll("[data-tab]").forEach((b) => b.addEventListener("click", () => draw(el, b.dataset.tab)));
    el.querySelector("#cmdForm").addEventListener("submit", async (e) => { e.preventDefault(); const t = $("#cmdIn").value.trim(); if (!t) return; $("#cmdIn").value = ""; await JV.sendText(t); toast("Отправлено"); draw(el, tab); });
    el.querySelectorAll("[data-run]").forEach((b) => b.addEventListener("click", async () => { await api(`/api/macros/${b.dataset.run}/run`, "POST"); toast("Запускаю"); }));
    el.querySelectorAll("[data-mdel]").forEach((b) => b.addEventListener("click", async () => { if (await ask({ title: "Удалить цепочку?", yes: "Удалить", danger: true })) { await api(`/api/macros/${b.dataset.mdel}`, "DELETE"); draw(el, tab); } }));
    el.querySelectorAll("[data-again]").forEach((b) => b.addEventListener("click", () => JV.sendText(b.dataset.again)));
    const mf = el.querySelector("#macroForm");
    if (mf) mf.addEventListener("submit", async (e) => {
      e.preventDefault();
      const phrase = $("#mPhrase").value.trim(), lines = $("#mSteps").value.split("\n").map((s) => s.trim()).filter(Boolean);
      if (!phrase || !lines.length) return;
      try { await api("/api/macros", "POST", { phrase, actions: lines.map((value) => ({ type: "command", value })) }); toast("Цепочка сохранена"); draw(el, "macros"); }
      catch (err) { toast(err.message); }
    });
  }

  /* ---------- Memory ---------- */
  const MEMORY = {
    title: "Память", sub: "Что Джарвис помнит о вас, чему научился на поправках и что знает из ваших документов.",
    async render(el) { await draw(el); },
  };
  async function draw(el) {
    const [facts, metrics, docs, shield] = await Promise.all([api("/api/memory/facts").catch(() => ({ facts: [], habits: [] })), api("/api/learning/metrics").catch(() => ({})), api("/api/docs").catch(() => ({})), api("/api/shield").catch(() => null)]);
    const st = (STATE.hud || {}).stage || {};
    el.innerHTML = `<div class="grid-2">
      ${panel("Что Джарвис знает о вас", "Факты добавляются здесь или фразой «запомни факт: …». Их можно удалить.", `
        <form class="form-row" id="factForm" style="margin-bottom:10px"><div class="field grow"><label for="factIn">Новый факт</label><input id="factIn" type="text" maxlength="300" placeholder="Например: я работаю программистом"></div><button class="btn primary" type="submit">Запомнить</button></form>
        <div class="list">${(facts.facts || []).map((f) => `<div class="item"><span class="grow">${esc(f.text)}</span><button class="btn sm ghost" data-fdel="${f.id}">Забыть</button></div>`).join("") || `<div class="empty">Пока ничего. Добавьте первый факт.</div>`}</div>
        ${(facts.habits || []).length ? `<h4 style="margin-top:14px">Частые команды</h4><div class="pills" style="margin-top:8px">${facts.habits.slice(0, 6).map((h) => `<span class="chip">${esc(h.phrase)} · ${h.hits}</span>`).join("")}</div>` : ""}`)}
      <div class="stack">
        ${panel("Отношения и обучение", "Стадия растёт от числа разговоров и от ваших оценок 👍 и 👎.", `
          <div class="stat">${esc(st.stage || "знакомые")}</div>
          <div class="sub" style="margin:8px 0 12px">${num(st.exchanges ?? 0)} разговоров · ${num(st.days ?? 0)} дн.</div>
          <div class="grid-3" style="gap:8px">${[["Поправок", metrics.corrections_detected], ["Уроков", metrics.lessons_learned], ["Повторов", (metrics.repeat_mistake_rate ?? 0) + "%"]].map(([k, v]) => `<div class="panel" style="padding:12px;text-align:center"><div class="stat" style="font-size:22px">${typeof v === "string" ? v : num(v)}</div><div class="sub">${k}</div></div>`).join("")}</div>
          <div class="foot" style="margin-top:12px"><button class="btn" id="btnReflect">Разобрать поправки за день</button></div>`)}
        ${panel("Документы", docs.built ? `Файлов в индексе: ${num(docs.files)}` : "Документы ещё не изучены. Изучаются только Документы, рабочий стол и Загрузки.", `<div class="foot"><button class="btn primary" id="btnDocs">${docs.built ? "Обновить индекс" : "Изучить документы"}</button></div>
          <form class="form-row" id="docForm" style="margin-top:10px"><div class="field grow"><label for="docIn">Поиск по документам</label><input id="docIn" type="search" placeholder="Например: отчёт по выручке"></div><button class="btn" type="submit">Найти</button></form><div id="docOut" style="margin-top:10px"></div>`)}
        ${panel("Безопасность сети", "", shield ? `${kvr("Слушающих портов", num(shield.ports.listening.length))}${kvr("Внешних подключений", num(shield.ports.remote.length))}${kvr("Необычных открытых", (shield.ports.unusual || []).length ? `<span class="warn">${shield.ports.unusual.length}</span>` : "нет")}${kvr("VPN", shield.vpn.on ? "включён" : "выключен")}` : `<div class="empty">Проверяю…</div>`)}
      </div></div>`;
    el.querySelector("#factForm").addEventListener("submit", async (e) => { e.preventDefault(); const t = $("#factIn").value.trim(); if (!t) return; try { await api("/api/memory/facts", "POST", { text: t }); toast("Запомнил"); draw(el); } catch (err) { toast(err.message); } });
    el.querySelectorAll("[data-fdel]").forEach((b) => b.addEventListener("click", async () => { await api(`/api/memory/facts/${b.dataset.fdel}`, "DELETE"); draw(el); }));
    $("#btnReflect").addEventListener("click", async (e) => { const b = e.currentTarget; await busy(b, async () => { const r = await api("/api/learning/reflect", "POST"); toast(r.message || "Готово"); draw(el); }); });
    $("#btnDocs").addEventListener("click", async (e) => { const b = e.currentTarget; const ok = await ask({ title: "Изучить документы?", text: "Джарвис прочтёт PDF, Word и текстовые файлы в Документах, на рабочем столе и в Загрузках. Файлы остаются на этом ноутбуке.", yes: "Изучить" }); if (!ok) return; await busy(b, async () => { const r = await api("/api/docs/index", "POST", { confirm: true }); toast(r.message || "Изучаю"); }); });
    el.querySelector("#docForm").addEventListener("submit", async (e) => {
      e.preventDefault(); const q = $("#docIn").value.trim(); if (!q) return;
      const r = await api("/api/hud/action", "POST", { kind: "find", query: q }).catch(() => ({ items: [] }));
      const hits = r.items || [];
      $("#docOut").innerHTML = hits.length ? hits.map((h) => `<div class="item"><span class="grow ellipsis" title="${esc(h.path)}">${esc(h.name)}</span><span class="faint small">${esc(h.dir)}</span></div>`).join("") : `<div class="empty">Ничего не нашёл по имени. Поиск по тексту — голосом: «найди в моих документах …».</div>`;
    });
  }

  /* ---------- Presentation ---------- */
  const SHOW = {
    title: "Презентация", sub: "Доклад за месяц из ваших дел, целей и команд. Управляется голосом и кнопками.",
    render(el) {
      const s = (STATE.hud || {}).show || {};
      el.innerHTML = `<div class="grid-2" style="grid-template-columns:minmax(0,1fr) minmax(0,1.2fr)">
        ${panel("Управление", "", `<div class="col">
          <div class="field"><label for="showLang">Язык</label><select id="showLang"><option value="ru">Русский</option><option value="en">English</option><option value="ja">日本語</option></select></div>
          <div class="foot" style="display:flex;gap:8px;flex-wrap:wrap"><button class="btn primary" id="shStart">Начать доклад</button><button class="btn" id="shPrev">Назад</button><button class="btn" id="shNext">Дальше</button><button class="btn" id="shSay">Сказать вслух</button><button class="btn" id="shFull">На весь экран</button><button class="btn danger" id="shStop">Закончить</button></div>
          <div class="callout"><div><b>Голосом</b>«начни доклад», «следующий слайд», «предыдущий слайд», «переключись на японский», «закончи презентацию».</div></div></div>`)}
        ${panel("Текущий слайд", s.active ? `Слайд ${s.i + 1} из ${s.total}` : "Презентация не запущена", `<div class="stat" style="font-size:24px">${esc(s.slide?.title || "—")}</div><div class="sub" style="font-size:15px;margin-top:10px;color:var(--text)">${esc(s.slide?.say || "Запустите доклад, и здесь появится текст слайда.")}</div>`)}</div>`;
      $("#shStart").onclick = async () => { await hudAct("show", { op: "start", lang: $("#showLang").value }); pollHud(); toast("Доклад начат"); setTimeout(() => this.render(el), 600); };
      $("#shNext").onclick = async () => { await hudAct("show", { op: "next" }); pollHud(); setTimeout(() => this.render(el), 400); };
      $("#shPrev").onclick = async () => { await hudAct("show", { op: "prev" }); pollHud(); setTimeout(() => this.render(el), 400); };
      $("#shStop").onclick = async () => { await hudAct("show", { op: "stop" }); pollHud(); setTimeout(() => this.render(el), 400); };
      $("#shSay").onclick = () => { const x = (STATE.hud || {}).show?.slide; if (x?.say) api("/api/say", "POST", { text: x.say, lang: $("#showLang").value }).catch(() => {}); };
      $("#shFull").onclick = () => JV.openStage("deck");
    },
    onData(_, force) { if (force) return; },
  };

  /* ---------- Appearance ---------- */
  const APPEARANCE = {
    title: "Внешний вид", sub: "Цвет, стиль и раскладка. Всё сохраняется на этом компьютере.",
    render(el) {
      const p = PREFS();
      el.innerHTML = `<div class="grid-2" style="grid-template-columns:minmax(0,1.3fr) minmax(0,1fr)">
        ${panel("Цветовая тема", "Цвет и форма вокруг ядра меняются вместе.", `<div class="palette-grid" role="group" aria-label="Тема">${PALETTES.map((x) => `<button class="pal-card" data-pal="${x.id}" style="--c:${x.a};--bgp:${x.bg}" aria-pressed="${p.palette === x.id}"><span class="pv" aria-hidden="true"></span><b>${esc(x.name)}</b><small>${esc(x.desc)}</small></button>`).join("")}</div>`)}
        ${panel("Вид карточек", "", `${row("Стиль", "Стекло — с прозрачностью, сплошная — однотонная, минимал — без рамок", seg(LOOKS, p.look, "data-look"))}
          ${row("Плотность", "Компактно — меньше отступов и шрифт 13 px", seg(DENSITY, p.density, "data-den"))}
          ${row("Скругление", `${p.radius} px`, `<input class="range" id="rad" type="range" min="4" max="26" value="${p.radius}" style="--v:${(p.radius - 4) / 22 * 100}%;width:200px" aria-label="Скругление">`)}
          ${row("Размер текста", `${p.fs} px`, `<input class="range" id="fs" type="range" min="12" max="17" value="${p.fs}" style="--v:${(p.fs - 12) / 5 * 100}%;width:200px" aria-label="Размер текста">`)}
          ${row("Анимации", "Выключите, если компьютер тормозит", `<label class="switch"><input type="checkbox" id="anim" ${p.anim ? "checked" : ""} aria-label="Анимации"><span></span></label>`)}`)}
      </div>
      <div class="grid-2" style="margin-top:var(--gap);grid-template-columns:minmax(0,1fr) minmax(0,1fr)">
        ${panel("Раскладка главной", "Выберите готовый набор или настройте виджеты на главной кнопкой «Настроить виджеты».", `<div class="pills" style="margin-bottom:12px">${Object.keys(PRESETS).map((n) => `<button class="chip ${n === "Полный" ? "on" : ""}" data-preset="${n}">${esc(n)}</button>`).join("")}</div>
          <div class="field"><label>Место ядра</label>${seg([["center", "Ядро и виджеты"], ["grid", "Сетка"], ["focus", "Только ядро"]], p.layout.mode, "data-mode")}</div>`)}
        ${panel("Сброс и перенос", "", `<div class="foot" style="display:flex;gap:8px;flex-wrap:wrap"><button class="btn" id="btnExport">Сохранить настройки в файл</button><label class="btn" style="cursor:pointer">Загрузить из файла<input type="file" id="fileIn" accept="application/json" hidden></label><button class="btn danger" id="btnReset">Вернуть всё по умолчанию</button></div>`)}
      </div>`;
      el.querySelectorAll("[data-pal]").forEach((b) => b.addEventListener("click", () => { p.palette = b.dataset.pal; savePrefs(); applyLook(); this.render(el); }));
      el.querySelectorAll("[data-look]").forEach((b) => b.addEventListener("click", () => { p.look = b.dataset.look; savePrefs(); applyLook(); this.render(el); }));
      el.querySelectorAll("[data-den]").forEach((b) => b.addEventListener("click", () => { p.density = b.dataset.den === "Компактно" ? "compact" : b.dataset.den; savePrefs(); applyLook(); this.render(el); }));
      el.querySelectorAll("[data-mode]").forEach((b) => b.addEventListener("click", () => { p.layout.mode = b.dataset.mode; savePrefs(); this.render(el); }));
      el.querySelectorAll("[data-preset]").forEach((b) => b.addEventListener("click", () => { const items = PRESETS[b.dataset.preset]; p.layout.items = items ? clone(items).map((i) => ({ ...i, on: true })).concat(p.layout.items.filter((x) => !items.some((y) => y.id === x.id)).map((x) => ({ ...x, on: false }))) : clone(DEFAULT_PREFS.layout.items); savePrefs(); toast("Раскладка: " + b.dataset.preset); this.render(el); }));
      $("#rad").addEventListener("input", (e) => { p.radius = Number(e.target.value); savePrefs(); applyLook(); });
      $("#fs").addEventListener("input", (e) => { p.fs = Number(e.target.value); savePrefs(); applyLook(); });
      $("#anim").addEventListener("change", (e) => { p.anim = e.target.checked; savePrefs(); applyLook(); });
      $("#btnExport").onclick = () => { const a = document.createElement("a"); a.href = URL.createObjectURL(new Blob([JSON.stringify({ kind: "jarvis-ui", ...p }, null, 1)], { type: "application/json" })); a.download = "jarvis-ui.json"; a.click(); setTimeout(() => URL.revokeObjectURL(a.href), 4000); };
      $("#fileIn").addEventListener("change", async (e) => {
        try { const x = JSON.parse(await e.target.files[0].text()); if (x.kind !== "jarvis-ui") throw new Error("это не файл настроек Джарвиса"); Object.assign(p, { palette: x.palette, look: x.look, density: x.density, anim: !!x.anim, radius: Number(x.radius) || 16, fs: Number(x.fs) || 14, layout: x.layout || p.layout }); savePrefs(); applyLook(); toast("Настройки загружены"); this.render(el); }
        catch (err) { toast(err.message); }
      });
      $("#btnReset").onclick = async () => { if (await ask({ title: "Вернуть всё по умолчанию?", text: "Тема, раскладка и виджеты вернутся к начальным. Дела, цели и память не меняются.", yes: "Вернуть", danger: true })) { localStorage.removeItem("jv.ui"); location.reload(); } };
    },
  };

  /* ---------- Settings ---------- */
  const SECTIONS = [["voice", "Голос", "mic"], ["messengers", "Мессенджеры и почта", "msg"], ["calendar", "Календарь", "cal"], ["weather", "Погода", "weather"], ["ai", "Ключи и облако", "brain"], ["computer", "Компьютер", "shield"], ["character", "Характер", "paint"], ["data", "Данные", "doc"]];
  const SETTINGS = {
    title: "Настройки", sub: "Всё, что меняет поведение Джарвиса. Каждый раздел объясняет, что делает настройка и как её включить.",
    render(el, sub) {
      const cur = SECTIONS.some((s) => s[0] === sub) ? sub : "voice";
      el.innerHTML = `<div class="settings"><nav class="subnav" aria-label="Разделы настроек">${SECTIONS.map(([id, t, ic]) => `<a href="#/settings/${id}" aria-current="${id === cur}">${svg(ic)}${esc(t)}</a>`).join("")}</nav><div id="setBody"></div></div>`;
      const body = $("#setBody");
      const fn = { voice: SEC.voice, messengers: SEC.messengers, calendar: SEC.calendar, weather: SEC.weather, ai: SEC.ai, computer: SEC.computer, character: SEC.character, data: SEC.data }[cur];
      try { fn(body); } catch (e) { body.innerHTML = callout("bad", "Раздел не открылся", esc(e.message)); }
    },
  };
  const V3 = () => STATE.v3 || {};
  const CONN = () => STATE.conn || {};
  const REMOTE = () => STATE.remote || {};

  const SEC = {};
  SEC.voice = (el) => {
    const v = V3().voice || {}, f = V3().features || {};
    el.innerHTML = section("voice", "Голос", "Как Джарвис говорит, слушает и узнаёт вас. Голос, которым вы говорите, записывается один раз.",
      panel("Узнавание вашего голоса", "Джарвис реагирует только на вас, если это включено ниже.", `
        ${row("Голос записан", V3().voice_enrolled ? "да — Джарвис узнаёт вас" : "нет — запишите голос", `<span class="chip ${V3().voice_enrolled ? "ok" : "warn"}">${V3().voice_enrolled ? "записан" : "не записан"}</span><button class="btn" id="btnEnroll">${V3().voice_enrolled ? "Записать заново" : "Записать голос"}</button>`)}
        ${row("Слушать только меня", "Чужие голоса и телевизор не будут запускать Джарвиса", sw("features", "voice_lock", f.voice_lock !== false, "Слушать только меня"))}
        ${row("Можно перебивать", "Скажите «стоп» или имя, пока Джарвис говорит", sw("features", "barge_in", f.barge_in !== false, "Можно перебивать"))}`) +
      panel("Голос ответов", "Piper работает без интернета. Microsoft звучит естественнее, но нужна связь.", `
        ${row("Синтезатор", "", seg([["piper", "Piper · офлайн"], ["edge", "Microsoft · онлайн"]], v.engine, "data-eng"))}
        ${row("Голос Piper", "Русские голоса, которые поставлены", `<select data-set="voice|piper_voice_ru|str" aria-label="Голос Piper">${(v.piper_voices || ["dmitri"]).map((n) => `<option value="${esc(n)}" ${v.piper === n ? "selected" : ""}>${esc(n)}</option>`).join("")}</select>`)}
        ${row("Звуки интерфейса", "Короткие сигналы «слушаю», «готово»", sw("voice", "ui_sounds", v.ui_sounds !== false, "Звуки"))}
        ${row("Тише музыка, когда говорю", "Во сколько раз приглушать музыку и видео", `<input class="range" type="range" min="0" max="100" value="${Math.round((v.duck_level ?? 0.15) * 100)}" data-set="voice|duck_level|num" style="width:200px;--v:${Math.round((v.duck_level ?? 0.15) * 100)}%" aria-label="Приглушение">`)}
        ${row("Проверить голос", "Джарвис скажет короткую фразу", `<button class="btn" id="btnSay">Послушать</button>`)}`) +
      callout("", "Как это работает", `<p>Первый запуск проводит через запись голоса. Потом Джарвис слушает фразы «Джарвис», «Эй, Джарвис» и команды. Полный список имён — в файле config.toml, раздел [wake].</p>`));
    $("#btnEnroll").onclick = async (e) => { await busy(e.currentTarget, () => api("/api/voice/enroll", "POST")); toast("Читайте текст. Запись идёт около 20 секунд."); };
    $("#btnSay").onclick = () => api("/api/say", "POST", { text: "Слушаю вас. Так звучит мой голос." }).catch((e) => toast(e.message));
    el.querySelectorAll("[data-eng]").forEach((b) => b.addEventListener("click", async () => { await api("/api/settings", "POST", { section: "voice", key: "tts_engine_ru", value: b.dataset.eng }); toast("Голос переключён"); await pollSlow(); SEC.voice(el); }));
  };

  SEC.messengers = (el) => {
    const c = CONN(), r = REMOTE(), tg = c.telegram || {}, wa = c.whatsapp || {};
    el.innerHTML = section("messengers", "Мессенджеры и почта", "Джарвис может читать и отправлять сообщения там, где вы это разрешили. Ниже — что нужно сделать для каждого.",
      panel("WhatsApp", "Подключите телефон: откроется QR-код, отсканируйте его в WhatsApp", `
        ${row("Включить WhatsApp", wa.enabled ? (wa.state === "connected" ? "подключён" : "ждёт QR-кода") : "выключен", `<label class="switch"><input type="checkbox" id="waOn" ${wa.enabled ? "checked" : ""} aria-label="WhatsApp"><span></span></label>`)}
        ${wa.qr && wa.state !== "connected" ? `<div style="margin:12px 0"><img class="qr" alt="QR-код WhatsApp" src="${esc(wa.qr)}"></div><p class="sub">WhatsApp → Связанные устройства → Привязать устройство. Код обновляется сам.</p>` : ""}
        ${wa.state === "connected" ? `<div class="foot"><button class="btn danger" id="waOut">Отключить WhatsApp</button></div>` : ""}
        ${callout("", "Инструкция", `<ol class="steps" style="margin-top:10px"><li><div><b>Включите переключатель</b><p>Появится QR-код.</p></div></li><li><div><b>Откройте WhatsApp на телефоне</b><p>Меню → Связанные устройства → Привязать устройство.</p></div></li><li><div><b>Наведите камеру на код</b><p>Когда статус станет «подключён», можно просить: «что пишет мама».</p></div></li></ol>`)}`) +
      panel("Telegram-бот (управление с телефона)", "Бот отвечает только вам. Токен берётся у @BotFather.", `
        ${row("Статус бота", r.running ? `работает${r.username ? " · @" + esc(r.username) : ""}` : r.auth_error ? "токен не принят Telegram" : r.has_token ? "выключен" : "не настроен", `<span class="chip ${r.running ? "ok" : r.auth_error ? "bad" : ""}">${r.running ? "работает" : r.auth_error ? "ошибка токена" : "не работает"}</span>`)}
        ${row("Токен бота", r.has_token ? "сохранён в Windows" : "вставьте токен, он не показывается обратно", `<input type="password" id="tgTok" placeholder="${r.has_token ? "•••••• (чтобы заменить, введите новый)" : "123456:AA…"}" autocomplete="off" aria-label="Токен бота"><button class="btn" id="tgSave">Сохранить</button>`)}
        ${row("Ваш номер в Telegram", "Пишите боту с этого аккаунта: он ответит только вам", `<input type="text" id="tgOwner" inputmode="numeric" value="${esc(r.owner_id || "")}" placeholder="например 123456789" aria-label="Номер владельца"><button class="btn" id="tgOwnerSave">Сохранить</button>`)}
        ${callout("", "Как создать бота", `<ol class="steps" style="margin-top:10px"><li><div><b>Откройте @BotFather в Telegram</b><p>Напишите /newbot, придумайте имя и логин, который заканчивается на «bot».</p></div></li><li><div><b>Скопируйте токен</b><p>Вида 123456:AA… Вставьте его выше и нажмите «Сохранить». Чат с ботом не нужен.</p></div></li><li><div><b>Напишите боту любое слово</b><p>Джарвис покажет ваш номер. Вставьте его в поле выше.</p></div></li></ol>`)}`) +
      panel("Telegram (ваш аккаунт)", "Нужен, чтобы читать ваши личные чаты и отправлять сообщения от вашего имени.", `
        ${row("Вход", tg.connected ? "вход выполнен" : "нужно войти", `<span class="chip ${tg.connected ? "ok" : "warn"}">${tg.connected ? "есть" : "нужен вход"}</span>`)}
        ${row("api_id и api_hash", "Берутся на my.telegram.org → API development tools", `<input type="text" id="tgApi" placeholder="api_id" value="${esc(tg.api_id || "")}" style="width:110px" aria-label="api_id"><input type="password" id="tgHash" placeholder="${tg.has_hash ? "сохранён" : "api_hash"}" aria-label="api_hash"><button class="btn" id="tgCreds">Сохранить</button>`)}
        ${row("Номер телефона", "В формате +998…", `<input type="text" id="tgPhone" placeholder="+998901234567" aria-label="Телефон"><button class="btn" id="tgCode">Отправить код</button>`)}
        ${row("Код из Telegram", "Придёт в приложение Telegram", `<input type="text" id="tgCodeIn" inputmode="numeric" aria-label="Код"><button class="btn primary" id="tgSignIn">Войти</button>`)}
        ${tg.connected ? `<div class="foot"><button class="btn danger" id="tgOut">Выйти из аккаунта</button></div>` : ""}`) +
      panel("Почта", "Джарвис сообщит о новых письмах и прочитает их по запросу.", `
        <div class="list">${(c.email || []).map((a) => `<div class="item"><div class="grow"><div class="t">${esc(a.address)}</div><div class="m">${esc(a.imap_host || "")}</div></div><button class="btn sm ghost" data-mail="${esc(a.address)}">Удалить</button></div>`).join("") || `<div class="empty">Почта не подключена</div>`}</div>
        <form id="mailForm" class="col" style="margin-top:12px"><div class="form-row"><div class="field grow"><label for="mAddr">Адрес почты</label><input id="mAddr" type="email" placeholder="you@gmail.com" required></div><div class="field grow"><label for="mPass">Пароль приложения</label><input id="mPass" type="password" placeholder="16 символов из Google" required></div></div><div><button class="btn primary" type="submit">Подключить почту</button></div></form>
        ${callout("", "Как получить пароль приложения (Gmail)", `<ol class="steps" style="margin-top:10px"><li><div><b>Включите двухэтапную проверку</b><p>myaccount.google.com → Безопасность.</p></div></li><li><div><b>Создайте пароль приложения</b><p>myaccount.google.com/apppasswords → имя «Джарвис» → Создать.</p></div></li><li><div><b>Вставьте 16 символов сюда</b><p>Обычный пароль от почты не подходит.</p></div></li></ol>`)}`));
    $("#waOn").addEventListener("change", async (e) => { await api("/api/connections/whatsapp", "POST", { enabled: e.target.checked }); toast(e.target.checked ? "WhatsApp запускается, подождите QR-код" : "WhatsApp выключен"); pollSlow(); setTimeout(() => SEC.messengers(el), 2500); });
    const waOut = $("#waOut"); if (waOut) waOut.onclick = async () => { if (await ask({ title: "Отключить WhatsApp?", text: "Придётся заново сканировать QR-код.", yes: "Отключить", danger: true })) { await api("/api/connections/whatsapp_logout", "POST", {}); toast("WhatsApp отключён"); pollSlow(); SEC.messengers(el); } };
    $("#tgSave").onclick = async (e) => { const t = $("#tgTok").value.trim(); if (!t) return toast("Вставьте токен"); await busy(e.currentTarget, () => api("/api/keys", "POST", { name: "telegram_bot", value: t })); $("#tgTok").value = ""; toast("Токен сохранён, проверяю…"); setTimeout(() => { pollSlow(); SEC.messengers(el); }, 3500); };
    $("#tgOwnerSave").onclick = async () => { const n = $("#tgOwner").value.replace(/\D/g, ""); await api("/api/remote", "POST", { owner_id: Number(n || 0), enabled: true }); toast("Номер сохранён"); pollSlow(); };
    $("#tgCreds").onclick = async () => { const a = $("#tgApi").value.trim(), h = $("#tgHash").value.trim(); if (!a) return toast("Введите api_id"); await api("/api/connections/telegram_creds", "POST", { api_id: a, api_hash: h }); toast("Сохранено"); pollSlow(); };
    $("#tgCode").onclick = async (e) => { const p = $("#tgPhone").value.trim(); if (!p) return toast("Введите номер"); await busy(e.currentTarget, () => api("/api/connections/telegram_code", "POST", { phone: p })); toast("Код отправлен в Telegram"); };
    $("#tgSignIn").onclick = async (e) => { const code = $("#tgCodeIn").value.trim(); if (!code) return toast("Введите код"); const r = await busy(e.currentTarget, () => api("/api/connections/telegram_signin", "POST", { code })); if (r.step === "password_needed") toast("Нужен пароль двухэтапной проверки. Введите его в настройках Telegram."); else toast(r.ok ? "Вход выполнен" : "Код не подошёл"); pollSlow(); SEC.messengers(el); };
    const tgOut = $("#tgOut"); if (tgOut) tgOut.onclick = async () => { if (await ask({ title: "Выйти из Telegram?", text: "Джарвис перестанет читать ваши чаты.", yes: "Выйти", danger: true })) { await api("/api/connections/telegram_logout", "POST", {}); pollSlow(); SEC.messengers(el); } };
    el.querySelectorAll("[data-mail]").forEach((b) => b.addEventListener("click", async () => { if (await ask({ title: "Удалить почту?", text: b.dataset.mail, yes: "Удалить", danger: true })) { await api("/api/connections/email_delete", "POST", { address: b.dataset.mail }); pollSlow(); SEC.messengers(el); } }));
    $("#mailForm").addEventListener("submit", async (e) => {
      e.preventDefault();
      const address = $("#mAddr").value.trim(), password = $("#mPass").value;
      const r = await busy(e.submitter, () => api("/api/connections/email_add", "POST", { address, password, name: address }).catch((err) => ({ ok: false, message: err.message })));
      toast(r.message || (r.ok ? "Почта подключена" : "Не получилось")); if (r.ok) { $("#mPass").value = ""; pollSlow(); SEC.messengers(el); }
    });
  };

  SEC.calendar = (el) => {
    const c = CONN().calendar || {};
    el.innerHTML = section("calendar", "Календарь", "Джарвис расскажет, что у вас сегодня, и напомнит перед встречами.",
      panel("Google Календарь", `Подключено календарей: ${c.count ?? 0}`, `
        <form id="calForm" class="form-row"><div class="field grow"><label for="calUrl">Секретная ссылка .ics</label><input id="calUrl" type="password" placeholder="https://calendar.google.com/…/basic.ics" autocomplete="off" required></div><button class="btn primary" type="submit">Добавить</button></form>
        ${callout("", "Где взять ссылку", `<ol class="steps" style="margin-top:10px"><li><div><b>Откройте Google Календарь на компьютере</b><p>Настройки → нужный календарь.</p></div></li><li><div><b>Найдите «Секретный адрес в формате iCal»</b><p>Скопируйте ссылку и вставьте сюда. Она похожа на пароль, не отправляйте её никому.</p></div></li></ol>`)}`));
    $("#calForm").addEventListener("submit", async (e) => { e.preventDefault(); const url = $("#calUrl").value.trim(); const r = await busy(e.submitter, () => api("/api/connections/calendar_add", "POST", { url }).catch((err) => ({ message: err.message }))); toast(r.message || "Календарь добавлен"); pollSlow(); SEC.calendar(el); });
  };

  SEC.weather = (el) => {
    const city = (V3().weather || {}).city || "";
    el.innerHTML = section("weather", "Погода", "Город для прогноза на главной и в ответах.",
      panel("Город", "", row("Город по умолчанию", "Можно сказать «погода в Самарканде» — тогда город будет другой", `<input type="text" id="wCity" value="${esc(city)}" aria-label="Город">`)));
    $("#wCity").addEventListener("change", async (e) => { await api("/api/settings", "POST", { section: "weather", key: "city", value: e.target.value.trim() }); toast("Город сохранён"); });
  };

  SEC.ai = (el) => {
    const k = V3().keys || {}, cl = V3().cloud || {};
    const key = (name, title, hint, link) => `<div class="setting"><div class="lbl-wrap"><b>${title}</b><small>${hint} ${link ? `<a href="${link}" target="_blank" rel="noopener">Где взять</a>` : ""}</small></div><div class="ctrl"><span class="chip ${k[name] ? "ok" : ""}">${k[name] ? "сохранён" : "не задан"}</span><input type="password" id="k_${name}" placeholder="вставьте ключ" autocomplete="off" aria-label="${title}" style="width:200px"><button class="btn" data-savekey="${name}">Сохранить</button>${k[name] ? `<button class="btn ghost sm" data-clearkey="${name}">Удалить</button>` : ""}</div></div>`;
    el.innerHTML = section("ai", "Ключи и облако", "Ключи хранятся в диспетчере учётных данных Windows и не показываются обратно. Оба бесплатны.",
      panel("Ключи", "", key("groq", "Groq", "Речь и ответы. Бесплатно.", "https://console.groq.com/keys") + key("gemini", "Gemini", "Зрение и запасной мозг. Бесплатно.", "https://aistudio.google.com/apikey") + key("anthropic", "Anthropic", "Необязательно.", "https://console.anthropic.com/"))) +
      panel("Облако", "", `${row("Использовать облако", "Выключите, чтобы всё работало только на этом ноутбуке", sw("cloud", "enabled", cl.enabled !== false, "Облако"))}
        ${row("Работать без интернета, если связи нет", "Загрузит локальные модели, когда облако недоступно", sw("cloud", "local_fallback", !!cl.local_fallback, "Без интернета"))}`);
    el.querySelectorAll("[data-savekey]").forEach((b) => b.addEventListener("click", async () => { const n = b.dataset.savekey, v = $("#k_" + n).value.trim(); if (!v) return toast("Вставьте ключ"); await busy(b, () => api("/api/keys", "POST", { name: n, value: v })); toast("Ключ сохранён"); pollSlow(); SEC.ai(el); }));
    el.querySelectorAll("[data-clearkey]").forEach((b) => b.addEventListener("click", async () => { if (await ask({ title: "Удалить ключ?", text: "Без него часть функций перестанет работать.", yes: "Удалить", danger: true })) { await api("/api/keys", "POST", { name: b.dataset.clearkey, value: "" }); pollSlow(); SEC.ai(el); } }));
  };

  SEC.computer = (el) => {
    const f = V3().features || {}, perf = V3().performance || {}, vpn = (STATE.shield || {}).vpn || {};
    el.innerHTML = section("computer", "Компьютер и безопасность", "Анализ ноутбука, поиск по документам, VPN и режим игры.",
      panel("Анализ и оптимизация", "Ноутбук оценивается, и предлагаются безопасные улучшения. Ничего не меняется без вашего выбора.", `<div class="foot"><button class="btn primary" id="btnAnalyze">Проанализировать ноутбук</button></div>`) +
      panel("Режим игры", "", row("Не беспокоить во время игр", "Джарвис молчит, пока идёт игра, и экономит видеопамять", sw("performance", "game_mode", perf.game_mode !== false, "Режим игры"))) +
      panel("VPN", "Имя туннеля WireGuard, который включает команда «включи VPN». Туннель создаётся в приложении WireGuard.", `${row("Имя туннеля", vpn.on ? "сейчас включён" : "сейчас выключен", `<input type="text" data-set="vpn|tunnel|str" value="${esc((V3().vpn || {}).tunnel || "")}" placeholder="например, home" aria-label="Туннель">`)}`) +
      panel("Документы", "Поиск по PDF, Word и текстовым файлам — в разделе «Память».", `<div class="foot"><button class="btn" data-go="#/memory">Открыть «Память»</button></div>`));
    $("#btnAnalyze").onclick = () => JV.STATE && window.Analysis && Analysis.open();
    el.querySelectorAll("[data-go]").forEach((b) => b.addEventListener("click", () => (location.hash = b.dataset.go.slice(1))));
  };

  SEC.character = (el) => {
    const v = V3(), cur = v.persona || "tactical";
    const opts = [["tactical", "Тактический", "Коротко, по делу, «сэр»"], ["coder", "Программист", "Технично, без лишних слов"], ["business", "Деловой", "Сроки, результат, решения"], ["friend", "Друг", "Тепло, шутки, разговор"], ["quiet", "Тихий", "Отвечает только на экране"], ["custom", "Свой", "Опишите характер сами"]];
    el.innerHTML = section("character", "Характер", "Как Джарвис формулирует ответы. Меняется сразу.",
      panel("Характер", "", `<div class="col">${opts.map(([id, t, d]) => `<button class="opt" data-persona="${id}" aria-pressed="${cur === id}"><span><b>${t}</b><small>${d}</small></span></button>`).join("")}</div>
        <div class="field" style="margin-top:12px"><label for="cp">Свой характер</label><textarea id="cp" rows="3" placeholder="Например: строгий тренер по английскому, коротко и с исправлением ошибок">${esc(v.custom_persona || "")}</textarea></div>
        <div class="foot" style="margin-top:8px"><button class="btn" id="cpSave">Сохранить свой характер</button></div>`));
    el.querySelectorAll("[data-persona]").forEach((b) => b.addEventListener("click", async () => { await api("/api/persona", "POST", { persona: b.dataset.persona }); toast("Характер изменён"); pollSlow(); SEC.character(el); }));
    $("#cpSave").onclick = async () => { await api("/api/persona", "POST", { custom_persona: $("#cp").value, persona: "custom" }); toast("Сохранено"); pollSlow(); SEC.character(el); };
  };

  SEC.data = (el) => {
    el.innerHTML = section("data", "Данные", "Резервная копия настроек, очистка истории и сброс.",
      panel("Резервная копия", "Файл с внешним видом и раскладкой. Дела, цели и память в него не входят.", `<div class="foot"><button class="btn" id="dExport">Сохранить в файл</button></div>`) +
      panel("История разговоров", "Удаляет список команд и ответов. Перед этим делается резервная копия файла.", `<div class="foot"><button class="btn danger" id="dHist">Очистить историю</button></div>`) +
      panel("Журнал работы", "Нужен, если что-то сломалось. Его можно отправить разработчику.", `<div class="foot"><button class="btn" id="dLog">Открыть журнал</button></div>`));
    $("#dExport").onclick = () => { const a = document.createElement("a"); a.href = URL.createObjectURL(new Blob([JSON.stringify({ kind: "jarvis-ui", ...PREFS() }, null, 1)], { type: "application/json" })); a.download = "jarvis-ui.json"; a.click(); };
    $("#dHist").onclick = async () => { if (await ask({ title: "Очистить историю?", text: "Список команд и ответов пропадёт. Резервная копия сохранится рядом.", yes: "Очистить", danger: true })) { await api("/api/history/clear", "POST", {}).then((r) => toast(r.message || "История очищена")).catch((e) => toast(e.message)); pollSlow(); } };
    $("#dLog").onclick = () => dialog(`<div class="code" id="logBox" style="max-height:60vh;overflow:auto;white-space:pre-wrap">Загружаю…</div>`, "Журнал работы");
    api("/api/hud").then((h) => { const b = $("#logBox"); if (b) b.textContent = (h.logs || []).join("\n") || "Журнал пуст"; }).catch(() => {});
  };

  /* ---------- First run: three steps ---------- */
  const ONB = { step: 0, persona: "tactical", cloud: true, palette: PREFS().palette };
  function onbOpen() {
    const d = $("#dlg"); if (d.open) return;
    ONB.step = 0; onbDraw(d); d.showModal();
  }
  function onbDraw(d) {
    const s = ONB.step, enrolled = !!(STATE.v3 && STATE.v3.voice_enrolled) || !!(STATE.hud && STATE.hud.voice_enrolled);
    const steps = ["Голос", "Характер и цвет", "Работа"];
    let body = "";
    if (s === 0) body = `<p class="onb-big">Джарвис будет слушать только вас. Прочитайте вслух три-четыре предложения: он запомнит ваш голос, и чужие голоса и телевизор его не разбудят.</p>
      <button class="voice-test" id="onbVoice" ${enrolled ? "disabled" : ""}><b>${enrolled ? "Голос запомнен" : "Нажмите и читайте"}</b><span>${enrolled ? "можно идти дальше" : "около 20 секунд"}</span></button>`;
    if (s === 1) body = `${[["tactical", "Тактический", "Коротко, по делу, «сэр»"], ["coder", "Программист", "Технично, без лишних слов"], ["business", "Деловой", "Сроки и решения"], ["friend", "Друг", "Тепло и шутки"]].map(([id, t, x]) => `<button class="opt" data-onbp="${id}" aria-pressed="${ONB.persona === id}"><span><b>${t}</b><small>${x}</small></span></button>`).join("")}
      <h4 style="margin:14px 0 8px">Цвет</h4><div class="swatches">${PALETTES.map((p) => `<button class="swatch" data-onbc="${p.id}" style="background:${p.a};color:${p.a}" aria-pressed="${ONB.palette === p.id}" aria-label="${esc(p.name)}" title="${esc(p.name)}"></button>`).join("")}</div>`;
    if (s === 2) body = `<p class="onb-big">Как Джарвис будет работать?</p>
      <button class="opt" data-onbcl="1" aria-pressed="${ONB.cloud}"><span><b>С облаком (рекомендуется)</b><small>Быстрее отвечает и понимает речь. Нужен бесплатный ключ Groq — его вводят в «Настройки → Ключи».</small></span></button>
      <button class="opt" data-onbcl="0" aria-pressed="${!ONB.cloud}"><span><b>Без интернета</b><small>Всё работает на этом ноутбуке. Медленнее, зато ничего никуда не уходит.</small></span></button>`;
    d.innerHTML = `<div class="onb-steps" aria-hidden="true">${steps.map((_, i) => `<i class="${i <= s ? "on" : ""}"></i>`).join("")}</div>
      <h3>Знакомство · шаг ${s + 1} из 3: ${steps[s]}</h3><p style="margin-bottom:12px">Всё можно поменять позже в настройках.</p>${body}
      <div class="bs"><button class="btn" id="onbBack" ${s === 0 ? "hidden" : ""}>Назад</button><button class="btn primary" id="onbNext" ${s === 0 && !enrolled ? "disabled" : ""}>${s === 2 ? "Готово, к анализу" : "Дальше"}</button></div>`;
    d.querySelector("#onbBack").onclick = () => { ONB.step--; onbDraw(d); };
    d.querySelector("#onbNext").onclick = onbNext;
    const v = d.querySelector("#onbVoice"); if (v) v.onclick = async () => { await api("/api/voice/enroll", "POST").catch((e) => toast(e.message)); toast("Читайте текст, запись около 20 секунд"); };
    d.querySelectorAll("[data-onbp]").forEach((b) => b.onclick = () => { ONB.persona = b.dataset.onbp; onbDraw(d); });
    d.querySelectorAll("[data-onbc]").forEach((b) => b.onclick = () => { ONB.palette = b.dataset.onbc; PREFS().palette = ONB.palette; savePrefs(); applyLook(); onbDraw(d); });
    d.querySelectorAll("[data-onbcl]").forEach((b) => b.onclick = () => { ONB.cloud = b.dataset.onbcl === "1"; onbDraw(d); });
    d.onclose = () => {};
  }
  async function onbNext() {
    const d = $("#dlg");
    if (ONB.step === 1) { await api("/api/persona", "POST", { persona: ONB.persona }).catch(() => {}); }
    if (ONB.step < 2) { ONB.step++; onbDraw(d); return; }
    await api("/api/settings", "POST", { section: "cloud", key: "enabled", value: ONB.cloud }).catch(() => {});
    await api("/api/settings", "POST", { section: "ui", key: "onboarded", value: true }).catch(() => {});
    await api("/api/setup/done", "POST", {}).catch(() => {});
    d.close(); setTimeout(openAnalysis, 200); pollSlow();
  }

  /* ---------- Analysis: score, what is missing, optimisation ---------- */
  function openAnalysis() {
    const d = $("#dlg");
    d.innerHTML = `<h3>Анализ ноутбука</h3><p>Ничего не меняется, пока вы не отметите и не нажмёте кнопку.</p><div id="anBody" class="col" style="min-height:120px"><div class="empty">Изучаю компьютер… около 30 секунд.</div></div>
      <div class="bs"><button class="btn" value="close">Закрыть</button><button class="btn" id="anAgain">Проверить снова</button><button class="btn primary" id="anGo" disabled>Сделать отмеченное</button></div>`;
    d.querySelector('[value="close"]').onclick = () => d.close();
    d.showModal();
    load(d);
  }
  async function load(d) {
    const body = d.querySelector("#anBody"), go = d.querySelector("#anGo");
    d.querySelector("#anAgain").onclick = () => load(d);
    go.disabled = true;
    let a = null, setup = null;
    try { [a, setup] = await Promise.all([api("/api/optimize"), api("/api/setup")]); }
    catch (e) { body.innerHTML = callout("bad", "Анализ не получился", esc(e.message)); return; }
    const L = 2 * Math.PI * 44, col = a.score >= 80 ? "var(--ok)" : a.score >= 55 ? "var(--warn)" : "var(--bad)";
    body.innerHTML = `<div class="row" style="gap:18px;align-items:center;flex-wrap:wrap">
        <svg viewBox="0 0 110 110" width="130" height="130" aria-label="Оценка ${a.score} из 100"><circle cx="55" cy="55" r="44" fill="none" stroke="rgba(255,255,255,.08)" stroke-width="8"/><circle cx="55" cy="55" r="44" fill="none" stroke="${col}" stroke-width="8" stroke-linecap="round" stroke-dasharray="${L}" stroke-dashoffset="${L * (1 - a.score / 100)}" transform="rotate(-90 55 55)"/><text x="55" y="58" text-anchor="middle" font-size="26" font-weight="600" fill="currentColor">${a.score}</text><text x="55" y="75" text-anchor="middle" font-size="10" fill="#8a97a8">из 100</text></svg>
        <div class="grow"><table style="width:100%;font-size:13px">${a.passport.map(([k, v]) => `<tr><td class="faint" style="padding:3px 10px 3px 0;white-space:nowrap">${esc(k)}</td><td>${esc(v)}</td></tr>`).join("")}</table></div></div>
      <h4>Что мешает</h4>${a.problems.map((p) => `<div class="item"><span class="chip ${p.sev === "bad" ? "bad" : p.sev === "warn" ? "warn" : ""}">${p.sev === "bad" ? "важно" : p.sev === "warn" ? "внимание" : "инфо"}</span><div class="grow"><b>${esc(p.title)}</b><div class="m">${esc(p.how)}</div></div></div>`).join("") || `<div class="item"><span class="chip ok">ок</span><div class="grow">Серьёзных проблем нет</div></div>`}
      <h4>Оптимизация</h4>${a.plan.filter((p) => p.group !== "startup").map((p) => `<label class="item"><input class="check" type="checkbox" data-opt="${esc(p.id)}" ${p.default ? "checked" : ""}><div class="grow"><b>${esc(p.title)}</b><div class="m">${esc(p.why)}${p.undo ? "" : " · вернуть нельзя"}</div></div></label>`).join("") || `<div class="item"><div class="grow">Всё уже настроено</div></div>`}
      ${a.plan.some((p) => p.group === "startup") ? `<details style="margin-top:8px"><summary class="muted">Автозапуск: ${a.plan.filter((p) => p.group === "startup").length}</summary>${a.plan.filter((p) => p.group === "startup").map((p) => `<label class="item"><input class="check" type="checkbox" data-opt="${esc(p.id)}"><div class="grow">${esc(p.title)}</div></label>`).join("")}</details>` : ""}
      <h4>Драйверы и настройка Джарвиса</h4>${(setup.items || []).filter((i) => i.status !== "ok").map((i) => `<div class="item"><span class="chip ${i.status === "missing" ? "bad" : "warn"}">${i.status === "missing" ? "не хватает" : "внимание"}</span><div class="grow"><b>${esc(i.title)}</b><div class="m">${esc(i.detail || i.fix || "")}</div></div>${i.fix_id && (setup.auto_ids || []).includes(i.fix_id) ? `<label class="row"><input class="check" type="checkbox" data-fix="${esc(i.fix_id)}" checked></label>` : ""}</div>`).join("") || `<div class="item"><span class="chip ok">ок</span><div class="grow">Всё на месте</div></div>`}
      ${a.can_undo ? `<div class="foot"><button class="btn" id="anUndo">Отменить прошлую оптимизацию</button></div>` : ""}
      <div id="anLog"></div>`;
    go.disabled = false;
    go.onclick = async () => {
      const ids = [...body.querySelectorAll("[data-opt]:checked")].map((x) => x.dataset.opt);
      const fixes = [...body.querySelectorAll("[data-fix]:checked")].map((x) => x.dataset.fix);
      if (!ids.length && !fixes.length) return toast("Ничего не отмечено");
      go.disabled = true; go.textContent = "Выполняю…";
      try {
        if (ids.length) { const r = await api("/api/optimize", "POST", { ids }); d.querySelector("#anLog").innerHTML = r.items.map((x) => `<div class="item"><span class="chip ${x.ok ? "ok" : "bad"}">${x.ok ? "готово" : "ошибка"}</span><div class="grow">${esc(x.title)}<div class="m">${esc(x.message || "")}</div></div></div>`).join(""); }
        if (fixes.length) { await api("/api/setup/run", "POST", { confirm: true, ids: fixes }); toast("Устанавливаю недостающее в фоне"); }
      } catch (e) { toast(e.message); }
      go.textContent = "Сделать отмеченное"; go.disabled = false;
    };
    const un = body.querySelector("#anUndo");
    if (un) un.onclick = async () => { const r = await api("/api/optimize/undo", "POST", {}); toast("Возвращено: " + (r.done || []).length); load(d); };
  }

  window.PAGES = { tasks: TASKS, goals: GOALS, commands: COMMANDS, memory: MEMORY, show: SHOW, appearance: APPEARANCE, settings: SETTINGS };
  window.Onboarding = { open: onbOpen };
  window.Analysis = { open: openAnalysis };
})();
