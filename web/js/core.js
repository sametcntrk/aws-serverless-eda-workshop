/* Voltaj core: visitor id, persona sign-in (Cognito), API calls, the live "Behind the scenes" panel and the WebSocket. */
export const $ = (sel, root = document) => root.querySelector(sel);
export const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];
export const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
export const eur = (n) => new Intl.NumberFormat("en-IE", { style: "currency", currency: "EUR" }).format(Number(n || 0));
export const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

export let CONFIG = null;
export let SCENARIOS = null;
const SC = {};            // p3s1 → {page, no, color, title, steps: {label: step}}

export async function loadConfig() {
  const [cfg, sc] = await Promise.all([fetch("/config.json", { cache: "no-store" }).then((r) => r.json()),
    fetch("/data/scenarios.json").then((r) => r.json())]);
  CONFIG = cfg; SCENARIOS = sc;
  for (const p of sc.pages) for (const s of p.scenarios) {
    SC[s.id] = { page: p.page, pageName: p.name, no: s.no, color: s.color, title: s.title, steps: Object.fromEntries(s.steps.map((x) => [x.label, x])) };
  }
}
export const scenario = (id) => SC[id];

/* ---------------- visitor id (one per browser) */
export const vid = (() => {
  let v = localStorage.getItem("vt_vid");
  if (!v) { v = "v-" + crypto.randomUUID().slice(0, 13); localStorage.setItem("vt_vid", v); }
  return v;
})();
export const newCid = (prefix = "c") => `${prefix}-${crypto.randomUUID().replace(/-/g, "").slice(0, 12)}`;

/* ---------------- service colours and labels (same colour in the panel and on the page tags) */
export const SVC = {
  cf: ["CloudFront", "#8C4FFF"], apigw: ["API Gateway", "#E7157B"], lambda: ["Lambda", "#ED7100"], sfn: ["Step Functions", "#E7157B"],
  eb: ["EventBridge", "#E7157B"], sns: ["SNS", "#E7157B"], sqs: ["SQS", "#E7157B"], pipes: ["Pipes", "#E7157B"], ddb: ["DynamoDB", "#4053D6"],
  aurora: ["Aurora", "#4053D6"], aoss: ["OpenSearch", "#8C4FFF"], osis: ["OpenSearch Ingestion", "#8C4FFF"], s3: ["S3", "#3F8624"],
  mq: ["Amazon MQ", "#E7157B"], msk: ["MSK", "#8C4FFF"], ses: ["SES", "#DD344C"], eum: ["End User Messaging", "#DD344C"],
  cognito: ["Cognito", "#DD344C"], sm: ["Secrets Manager", "#DD344C"], pay: ["VoltPay (provider)", "#5B5B66"], "3pl": ["3PL WMS", "#5B5B66"],
  guard: ["Cost guard", "#B42318"], cw: ["CloudWatch", "#E7157B"],
};
export const svcTag = (id) => `<span class="svc-tag" style="--svc:${(SVC[id] || ["", "#666"])[1]}">${esc((SVC[id] || [id])[0])}</span>`;

