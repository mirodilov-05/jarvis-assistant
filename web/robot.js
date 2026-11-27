/* The robot mode of the home screen: a small chrome robot whose face shows what Jarvis feels.
 * Feelings come from the server (/api/hud → emotion, cognition/emotion.py): rudeness hurts him, an apology makes him
 * forgive, praise pleases him, your sadness makes him sad. Jarvis's state (listening, thinking, speaking) and the
 * loudness of his voice move the face too. Public: Robot.html(), mount(), unmount(), onReply(text),
 * setStatus(s), setLevel(v). */
(function () {
  "use strict";
  const $ = (s, r = document) => r.querySelector(s);
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const R = { on: false, emo: "neutral", status: "listening", level: 0, timer: 0, blinkT: 0, raf: 0, lastSay: "" };
  const COLORS = { neutral: "#4f7cff", happy: "#38c8ff", laugh: "#38c8ff", love: "#ff5c9a", sad: "#6f8dff", cry: "#6f8dff",
    offended: "#ff6b5b", angry: "#ff3b3b", scared: "#ffd24a", surprised: "#ffe07a", confused: "#b48cff", sleepy: "#3f5590", proud: "#ffc94a" };
  const POKES = [["pet", "Погладить", "♥"], ["praise", "Похвалить", "★"], ["joke", "Пошутить", "☺"], ["wow", "Удивить", "!"],
    ["sad", "Мне грустно", "☁"], ["scold", "Поругать", "✕"], ["sorry", "Извиниться", "✓"]];

  const eye = (x) => `<g class="eye" transform="translate(${x} 196)">
      <rect class="e-open" x="-16" y="-34" width="32" height="68" rx="16"/>
      <path class="e-happy" d="M-20 8 Q0 -26 20 8"/>
      <path class="e-heart" d="M0 18 C-26 0 -22 -24 -8 -24 C-2 -24 0 -18 0 -14 C0 -18 2 -24 8 -24 C22 -24 26 0 0 18Z"/>
      <circle class="e-round" r="23"/>
      <rect class="e-flat" x="-20" y="-4" width="40" height="8" rx="4"/>
    </g>`;
  function svg() {
    return `<svg class="robot-svg" viewBox="0 0 400 450" role="img" aria-labelledby="robotTitle">
      <title id="robotTitle">Робот Джарвис</title>
      <defs>
        <radialGradient id="rbChrome" cx="35%" cy="28%" r="80%"><stop offset="0" stop-color="#ffffff"/><stop offset=".25" stop-color="#dfe5ec"/><stop offset=".6" stop-color="#7d8794"/><stop offset=".85" stop-color="#2c333c"/><stop offset="1" stop-color="#11151a"/></radialGradient>
        <linearGradient id="rbScreen" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#0d1018"/><stop offset="1" stop-color="#020306"/></linearGradient>
        <radialGradient id="rbFoot" cx="40%" cy="30%" r="80%"><stop offset="0" stop-color="#f2f5f8"/><stop offset=".6" stop-color="#8a939e"/><stop offset="1" stop-color="#1e242b"/></radialGradient>
        <filter id="rbGlow" x="-50%" y="-50%" width="200%" height="200%"><feGaussianBlur stdDeviation="5" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter>
      </defs>
      <ellipse class="rb-shadow" cx="200" cy="428" rx="118" ry="14"/>
      <g class="rb-bot">
        <g class="rb-feet"><path d="M128 352 q-6 52 34 58 q26 2 30 -22 l2 -36z" fill="url(#rbFoot)"/><path d="M272 352 q6 52 -34 58 q-26 2 -30 -22 l-2 -36z" fill="url(#rbFoot)"/></g>
        <g class="rb-body">
          <circle cx="200" cy="210" r="156" fill="url(#rbChrome)"/>
          <ellipse cx="150" cy="104" rx="70" ry="26" fill="#fff" opacity=".28"/>
          <g class="rb-ear"><circle cx="46" cy="214" r="18"/><circle class="ring" cx="46" cy="214" r="12"/></g>
          <g class="rb-ear"><circle cx="354" cy="214" r="18"/><circle class="ring" cx="354" cy="214" r="12"/></g>
        </g>
        <g class="rb-head">
          <rect class="rb-screen" x="88" y="116" width="224" height="174" rx="84" fill="url(#rbScreen)"/>
          <path class="rb-glare" d="M112 150 q40 -30 110 -26" stroke="#fff" stroke-opacity=".12" stroke-width="8" fill="none" stroke-linecap="round"/>
          <g class="rb-face" filter="url(#rbGlow)">
            <g class="rb-eyes">${eye(160)}${eye(240)}</g>
            <path class="rb-brow l" d="M136 150 L182 160"/><path class="rb-brow r" d="M264 150 L218 160"/>
            <rect class="rb-mouth" x="184" y="252" width="32" height="6" rx="3"/>
            <path class="rb-smile" d="M178 248 Q200 266 222 248"/>
            <path class="rb-frown" d="M180 260 Q200 244 220 260"/>
            <g class="rb-tears"><path class="t l" d="M152 236 q-6 10 0 14 q6 -4 0 -14z"/><path class="t r" d="M248 236 q-6 10 0 14 q6 -4 0 -14z"/></g>
            <g class="rb-blush"><ellipse cx="126" cy="238" rx="14" ry="7"/><ellipse cx="274" cy="238" rx="14" ry="7"/></g>
          </g>
          <text class="rb-mark q" x="296" y="128">?</text>
          <text class="rb-mark z" x="300" y="120">Z</text>
          <g class="rb-dots"><circle cx="180" cy="270" r="4"/><circle cx="200" cy="270" r="4"/><circle cx="220" cy="270" r="4"/></g>
        </g>
      </g>
    </svg>`;
  }

  function html() {
    return `<div class="robot-stage" id="robotStage">
        <div class="robot-box">
          <div class="robot-bubble" id="robotBubble" aria-live="polite"></div>
          <div class="robot-wrap" id="robotWrap" data-emo="neutral" data-status="listening">${svg()}</div>
          <div class="robot-state"><span id="robotStatus">слушаю</span></div>
        </div>
        <aside class="robot-side">
          <div class="emo-card"><div class="sub">Сейчас Джарвис</div><b id="emoLabel">спокоен</b><div class="sub" id="emoWhy">Скажите «Джарвис» и поговорите с ним.</div><div class="emo-meter"><i id="emoMeter"></i></div></div>
          <div class="emo-card"><div class="sub">Ваше настроение</div><b id="userMood">спокойно</b><div class="sub" id="userWhy">по словам и по тону голоса</div></div>
          <div class="poke-grid" role="group" aria-label="Показать эмоции">${POKES.map(([k, n, i]) => `<button type="button" class="btn sm" data-poke="${k}"><span aria-hidden="true">${i}</span> ${n}</button>`).join("")}</div>
          <p class="sub robot-note">Робот понимает настроение по словам и по тону голоса относительно вашего обычного голоса. Грубость его обижает, а повторная доводит до слёз; «прости» — и он простит. Похвала радует, шутка смешит, ваша грусть огорчает и его.</p>
        </aside>
      </div>`;
  }

  function apply(st) {
    if (!R.on || !st) return;
    const wrap = $("#robotWrap"); if (!wrap) return;
    R.emo = st.emotion || "neutral";
    wrap.dataset.emo = R.emo;
    wrap.style.setProperty("--emo", COLORS[R.emo] || COLORS.neutral);
    const set = (id, t) => { const e = $("#" + id); if (e) e.textContent = t; };
    set("emoLabel", st.label || "спокоен");
    set("emoWhy", st.reason ? `потому что: ${st.reason}` : "всё хорошо");
    set("userMood", st.user_label || "спокойно");
    set("userWhy", st.user_reason || "по словам и по тону голоса");
    const m = $("#emoMeter"); if (m) { m.style.width = `${Math.round((st.intensity || 0.2) * 100)}%`; m.style.background = COLORS[R.emo] || ""; }
  }
  function say(text) {
    const b = $("#robotBubble"); if (!b || !text) return;
    b.textContent = text; b.classList.add("on");
    clearTimeout(R.sayT); R.sayT = setTimeout(() => b.classList.remove("on"), Math.min(14000, 3000 + text.length * 60));
  }
  async function refresh() {
    try { const st = await (await fetch("/api/robot")).json(); apply(st); } catch { /* the next poll */ }
  }
  function frame() {
    if (!R.on) return;
    R.raf = requestAnimationFrame(frame);
    const wrap = $("#robotWrap"); if (!wrap) return;
    const now = performance.now();
    if (now > R.blinkT) {                                          // a blink every few seconds
      wrap.classList.add("blink"); setTimeout(() => wrap.classList.remove("blink"), 140);
      R.blinkT = now + 2200 + Math.random() * 3800;
    }
    const lv = R.status === "speaking" ? Math.max(R.level, 0.25 + 0.25 * Math.abs(Math.sin(now / 90))) : R.level;
    wrap.style.setProperty("--talk", lv.toFixed(2));
  }
  function look(e) {
    const wrap = $("#robotWrap"); if (!wrap) return;
    const r = wrap.getBoundingClientRect(), cx = r.left + r.width / 2, cy = r.top + r.height * 0.45;
    const dx = Math.max(-1, Math.min(1, (e.clientX - cx) / (r.width * 1.2))), dy = Math.max(-1, Math.min(1, (e.clientY - cy) / (r.height * 1.2)));
    wrap.style.setProperty("--lx", `${(dx * 14).toFixed(1)}px`); wrap.style.setProperty("--ly", `${(dy * 9).toFixed(1)}px`);
  }
  async function poke(what) {
    try {
      const r = await fetch("/api/robot/poke", { method: "POST", headers: { "Content-Type": "application/json", "X-Jarvis": "1" }, body: JSON.stringify({ what }) });
      const d = await r.json(); apply(d.emotion); if (d.say) say(d.say);
    } catch (e) { /* offline: nothing to show */ }
  }
  const settingsRobot = (on) => fetch("/api/settings", { method: "POST", headers: { "Content-Type": "application/json", "X-Jarvis": "1" },
    body: JSON.stringify({ section: "ui", key: "robot_mode", value: on }) }).catch(() => {});

  window.Robot = {
    html,
    mount() {
      R.on = true; R.blinkT = performance.now() + 1500;
      const stage = $("#robotStage");
      stage.addEventListener("click", (e) => { const b = e.target.closest("[data-poke]"); if (b) poke(b.dataset.poke); });
      addEventListener("pointermove", look);
      apply(window.JV?.STATE?.hud?.emotion); refresh();
      clearInterval(R.timer); R.timer = setInterval(() => { if (!document.hidden) refresh(); }, 2000);
      cancelAnimationFrame(R.raf); R.raf = requestAnimationFrame(frame);
      this.setStatus(R.status);
      settingsRobot(true);
    },
    unmount() {
      if (!R.on) return;
      R.on = false; clearInterval(R.timer); cancelAnimationFrame(R.raf); removeEventListener("pointermove", look);
      settingsRobot(false);
    },
    onReply(text) { if (R.on) { say(text); setTimeout(refresh, 300); } },
    setStatus(s) {
      R.status = s || "listening";
      const wrap = $("#robotWrap"); if (wrap) wrap.dataset.status = R.status;
      const t = { listening: "слушаю «Джарвис»", recording: "слушаю вас", thinking: "думаю…", speaking: "говорю", starting: "просыпаюсь", game: "игровой режим" }[R.status] || R.status;
      const el = $("#robotStatus"); if (el) el.textContent = t;
    },
    setLevel(v) { R.level = Math.max(0, Math.min(1, v || 0)); },
  };
})();
