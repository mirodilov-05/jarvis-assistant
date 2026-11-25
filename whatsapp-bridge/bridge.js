// Jarvis <-> WhatsApp bridge. Links to your WhatsApp as a "linked device" (like
// WhatsApp Web) and exposes a tiny HTTP API on 127.0.0.1 only.
//   GET  /status            -> { state: "starting"|"qr"|"connected"|"logged_out", qr: dataURL, me }
//   GET  /unread            -> [{ name, jid, unread, last }]
//   GET  /chat?name=...     -> { name, messages: [{ fromMe, text, ts }] }
//   POST /send {to, text}   -> { ok, name }
//   POST /logout
// Session: ../data/whatsapp-auth  ·  Recent messages cache: ../data/whatsapp-store.json
const http = require("http");
const fs = require("fs");
const path = require("path");
const QRCode = require("qrcode");
const pino = require("pino");
const {
  default: makeWASocket, useMultiFileAuthState, DisconnectReason, Browsers, fetchLatestBaileysVersion, jidNormalizedUser,
} = require("@whiskeysockets/baileys");

const PORT = 50779;
const DATA = path.join(__dirname, "..", "data");
const AUTH_DIR = path.join(DATA, "whatsapp-auth");
const STORE_FILE = path.join(DATA, "whatsapp-store.json");
const logger = pino({ level: "silent" });

let sock = null;
let state = { state: "starting", qr: null, me: null };
let store = { chats: {}, contacts: {} };
try { store = JSON.parse(fs.readFileSync(STORE_FILE, "utf8")); } catch (_) {}
const saveStore = () => fs.writeFile(STORE_FILE, JSON.stringify(store), () => {});
setInterval(saveStore, 20000);

function textOf(msg) {
  const m = msg.message || {};
  return m.conversation || m.extendedTextMessage?.text || m.imageMessage?.caption || m.videoMessage?.caption
    || (m.imageMessage ? "[фото]" : m.videoMessage ? "[видео]" : m.audioMessage ? "[голосовое]"
      : m.documentMessage ? "[документ]" : m.stickerMessage ? "[стикер]" : "");
}
function chatName(jid) {
  const c = store.chats[jid] || {};
  const ct = store.contacts[jid] || {};
  return c.name || ct.name || ct.notify || ct.verifiedName || jid.split("@")[0];
}
function chat(jid) {
  return (store.chats[jid] ||= { name: null, unread: 0, messages: [] });
}
function addMessage(msg, countUnread) {
  const jid = msg.key.remoteJid;
  if (!jid || jid === "status@broadcast" || jid.endsWith("@newsletter")) return;
  const text = textOf(msg);
  if (!text) return;
  const c = chat(jid);
  if (!msg.key.fromMe && msg.pushName && !jid.endsWith("@g.us")) {
    (store.contacts[jid] ||= {}).notify ||= msg.pushName;
  }
  c.messages.push({ fromMe: !!msg.key.fromMe, text: text.slice(0, 500), ts: Number(msg.messageTimestamp) || Date.now() / 1000,
                    sender: msg.key.fromMe ? "me" : (msg.pushName || "") });
  if (c.messages.length > 30) c.messages.splice(0, c.messages.length - 30);
  if (countUnread && !msg.key.fromMe) c.unread = (c.unread || 0) + 1;
  if (msg.key.fromMe) c.unread = 0;
}

async function start() {
  const { state: auth, saveCreds } = await useMultiFileAuthState(AUTH_DIR);
  let version;
  try { ({ version } = await fetchLatestBaileysVersion()); } catch (_) {}
  sock = makeWASocket({
    auth, logger, version, browser: Browsers.windows("Jarvis"), printQRInTerminal: false,
    markOnlineOnConnect: false, syncFullHistory: false,
  });
  sock.ev.on("creds.update", saveCreds);
  sock.ev.on("connection.update", async (u) => {
    if (u.qr) {
      state = { ...state, state: "qr", qr: await QRCode.toDataURL(u.qr, { margin: 4, width: 360 }), qrAt: Date.now() };
      console.log(new Date().toISOString(), "new QR");
    }
    if (u.isNewLogin) console.log(new Date().toISOString(), "scanned: linked, reconnecting");
    if (u.lastDisconnect) console.log(new Date().toISOString(), "closed", u.lastDisconnect?.error?.output?.statusCode, u.lastDisconnect?.error?.message);
    if (u.connection === "open") {
      state = { state: "connected", qr: null, me: sock.user ? { id: sock.user.id, name: sock.user.name } : null };
    }
    if (u.connection === "close") {
      const code = u.lastDisconnect?.error?.output?.statusCode;
      if (code === DisconnectReason.loggedOut) {
        state = { state: "logged_out", qr: null, me: null };
        fs.rmSync(AUTH_DIR, { recursive: true, force: true });
        setTimeout(start, 2000);
      } else {
        state = { ...state, state: "starting", qr: null };   // the old code no longer works: don't show it
        setTimeout(start, 3000);
      }
    }
  });
  sock.ev.on("messaging-history.set", ({ chats = [], contacts = [], messages = [] }) => {
    for (const c of contacts) store.contacts[c.id] = { ...(store.contacts[c.id] || {}), ...c };
    for (const c of chats) {
      const s = chat(c.id);
      if (c.name) s.name = c.name;
      if (typeof c.unreadCount === "number") s.unread = c.unreadCount;
    }
    for (const m of messages) addMessage(m, false);
  });
  sock.ev.on("chats.upsert", (chats) => chats.forEach((c) => {
    const s = chat(c.id);
    if (c.name) s.name = c.name;
    if (typeof c.unreadCount === "number") s.unread = c.unreadCount;
  }));
  sock.ev.on("chats.update", (updates) => updates.forEach((c) => {
    const s = chat(c.id);
    if (c.name) s.name = c.name;
    if (typeof c.unreadCount === "number") s.unread = Math.max(0, c.unreadCount < 0 ? 0 : c.unreadCount);
  }));
  sock.ev.on("contacts.upsert", (cs) => cs.forEach((c) => { store.contacts[c.id] = { ...(store.contacts[c.id] || {}), ...c }; }));
  sock.ev.on("contacts.update", (cs) => cs.forEach((c) => { store.contacts[c.id] = { ...(store.contacts[c.id] || {}), ...c }; }));
  sock.ev.on("groups.update", (gs) => gs.forEach((g) => { if (g.subject) chat(g.id).name = g.subject; }));
  sock.ev.on("messages.upsert", ({ messages, type }) => messages.forEach((m) => addMessage(m, type === "notify")));
}