/* ---------------- persona sign-in (Cognito user pool, USER_PASSWORD_AUTH; the demo admin also answers the TOTP challenge) */
const IDP = () => `https://cognito-idp.${CONFIG.region}.amazonaws.com/`;
async function idp(target, body) {
  const t0 = performance.now();
  const res = await fetch(IDP(), { method: "POST", headers: { "Content-Type": "application/x-amz-json-1.1",
    "X-Amz-Target": `AWSCognitoIdentityProviderService.${target}` }, body: JSON.stringify(body) });
  const json = await res.json();
  return { ok: res.ok, json, ms: Math.round(performance.now() - t0) };
}
export function persona() {
  const key = localStorage.getItem("vt_persona");
  if (key === CONFIG.demoAdmin.key) return { ...CONFIG.demoAdmin, admin: true };
  return CONFIG.personas.find((p) => p.key === key) || null;
}
export function session() {
  try { const s = JSON.parse(localStorage.getItem("vt_session") || "null"); return s && s.exp > Date.now() + 30000 ? s : null; }
  catch { return null; }
}
export async function signIn(p, label = "Sign in") {
  const cid = newCid("auth");
  const g = panel.group({ cid, label, method: "POST", url: `cognito-idp.${CONFIG.region}.amazonaws.com (InitiateAuth)`, source: "#persona-chip" });
  let r = await idp("InitiateAuth", { AuthFlow: "USER_PASSWORD_AUTH", ClientId: CONFIG.clientId, AuthParameters: { USERNAME: p.email, PASSWORD: p.password } });
  panel.add(cid, { svc: "cognito", engine: "Amazon Cognito", op: "InitiateAuth", sc: "p2s2", st: "1", ms: r.ms, ok: r.ok,
    request: `cognito-idp.initiate_auth(AuthFlow='USER_PASSWORD_AUTH', ClientId='${CONFIG.clientId}', USERNAME='${p.email}', PASSWORD=***)`,
    path: "Browser → Cognito public endpoint (HTTPS)", auth: "None (the password is the proof)",
    note: r.json.ChallengeName ? `Cognito asks for a second factor: ${r.json.ChallengeName}.` :
      "The browser talks to Cognito directly. The demo uses USER_PASSWORD_AUTH; a production SPA uses USER_SRP_AUTH, which never sends the password.",
    error: r.ok ? null : `${r.json.__type}: ${r.json.message}` });
  if (r.ok && r.json.ChallengeName === "SOFTWARE_TOKEN_MFA") {
    const { totp } = await import("./totp.js");
    const code = await totp(p.totpSecret);
    r = await idp("RespondToAuthChallenge", { ChallengeName: "SOFTWARE_TOKEN_MFA", ClientId: CONFIG.clientId, Session: r.json.Session,
      ChallengeResponses: { USERNAME: p.email, SOFTWARE_TOKEN_MFA_CODE: code } });
    panel.add(cid, { svc: "cognito", engine: "Amazon Cognito", op: "RespondToAuthChallenge", sc: "p2s2", st: "1", ms: r.ms, ok: r.ok,
      request: `cognito-idp.respond_to_auth_challenge(ChallengeName='SOFTWARE_TOKEN_MFA', SOFTWARE_TOKEN_MFA_CODE='${code}')`,
      path: "Browser → Cognito public endpoint (HTTPS)", auth: "Session from the first step + TOTP code",
      note: "The demo page computes the 6-digit TOTP code from the shared secret (RFC 6238), like an authenticator app.",
      error: r.ok ? null : `${r.json.__type}: ${r.json.message}` });
  }
  g.done(r.ok);
  if (!r.ok || !r.json.AuthenticationResult) throw new Error(r.json.message || "Sign-in failed.");
  const a = r.json.AuthenticationResult;
  const s = { key: p.key, id: a.IdToken, access: a.AccessToken, exp: Date.now() + a.ExpiresIn * 1000 };
  localStorage.setItem("vt_session", JSON.stringify(s));
  localStorage.setItem("vt_persona", p.key);
  ws.connect(true);
  return s;
}
export async function ensureSession() {
  const p = persona();
  if (!p) return null;
  return session() || signIn(p, `Sign in again as ${p.name}`);
}

/* ---------------- API */
export class ApiError extends Error { constructor(msg, status, payload) { super(msg); this.status = status; this.payload = payload; } }

/**
 * Call the REST API (through CloudFront /api/*) and show the call in the panel.
 * opts: {method, body, label, source (CSS selector of the page element), auth, cid, headers, background}
 */
