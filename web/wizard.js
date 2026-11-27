/* «Анализ ноутбука»: full analysis, what is missing, optimization. Opens by itself on the first start. Nothing runs before a click. */
"use strict";
const WZ = { a: null, s: null, busy: false, log: [] };
const wzPost = async (url, body = {}) => (await fetch(url, { method: "POST", headers: { "Content-Type": "application/json", "X-Jarvis": "1" }, body: JSON.stringify(body) })).json();
const wzSleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function wizardOpen() {
  const d = hEl("hxWiz"); if (d.open) return;
  WZ.a = WZ.s = null; WZ.log = []; WZ.busy = false; wizardDraw(); d.showModal();
  await wizardScan();
}
async function wizardScan() {
  WZ.a = WZ.s = null; wizardDraw();
  const get = (u, k) => fetch(u).then((r) => r.json()).then((x) => { WZ[k] = x; }).catch(() => { WZ[k] = { error: true }; }).then(wizardDraw);
  await Promise.all([get("/api/optimize", "a"), get("/api/setup", "s")]);
}
function wizardRow(id, title, sub, on, tag = "") {
  return `<label class="wz-row"><input type="checkbox" class="ck" data-wz="${hE(id)}" ${on ? "checked" : ""}><span><b>${hE(title)}</b>${tag ? `<em>${hE(tag)}</em>` : ""}<small>${hE(sub)}</small></span></label>`;
}
function wizardDraw() {
  const a = WZ.a, s = WZ.s, box = hEl("wzBody"); if (!box) return;
  const keep = new Map([...box.querySelectorAll("[data-wz]")].map((x) => [x.dataset.wz, x.checked])), top = box.scrollTop;
  let h = "";
  if (!a) h += `<div class="wz-scan"><i></i><div><b>Изучаю компьютер</b><span>Процессор, память, диски, видеокарта, батарея, автозапуск. Около 30 секунд.</span></div></div>`;
  else if (a.error) h += none("Анализ не получился. Нажмите «Проверить снова».");
  else {
    const L = 2 * Math.PI * 44, col = a.score >= 80 ? "var(--hx-ok)" : a.score >= 55 ? "var(--hx-warn)" : "var(--hx-bad)";
    h += `<div class="wz-top"><div class="gauge wz-g"><svg viewBox="0 0 110 110"><circle cx="55" cy="55" r="44"/><circle class="v" cx="55" cy="55" r="44" style="stroke:${col}" stroke-dasharray="${L}" stroke-dashoffset="${L * (1 - a.score / 100)}"/></svg><div><b>${a.score}</b><small>из 100</small></div></div><table class="wz-pass"><tbody>${a.passport.map(([k, v]) => `<tr><td>${hE(k)}</td><td>${hE(v)}</td></tr>`).join("")}</tbody></table></div>`;
    h += `<h4>Что мешает</h4>` + (a.problems.map((p) => `<div class="wz-p ${p.sev}"><i></i><span><b>${hE(p.title)}</b><small>${hE(p.how)}</small></span></div>`).join("") || `<div class="wz-p ok"><i></i><span><b>Серьёзных проблем нет</b><small>Компьютер ${hE(a.tier_name)}, Джарвис будет работать в полную силу.</small></span></div>`);
  }
  h += `<h4>Чего не хватает Джарвису</h4>`;
  if (!s) h += none("Проверяю программы и библиотеки…");
  else if (s.error) h += none("Проверка не получилась.");
  else {
    const todo = s.items.filter((i) => i.status !== "ok"), auto = new Set(s.auto_ids || []);
    h += todo.length ? "" : `<div class="wz-p ok"><i></i><span><b>Всё на месте</b><small>Проверено пунктов: ${s.items.length}</small></span></div>`;
    h += todo.map((i) => (i.fix_id && auto.has(i.fix_id) ? wizardRow("fix:" + i.fix_id, i.fix || i.title, i.detail || i.title, i.status === "missing", i.size) : `<div class="wz-p ${i.status === "missing" ? "bad" : i.status === "warn" ? "warn" : "info"}"><i></i><span><b>${hE(i.title)}</b><small>${hE(i.fix || i.detail || "")}</small></span>${["groq", "gemini"].includes(i.id) ? '<button type="button" class="b s" data-wa="keys">Ввести ключ</button>' : ""}</div>`)).join("");
  }
  if (a && !a.error) {
    const main = a.plan.filter((p) => p.group !== "startup"), st = a.plan.filter((p) => p.group === "startup");
    h += `<h4>Оптимизация</h4>` + (main.map((p) => wizardRow(p.id, p.title, p.why, p.default, p.undo ? "" : "вернуть нельзя")).join("") || `<div class="wz-p ok"><i></i><span><b>Всё уже настроено</b><small>Питание, игровой режим и настройки Джарвиса в порядке.</small></span></div>`);
    if (st.length) h += `<details class="wz-d"><summary>Автозапуск: ${st.length}</summary>${st.map((p) => wizardRow(p.id, p.title, p.why, false)).join("")}</details>`;
  }
  h += `<h4>По желанию</h4><div class="bs"><button type="button" class="b" data-wa="tv">Найти телевизор Samsung</button><button type="button" class="b" data-wa="index">Изучить имена файлов</button>${a && a.can_undo ? '<button type="button" class="b" data-wa="undo">Отменить оптимизацию</button>' : ""}</div>`;
  if (WZ.log.length) h += `<h4>Сделано</h4>` + WZ.log.map((x) => `<div class="wz-p ${x.ok ? "ok" : "bad"}"><i></i><span><b>${hE(x.title)}</b><small>${hE(x.message || "")}</small></span></div>`).join("");
  box.innerHTML = h; box.scrollTop = top;
  box.querySelectorAll("[data-wz]").forEach((x) => { if (keep.has(x.dataset.wz)) x.checked = keep.get(x.dataset.wz); });
  hEl("wzGo").disabled = WZ.busy || !a || !s; hEl("wzGo").textContent = WZ.busy ? "Выполняю…" : "Сделать отмеченное";
  hEl("wzAgain").disabled = WZ.busy;
}
async function wizardGo() {
  const ids = [...document.querySelectorAll("#wzBody [data-wz]:checked")].map((x) => x.dataset.wz);
  if (!ids.length) { toast("Ничего не отмечено"); return; }
  const fixes = ids.filter((i) => i.startsWith("fix:")).map((i) => i.slice(4)), opt = ids.filter((i) => !i.startsWith("fix:"));
  WZ.busy = true; WZ.log = []; wizardDraw();
  try {
    if (opt.length) { WZ.log.push(...(await wzPost("/api/optimize", { ids: opt })).items); wizardDraw(); }
    if (fixes.length) {
      await api("/api/setup/run", "POST", { confirm: true, ids: fixes });
      const names = Object.fromEntries((WZ.s.items || []).map((i) => [i.fix_id, i.fix || i.title])), done = new Set();
      for (;;) {
        await wzSleep(2000);
        const l = await api("/api/setup/last");
        l.log.forEach((x) => { if (!done.has(x.id)) { done.add(x.id); WZ.log.push({ ok: x.ok, title: names[x.id] || x.id, message: x.message }); } });
        hEl("wzStat").textContent = l.running ? `Шаг ${l.log.length + 1} из ${l.total}: ${names[l.now] || l.now}` : "";
        wizardDraw();
        if (!l.running) break;
      }
    }
  } catch { WZ.log.push({ ok: false, title: "Нет связи с Джарвисом", message: "Проверьте, что он запущен, и нажмите «Проверить снова»." }); }
  WZ.busy = false; hEl("wzStat").textContent = "";
  const log = WZ.log; await wizardScan(); WZ.log = log; wizardDraw();
}
const ONB = { step: 0, persona: "tactical", cloud: true, voiceTimer: null, voiceDone: false };
const ONB_STEPS = ["Голос", "Характер и цвет", "Работа"];
function onbOpen() {
  const d = hEl("hxOnb"); if (d.open) return;
  ONB.step = 0; ONB.voiceDone = !!(D && D.voice_enrolled); onbDraw(); d.showModal();
}
function onbDraw() {
  const box = hEl("onbBody"), s = ONB.step;
  const dots = `<div class="onb-dots">${ONB_STEPS.map((_, i) => `<i class="${i <= s ? "on" : ""}"></i>`).join("")}</div>`;
  let h = dots;
  if (s === 0) {
    const done = ONB.voiceDone || (D && D.voice_enrolled);
    h += `<p class="onb-big">Джарвис будет слушать только вас. Прочитайте вслух три-четыре предложения: он запомнит ваш голос, и чужие голоса и телевизор его не разбудят.</p>`
      + `<button type="button" class="onb-voice" data-onb="voice" aria-label="Записать голос" ${done ? "disabled" : ""}><b>${done ? "Голос запомнен" : "Нажмите и читайте"}</b><span>${done ? "можно идти дальше" : "несколько секунд, пока горит запись"}</span></button>`;
  } else if (s === 1) {
    h += `<h4>Характер</h4>` + [["tactical", "Тактический", "Коротко, по делу, «сэр»"], ["coder", "Программист", "Технично, без лишних слов"], ["business", "Деловой", "Сроки, результат, решения"], ["friend", "Друг", "Тепло, шутки, разговор"]]
      .map(([id, t, d]) => `<button type="button" class="onb-opt" data-onb="persona" data-v="${id}" aria-pressed="${ONB.persona === id}"><span><b>${t}</b><small>${d}</small></span></button>`).join("")
      + `<h4 style="margin-top:14px">Цвет</h4><div class="sws">${PALETTES.map((p) => `<button type="button" style="background-color:${p.a}" data-acc="${p.id}" aria-label="${p.name}" title="${p.name}" aria-pressed="${C.accent === p.id}"></button>`).join("")}</div>`;
  } else {
    h += `<p class="onb-big">Как Джарвис будет работать?</p>`
      + `<button type="button" class="onb-opt" data-onb="cloud" data-v="1" aria-pressed="${ONB.cloud}"><span><b>С облаком (рекомендуется)</b><small>Речь и ответы быстрее, нужен бесплатный ключ Groq. Ключ вводится в «Настройки → Ключи».</small></span></button>`
      + `<button type="button" class="onb-opt" data-onb="cloud" data-v="0" aria-pressed="${!ONB.cloud}"><span><b>Без интернета</b><small>Всё на этом ноутбуке. Медленнее, зато никуда ничего не уходит.</small></span></button>`
      + `<p class="faint small" style="margin-top:12px">Дальше откроется анализ ноутбука: там можно отметить оптимизацию.</p>`;
  }
  box.innerHTML = h;
  hEl("onbBack").hidden = s === 0;
  hEl("onbNext").textContent = s === 2 ? "Готово, к анализу" : "Дальше";
  hEl("onbNext").disabled = s === 0 && !(ONB.voiceDone || (D && D.voice_enrolled));
  hEl("onbSub").textContent = `Шаг ${s + 1} из 3: ${ONB_STEPS[s]}`;
  hEl("onbStat").textContent = s === 0 ? "Запись голоса" + (ONB.voiceDone ? "" : " ещё не сделана") : "";
}
async function onbVoice() {
  hEl("onbStat").textContent = "Говорите…";
  await api("/api/voice/enroll", "POST");
  const t0 = Date.now();
  while (Date.now() - t0 < 90000) {
    await new Promise((r) => setTimeout(r, 1500));
    const d = await (await fetch("/api/hud")).json();
    D = d;
    if (d.voice_enrolled) { ONB.voiceDone = true; onbDraw(); toast("Голос запомнен"); return; }
  }
  hEl("onbStat").textContent = "Не расслышал. Попробуйте ещё раз.";
}
async function onbNext() {
  if (ONB.step === 1) {
    await wzPost("/api/persona", { persona: ONB.persona });
    save();
  }
  if (ONB.step < 2) { ONB.step++; onbDraw(); return; }
  await wzPost("/api/settings", { section: "cloud", key: "enabled", value: ONB.cloud });
  await wzPost("/api/settings", { section: "ui", key: "onboarded", value: true });
  hEl("hxOnb").close();
  wizardOpen();
}
function onbBind() {
  hEl("onbNext").onclick = onbNext;
  hEl("onbBack").onclick = () => { if (ONB.step > 0) { ONB.step--; onbDraw(); } };
  hEl("hxOnb").addEventListener("click", (e) => {
    const b = e.target.closest("[data-onb]"); if (!b) return;
    const k = b.dataset.onb;
    if (k === "voice") onbVoice();
    if (k === "persona") { ONB.persona = b.dataset.v; onbDraw(); }
    if (k === "cloud") { ONB.cloud = b.dataset.v === "1"; onbDraw(); }
    if (b.dataset.acc) { C.accent = b.dataset.acc; save(); applyPalette(); onbDraw(); }
  });
}
function wizardBind() {
  onbBind();
  hEl("wzGo").onclick = wizardGo; hEl("wzAgain").onclick = wizardScan;
  hEl("wzClose").onclick = () => hEl("hxWiz").close();
  hEl("hxWiz").addEventListener("close", () => { wzPost("/api/setup/done").catch(() => {}); if (D) D.first_run = false; });
  hEl("wzBody").addEventListener("click", async (e) => {
    const b = e.target.closest("[data-wa]"); if (!b) return;
    const w = b.dataset.wa;
    if (w === "keys") { hEl("hxWiz").close(); location.hash = "#settings/keys"; }
    if (w === "tv") { b.disabled = true; b.textContent = "Ищу в домашней сети…"; const r = await wzPost("/api/find-tv"); WZ.log.push({ ok: r.found, title: "Телевизор", message: r.message }); wizardDraw(); }
    if (w === "index") UI.ui_index();
    if (w === "undo") { const r = await wzPost("/api/optimize/undo"); toast("Возвращено настроек: " + r.done.length); wizardScan(); }
  });
}