function findChat(name) {
  const q = String(name || "").toLowerCase().trim();
  if (/^\+?\d{7,15}$/.test(q.replace(/[\s-]/g, ""))) return q.replace(/\D/g, "") + "@s.whatsapp.net";
  const variants = [q, q.replace(/(е|у|ю|ой|ей|и|ga|ka|qa|ni)$/, ""), q.replace(/(е|у|ю)$/, "а")].filter(Boolean);
  const all = new Set([...Object.keys(store.chats), ...Object.keys(store.contacts)]);
  const entries = [...all].filter((j) => j.endsWith("@s.whatsapp.net") || j.endsWith("@g.us"))
    .map((j) => [j, chatName(j).toLowerCase()]);
  for (const v of variants) {
    const exact = entries.find(([, n]) => n === v) || entries.find(([, n]) => n.startsWith(v))
      || entries.find(([, n]) => n.split(/\s+/).includes(v)) || entries.find(([, n]) => n.includes(v));
    if (exact) return exact[0];
  }
  return null;
}

function json(res, code, body) {
  res.writeHead(code, { "Content-Type": "application/json; charset=utf-8" });
  res.end(JSON.stringify(body));
}

http.createServer(async (req, res) => {
  const url = new URL(req.url, `http://127.0.0.1:${PORT}`);
  try {
    if (req.method === "GET" && url.pathname === "/status") return json(res, 200, state);
    if (req.method === "GET" && url.pathname === "/unread") {
      const list = Object.entries(store.chats).filter(([j, c]) => c.unread > 0 && !j.endsWith("@broadcast"))
        .map(([j, c]) => ({ jid: j, name: chatName(j), unread: c.unread, group: j.endsWith("@g.us"),
                            last: (c.messages.filter((m) => !m.fromMe).slice(-1)[0] || {}).text || "" }))
        .sort((a, b) => b.unread - a.unread);
      return json(res, 200, list);
    }
    if (req.method === "GET" && url.pathname === "/chat") {
      const jid = findChat(url.searchParams.get("name"));
      if (!jid) return json(res, 404, { error: "not found" });
      const c = chat(jid);
      const out = { name: chatName(jid), messages: c.messages.slice(-Number(url.searchParams.get("limit") || 8)) };
      c.unread = 0;
      return json(res, 200, out);
    }
    if (req.method === "POST" && (url.pathname === "/send" || url.pathname === "/logout")) {
      let body = "";
      for await (const chunk of req) body += chunk;
      const data = body ? JSON.parse(body) : {};
      if (url.pathname === "/logout") {
        try { await sock.logout(); } catch (_) {}
        fs.rmSync(AUTH_DIR, { recursive: true, force: true });
        return json(res, 200, { ok: true });
      }
      if (state.state !== "connected") return json(res, 409, { error: "not connected" });
      const jid = data.jid || findChat(data.to);
      if (!jid) return json(res, 404, { error: "contact not found" });
      await sock.sendMessage(jidNormalizedUser(jid), { text: String(data.text || "") });
      return json(res, 200, { ok: true, name: chatName(jid) });
    }
    if (req.method === "GET" && url.pathname === "/resolve") {
      const jid = findChat(url.searchParams.get("name"));
      return jid ? json(res, 200, { jid, name: chatName(jid) }) : json(res, 404, { error: "not found" });
    }
    json(res, 404, { error: "unknown route" });
  } catch (e) {
    json(res, 500, { error: String(e && e.message || e) });
  }
}).listen(PORT, "127.0.0.1", () => start());

process.on("SIGINT", () => { saveStore(); process.exit(0); });