export async function api(path, opts = {}) {
  const method = opts.method || (opts.body ? "POST" : "GET");
  const cid = opts.cid || newCid();
  const headers = { "X-Vid": vid, "X-Cid": cid, ...(opts.headers || {}) };
  if (opts.body) headers["Content-Type"] = "application/json";
  if (opts.auth) {
    const s = await ensureSession();
    if (!s) throw new ApiError("Choose a persona first.", 401);
    headers.Authorization = s.id;
  }
  const g = panel.group({ cid, label: opts.label || path, method, url: `/api${path}`, source: opts.source, background: opts.background });
  const t0 = performance.now();
  let json, status = 0;
  try {
    const res = await fetch(`/api${path}`, { method, headers, body: opts.body ? JSON.stringify(opts.body) : undefined });
    status = res.status;
    json = await res.json().catch(() => ({ ok: false, error: `HTTP ${res.status}: the answer is not JSON.` }));
    if (res.status === 429 && !json.trace) json = { ok: false, error: "HTTP 429: WAF or API Gateway throttling stopped the request.", trace: [] };
    if (!res.ok && json.ok !== false) json = { ...json, ok: false, error: json.error || json.message || `HTTP ${res.status}` };
  } catch (err) {
    json = { ok: false, error: `The request did not reach the API: ${err.message}` };
  }
  const ms = Math.round(performance.now() - t0);
  g.edge(ms, status);
  (json.trace || []).forEach((e) => panel.add(cid, e));
  g.done(json.ok !== false, json.error);
  if (json.ok === false) throw new ApiError(json.error || "The call failed.", status, json);
  return json.data;
}

/* ---------------- clickstream (batched, sent to /api/events → Lambda producer → MSK) */
const clicks = [];
let clickTimer = null;
export function click(type, data = {}) {
  clicks.push({ type, ...data, ts: Date.now(), page: location.pathname });
  clearTimeout(clickTimer);
  clickTimer = setTimeout(flushClicks, 1500);
}
async function flushClicks() {
  if (!clicks.length) return;
  const events = clicks.splice(0, 50);
  try { await api("/events", { body: { events, session: vid }, label: `Clickstream (${events.length} event${events.length > 1 ? "s" : ""})`, background: true }); }
  catch { /* shown in the panel */ }
}

/* ---------------- lesson routing: which 101 lesson explains an entry */
export function lessonFor(e) {
  const op = (e.op || "").toLowerCase();
  const by = {
    cognito: "cognito", aoss: "zero-etl", osis: "zero-etl", aurora: "aurora", mq: "pipes", msk: "clickstream", ses: "notifications",
    eum: "notifications", pay: "task-token", "3pl": "pipes", pipes: "pipes", sns: "fanout", s3: "upload-resize", cf: "edge", guard: "dlq",
  };
  if (e.sc && e.sc.startsWith("p3s5")) return "fanout";
  if (e.sc === "p3s4") return "saga";
  if (e.sc === "p3s2" || (e.sc === "p3s1" && e.st !== "1")) return "task-token";
  if (e.sc === "p3s1" || e.sc === "p3s3" && e.svc === "sfn") return "saga";
  if (e.sc === "p2s5" || e.svc === "apigw") return "websocket";
  if (op.includes("duplicate") || op.includes("idempot")) return "idempotency";
  if (e.svc === "eb") return e.sc === "p4s2" ? "pipes" : "fanout";
  if (e.svc === "sqs") return op.includes("redrive") || (e.event && e.event.receiveCount > 1) ? "dlq" : "messaging-compare";
  if (e.svc === "ddb") return (e.sc === "p2s4" || op.includes("transact")) ? "ddb-conditional" : (e.sc === "p5s8" ? "clickstream" : (e.sc === "p2s3" ? "zero-etl" : "idempotency"));
  if (e.svc === "lambda") return e.sc && e.sc.startsWith("p4s3") ? "dlq" : "saga";
  if (e.svc === "sfn") return "saga";
  return by[e.svc] || "fanout";
}

/* ---------------- the panel: one group per user action (cid); async entries join their group when they arrive */
const LEARN_KEY = "vt_learn";
function keepForLesson(entry) {
  let all = {};
  try { all = JSON.parse(localStorage.getItem(LEARN_KEY) || "{}"); } catch { all = {}; }
  const e = { ...entry };
  if (JSON.stringify(e).length > 40000) delete e.data;
  all[e.id] = { ...e, at: Date.now(), page: location.pathname };
  const ids = Object.keys(all).sort((a, b) => all[a].at - all[b].at);
  while (ids.length > 60) delete all[ids.shift()];
  try { localStorage.setItem(LEARN_KEY, JSON.stringify(all)); } catch { /* full */ }
}

