/* Jarvis core: the sphere, the waveform, the rings and the load arcs.
 * Drawn on one canvas. The shape around the sphere depends on the chosen palette (see app.js).
 * Public API: JarvisCore.mount(canvas), JarvisCore.set(state), JarvisCore.setShape(name, rgb). */
(function () {
  "use strict";
  const REDUCE = matchMedia("(prefers-reduced-motion: reduce)").matches;
  const N = 160;
  const NOISE = Array.from({ length: N }, (_, i) => 0.5 + 0.5 * Math.sin(i * 1.7) * Math.cos(i * 0.61));
  const DOTS = Array.from({ length: 260 }, (_, i) => {
    const y = 1 - (2 * (i + 0.5)) / 260, r = Math.sqrt(1 - y * y), th = i * 2.399963;
    return [r * Math.cos(th), y, r * Math.sin(th)];
  });
  const st = { canvas: null, g: null, status: "starting", level: 0, sys: null, gpu: null, cloud: {}, lite: false,
    game: false, shape: "rings", rgb: "0,245,255", lv: 0, last: 0, visible: true };

  function fit() {
    const c = st.canvas; if (!c) return false;
    const d = Math.min(1.5, devicePixelRatio || 1), r = c.getBoundingClientRect();
    if (!r.width) return false;
    const w = Math.round(r.width * d), h = Math.round(r.height * d);
    if (c.width !== w || c.height !== h) { c.width = w; c.height = h; }
    return true;
  }
  const clamp = (v, a, b) => Math.max(a, Math.min(b, v));

  function arcText(g, text, cx, cy, r, a0, size) {
    g.font = `500 ${size}px "JetBrains Mono", ui-monospace, Consolas, monospace`;
    g.textAlign = "center"; g.textBaseline = "middle";
    const step = (size * 0.86) / r;
    for (let i = 0; i < text.length; i++) {
      const a = a0 + i * step;
      g.save(); g.translate(cx + Math.cos(a) * r, cy + Math.sin(a) * r); g.rotate(a + Math.PI / 2);
      g.fillText(text[i], 0, 0); g.restore();
    }
  }

  // The geometry that goes with each palette: the core is shared, the frame around it is not.
  function shapeLayer(g, c, R0, s, A) {
    if (st.shape === "dots") {                              // dotted globe, turning
      const Rg = R0 * 0.505, ca = Math.cos(s * 0.22), sa = Math.sin(s * 0.22), tilt = 0.28, ct = Math.cos(tilt), sn = Math.sin(tilt);
      for (const [x0, y0, z0] of DOTS) {
        const x1 = x0 * ca + z0 * sa, z1 = -x0 * sa + z0 * ca;
        const y2 = y0 * ct - z1 * sn, z2 = y0 * sn + z1 * ct;
        const front = (z2 + 1) / 2;
        g.fillStyle = `rgba(${A},${0.18 + front * 0.72})`;
        g.beginPath(); g.arc(c + x1 * Rg, c + y2 * Rg, R0 * 0.0068 * (0.55 + front), 0, 7); g.fill();
      }
    } else if (st.shape === "grid") {                       // meridians, parallels and a scan line
      const Rg = R0 * 0.52; g.lineWidth = Math.max(1, R0 / 380);
      for (let k = 0; k < 6; k++) {
        const a = k * Math.PI / 6 + s * 0.18;
        g.strokeStyle = `rgba(${A},${0.13 + 0.1 * Math.cos(a)})`;
        g.beginPath(); g.ellipse(c, c, Rg * Math.abs(Math.cos(a)), Rg, 0, 0, 7); g.stroke();
      }
      for (let j = -2; j <= 2; j++) {
        const yy = c + Math.sin(j * 0.4) * Rg, rr = Math.cos(j * 0.4) * Rg;
        g.strokeStyle = `rgba(${A},0.14)`; g.beginPath(); g.ellipse(c, yy, rr, rr * 0.18, 0, 0, 7); g.stroke();
      }
      const sy = c - Rg + ((s * 0.35) % 1) * 2 * Rg, half = Math.sqrt(Math.max(0, Rg * Rg - (sy - c) * (sy - c)));
      const scan = g.createLinearGradient(0, sy - 6, 0, sy + 6);
      scan.addColorStop(0, `rgba(${A},0)`); scan.addColorStop(0.5, `rgba(${A},0.55)`); scan.addColorStop(1, `rgba(${A},0)`);
      g.fillStyle = scan; g.fillRect(c - half, sy - 6, half * 2, 12);
    } else if (st.shape === "shield") {                     // six segments with gaps, turning slowly
      const r = R0 * 0.605, gap = 0.16;
      for (let k = 0; k < 6; k++) {
        const a0 = k * Math.PI / 3 + s * 0.12 + gap / 2;
        g.strokeStyle = k % 2 ? `rgba(${A},0.85)` : "rgba(255,170,0,0.8)";
        g.lineWidth = R0 * 0.012; g.lineCap = "butt";
        g.beginPath(); g.arc(c, c, r, a0, a0 + Math.PI / 3 - gap); g.stroke();
      }
      g.lineWidth = Math.max(1, R0 / 420); g.strokeStyle = `rgba(${A},0.35)`;
      g.setLineDash([3, 6]); g.beginPath(); g.arc(c, c, R0 * 0.625, -s * 0.4, -s * 0.4 + Math.PI * 2 * 0.9); g.stroke(); g.setLineDash([]);
    } else if (st.shape === "orbits") {                     // three tilted rings with satellites
      for (let k = 0; k < 3; k++) {
        const tilt = k * Math.PI / 3 + 0.35, ra = R0 * (0.66 + k * 0.03), rb = ra * (0.36 + 0.1 * k);
        g.strokeStyle = `rgba(${A},0.22)`; g.lineWidth = Math.max(1, R0 / 420);
        g.beginPath(); g.ellipse(c, c, ra, rb, tilt, 0, 7); g.stroke();
        const a = s * (0.9 + k * 0.35) + k;
        const x = Math.cos(a) * ra, y = Math.sin(a) * rb;
        const px = c + x * Math.cos(tilt) - y * Math.sin(tilt), py = c + x * Math.sin(tilt) + y * Math.cos(tilt);
        g.fillStyle = k === 1 ? "rgba(245,158,11,0.95)" : `rgba(${A},0.95)`;
        g.beginPath(); g.arc(px, py, R0 * 0.014, 0, 7); g.fill();
      }
    }
  }

  function draw(t) {
    const orb = st.canvas, g = st.g;
    const busy = (st.status !== "listening" && st.status !== "starting" && st.status !== "game") || st.lv > 0.12 || st.level > 0.15;
    const every = st.game ? 480 : st.lite ? 110 : busy ? 24 : 48;
    if (t - st.last < every) return;
    st.last = t;
    if (!fit()) return;
    const W = orb.width, c = W / 2, R0 = W / 2, s = REDUCE ? 0 : t / 1000, A = st.rgb;
    const sys = st.sys || { cpu: 0, ram_pct: 0 };
    const want = st.status === "speaking" ? 0.42 + 0.28 * Math.abs(Math.sin(s * 7.3) * Math.sin(s * 3.1))
      : st.status === "thinking" ? 0.18 + 0.06 * Math.sin(s * 5)
      : st.status === "recording" ? Math.max(0.1, st.level) : Math.min(0.35, st.level * 0.6);
    st.lv += (want - st.lv) * 0.18;
    const LV = st.lv;
    g.clearRect(0, 0, W, W);
    const halo = g.createRadialGradient(c, c, R0 * 0.3, c, c, R0);
    halo.addColorStop(0, `rgba(${A},${0.17 + LV * 0.25})`); halo.addColorStop(1, `rgba(${A},0)`);
    g.fillStyle = halo; g.fillRect(0, 0, W, W);

    g.lineCap = "round"; g.lineWidth = Math.max(1, W / 420);
    for (let i = 0; i < N; i++) {                           // 1. circular waveform
      const a = i / N * Math.PI * 2 - Math.PI / 2;
      const k = NOISE[(i + Math.floor(s * 9)) % N] * 0.6 + NOISE[(i * 3 + Math.floor(s * 14)) % N] * 0.4;
      const len = R0 * (0.012 + k * (0.018 + LV * 0.11)), r1 = R0 * 0.87;
      g.strokeStyle = `rgba(${A},${0.3 + k * 0.4 + LV * 0.3})`;
      g.beginPath(); g.moveTo(c + Math.cos(a) * r1, c + Math.sin(a) * r1);
      g.lineTo(c + Math.cos(a) * (r1 + len), c + Math.sin(a) * (r1 + len)); g.stroke();
    }
    for (let i = 0; i < 72; i++) {                          // 2. ticks
      const a = i / 72 * Math.PI * 2 + s * 0.05, big = i % 6 === 0;
      g.strokeStyle = `rgba(${A},${big ? 0.7 : 0.22})`; g.lineWidth = big ? 1.6 : 1;
      const r1 = R0 * 0.835, r2 = R0 * (big ? 0.805 : 0.82);
      g.beginPath(); g.moveTo(c + Math.cos(a) * r1, c + Math.sin(a) * r1); g.lineTo(c + Math.cos(a) * r2, c + Math.sin(a) * r2); g.stroke();
    }
    const cloud = st.cloud || {}, good = st.sys && !cloud.error && sys.cpu < 92;
    const label = (cloud.groq || cloud.gemini ? "CLOUD HYBRID" : "LOCAL MODE") + " · SYSTEM STATUS: " + (good ? "OPTIMAL" : st.sys ? "ATTENTION" : "…");
    const fs = Math.max(8, R0 * 0.04);
    g.fillStyle = good ? `rgba(${A},0.82)` : "rgba(255,176,32,0.9)";
    arcText(g, label, c, c, R0 * 0.752, s * 0.07 - 2.4, fs);
    arcText(g, label, c, c, R0 * 0.752, s * 0.07 - 2.4 + Math.PI, fs);

    const arcs = st.sys ? [[sys.cpu, `rgb(${A})`, "CPU"], [sys.ram_pct, "#a78bff", "RAM"], [st.gpu ? st.gpu.util : 0, "#37e0a0", "GPU"]] : [];
    arcs.forEach(([v, col, nm], i) => {                     // 3. load arcs
      const a0 = -Math.PI / 2 + i * Math.PI * 2 / 3 + 0.12, span = Math.PI * 2 / 3 - 0.24, r = R0 * 0.672;
      g.lineWidth = R0 * 0.022; g.lineCap = "butt";
      g.strokeStyle = "rgba(255,255,255,0.07)"; g.beginPath(); g.arc(c, c, r, a0, a0 + span); g.stroke();
      g.strokeStyle = col; g.beginPath(); g.arc(c, c, r, a0, a0 + span * clamp(v, 0, 100) / 100); g.stroke();
      g.fillStyle = "rgba(255,255,255,0.85)";
      arcText(g, `${nm} ${Math.round(v)}%`, c, c, R0 * 0.625, a0 + 0.03, Math.max(9, R0 * 0.038));
    });

    const m = g.createConicGradient(s * 0.25, c, c);        // 4. metal ring
    ["#1a222c", "#8fa2b5", "#202a35", "#0c1219", "#c9d7e4", "#1a222c"].forEach((q, i) => m.addColorStop(i / 5, q));
    g.strokeStyle = m; g.lineWidth = R0 * 0.03; g.beginPath(); g.arc(c, c, R0 * 0.565, 0, 7); g.stroke();
    g.strokeStyle = `rgba(${A},${0.55 + LV * 0.4})`; g.lineWidth = 1.4; g.beginPath(); g.arc(c, c, R0 * 0.543, 0, 7); g.stroke();

    const Rs = R0 * 0.53, ball = g.createRadialGradient(c - Rs * 0.35, c - Rs * 0.45, Rs * 0.05, c, c, Rs);   // 5. glass sphere
    ball.addColorStop(0, "#1c2b38"); ball.addColorStop(0.45, "#0a121a"); ball.addColorStop(1, "#020407");
    g.save(); g.beginPath(); g.arc(c, c, Rs, 0, 7); g.clip(); g.fillStyle = ball; g.fillRect(c - Rs, c - Rs, Rs * 2, Rs * 2);
    const low = g.createRadialGradient(c, c + Rs * 0.9, 0, c, c + Rs * 0.9, Rs * 1.1);
    low.addColorStop(0, `rgba(${A},${0.26 + LV * 0.35})`); low.addColorStop(1, `rgba(${A},0)`);
    g.fillStyle = low; g.fillRect(c - Rs, c - Rs, Rs * 2, Rs * 2);
    [[`rgba(${A},0.95)`, 2.1, 1.6, 0], ["rgba(167,139,255,0.75)", 2.9, -1.2, 1.4]].forEach(([col, fr, sp, ph]) => {
      g.strokeStyle = col; g.lineWidth = Math.max(1.3, R0 * 0.0075); g.beginPath();
      for (let x = -1; x <= 1.001; x += 0.03) {
        const y = Math.sin(x * Math.PI * fr + s * sp * 2 + ph) * Rs * (0.05 + LV * 0.34) * Math.cos(x * Math.PI / 2);
        const px = c + x * Rs, py = c + Rs * 0.44 + y;
        x === -1 ? g.moveTo(px, py) : g.lineTo(px, py);
      }
      g.stroke();
    });
    g.save(); g.translate(c - Rs * 0.12, c - Rs * 0.78); g.scale(1, 0.46);
    const hi = g.createRadialGradient(0, 0, 0, 0, 0, Rs * 0.8);
    hi.addColorStop(0, "rgba(225,248,255,0.3)"); hi.addColorStop(0.6, "rgba(225,248,255,0.07)"); hi.addColorStop(1, "rgba(225,248,255,0)");
    g.fillStyle = hi; g.fillRect(-Rs, -Rs, Rs * 2, Rs * 2); g.restore();
    g.restore();
    if (!st.lite) shapeLayer(g, c, R0, s, A);
    document.querySelectorAll("[data-vu]").forEach((v) => [...v.children].forEach((b, i) => b.classList.toggle("on", st.level * 18 > i)));
  }

  function loop(t) {
    requestAnimationFrame(loop);
    if (!st.canvas || document.hidden || !st.visible) return;
    draw(t);
  }

  window.JarvisCore = {
    mount(canvas) {
      st.canvas = canvas; st.g = canvas.getContext("2d");
      const again = () => { fit(); };
      addEventListener("resize", again); again();
      requestAnimationFrame(loop);
    },
    set(next) { Object.assign(st, next); },
    setShape(name, rgb) { st.shape = name; if (rgb) st.rgb = rgb; },
    setVisible(v) { st.visible = !!v; },
  };
})();