export const panel = (() => {
  const groups = new Map();
  const seen = new Set();
  const listeners = [];
  let n = 0;
  const list = () => $("#bts-list");

  function group({ cid, label, method, url, source, background }) {
    let g = groups.get(cid);
    if (g) return g.api;
    n += 1;
    const li = document.createElement("li");
    li.className = "call" + (background ? " background" : "");
    li.dataset.cid = cid;
    li.innerHTML = `<div class="call-head"><span class="call-no" aria-hidden="true">${n}</span>
      <div class="call-title"><strong>${esc(label)}</strong><span class="src">${esc(method || "")} ${esc(url || "")}</span></div>
      <span class="call-state" aria-live="polite">…</span></div>
      <ol class="entries"></ol><p class="cid">cid <code>${esc(cid)}</code></p>`;
    if (source) {
      li.addEventListener("mouseenter", () => $$(source).forEach((el) => el.classList.add("source-hl")));
      li.addEventListener("mouseleave", () => $$(".source-hl").forEach((el) => el.classList.remove("source-hl")));
    }
    $("#bts-empty").hidden = true;
    list().appendChild(li);
    const box = $("#bts");
    if (box && box.scrollHeight > box.clientHeight) box.scrollTo({ top: box.scrollHeight, behavior: "smooth" });
    g = { li, cid, entries: [], api: null, waiting: null };
    g.api = {
      cid,
      edge(ms, status) { li.querySelector(".call-state").textContent = `${ms} ms · HTTP ${status || "-"}`; },
      done(ok, error) {
        li.classList.toggle("failed", !ok);
        if (!ok && error && !li.querySelector(".call-error")) li.insertAdjacentHTML("beforeend", `<p class="call-error">${esc(error)}</p>`);
      },
      wait(text) {
        if (g.waiting) g.waiting.remove();
        g.waiting = document.createElement("li");
        g.waiting.className = "entry waiting";
        g.waiting.innerHTML = `<span class="spinner" aria-hidden="true"></span> ${esc(text)}`;
        li.querySelector(".entries").appendChild(g.waiting);
      },
      unwait() { if (g.waiting) { g.waiting.remove(); g.waiting = null; } },
    };
    groups.set(cid, g);
    return g.api;
  }

  function add(cid, e) {
    if (!e.id) e.id = Math.random().toString(36).slice(2, 12);
    if (seen.has(e.id)) return;
    seen.add(e.id);
    e.cid = e.cid || cid;
    keepForLesson(e);
    let g = groups.get(cid);
    if (!g) { group({ cid, label: e.fn ? `In the background: ${e.fn}` : "In the background", method: "", url: "async", background: true }); g = groups.get(cid); }
    g.entries.push(e);
    const ol = g.li.querySelector(".entries");
    const node = renderEntry(e);
    // keep entries in time order (async entries can arrive late)
    const after = [...ol.children].find((c) => c.dataset.sk && c.dataset.sk > (e.sk || e.ts || ""));
    if (after) ol.insertBefore(node, after); else ol.insertBefore(node, g.waiting || null);
    if (g.waiting) ol.appendChild(g.waiting);
    if (e.ok === false) g.li.classList.add("has-error");
    listeners.forEach((fn) => fn(e));
  }

  function renderEntry(e) {
    const li = document.createElement("li");
    li.className = "entry" + (e.ok === false ? " failed" : "");
    li.dataset.sk = e.sk || e.ts || "";
    const s = e.sc && SC[e.sc];
    const step = s && s.steps[e.st];
    const badge = s ? `<a class="step" style="--sc:${s.color}" href="/diagram?page=${s.page}&sc=${e.sc}&st=${encodeURIComponent(e.st || "")}" target="_blank" rel="noopener"
        title="${esc(s.title)}${step ? " · step " + esc(e.st) + ": " + esc(step.title) : ""} (open the diagram)">P${s.page} · S${s.no}${e.st ? " · " + esc(e.st) : ""}</a>` : "";
    const rows = [];
    const add = (k, v) => { if (v !== undefined && v !== null && v !== "" && !(typeof v === "object" && !Object.keys(v).length)) rows.push(`<dt>${k}</dt><dd>${esc(typeof v === "object" ? JSON.stringify(v) : v)}</dd>`); };
    add("Parameters", e.params);
    add("Result", e.items !== undefined && e.items !== null ? `${e.items} item(s)` : "");
    add("Capacity", e.capacity); add("Cost", e.cost); add("Network", e.path); add("Auth", e.auth);
    if (e.event) {
      const ev = e.event;
      add("Event", [ev.source && `source ${ev.source}`, ev.detailType && `detail-type ${ev.detailType}`, ev.bus && `bus ${ev.bus}`,
        ev.topic && `topic ${ev.topic}`, ev.queue && `queue ${ev.queue}`, ev.receiveCount && `receive count ${ev.receiveCount}`].filter(Boolean).join(" · "));
      add("Event keys", ev.keys);
    }
    add("Function", e.fn);
    const learn = `/learn/${lessonFor(e)}?id=${encodeURIComponent(e.id)}&cid=${encodeURIComponent(e.cid || "")}`;
    li.innerHTML = `<div class="op">${badge}${svcTag(e.svc)}<span class="opname">${esc(e.op)}</span><span class="ms">${e.ms ?? 0} ms</span></div>
      ${step ? `<p class="step-title">${esc(step.title)}</p>` : ""}
      ${e.request ? `<pre>${esc(e.request)}</pre>` : ""}
      <dl>${rows.join("")}</dl>
      ${e.note ? `<p class="note">${esc(e.note)}</p>` : ""}
      ${e.error ? `<p class="err">${esc(e.error)}</p>` : ""}
      <a class="learn-link" href="${learn}" target="_blank" rel="noopener">101: What happened to the data? <span aria-hidden="true">↗</span></a>`;
    return li;
  }

  function clear() { list().innerHTML = ""; groups.clear(); n = 0; $("#bts-empty").hidden = false; }
  return { group, add, clear, on: (fn) => listeners.push(fn), wait: (cid, text) => groups.get(cid)?.api.wait(text),
    unwait: (cid) => groups.get(cid)?.api.unwait() };
})();

/* ---------------- WebSocket: trace entries (learning layer) and checkout.result frames (shop) */
export const ws = (() => {
  let sock = null, timer = null, wantOpen = false;
  const handlers = [];
  function setState(s) { const el = $("#ws-state"); if (el) { el.dataset.state = s; el.title = `Live channel: ${s}`; } }
  function connect(force) {
    const s = session();
    if (!s) return;
    if (sock && !force && sock.readyState <= 1) return;
    try { sock && sock.close(); } catch { /* ignore */ }
    wantOpen = true;
    setState("connecting");
    sock = new WebSocket(`${CONFIG.wsUrl}?token=${encodeURIComponent(s.access)}&vid=${encodeURIComponent(vid)}`);
    sock.onopen = () => { setState("open"); clearInterval(timer); timer = setInterval(() => sock.readyState === 1 && sock.send('{"action":"ping"}'), 300000); };
    sock.onmessage = (m) => {
      let msg; try { msg = JSON.parse(m.data); } catch { return; }
      if (msg.type === "trace" && msg.entry) panel.add(msg.entry.cid, msg.entry);
      handlers.forEach((fn) => fn(msg));
    };
    sock.onclose = () => { setState("closed"); if (wantOpen) setTimeout(() => connect(false), 3000); };
  }
  return { connect, on: (fn) => handlers.push(fn) };
})();

export function toast(text, kind = "") {
  const t = document.createElement("div");
  t.className = `toast ${kind}`;
  t.setAttribute("role", "status");
  t.textContent = text;
  $("#toasts").appendChild(t);
  setTimeout(() => t.remove(), 5000);
}
