/* Voltaj SPA: router, persona dialog, header search, and the shop pages. */
import { $, $$, esc, eur, api, click, CONFIG, loadConfig, persona, session, signIn, panel, ws, toast, svcTag, vid, newCid, ApiError, sleep } from "./core.js";
import { initLearnUi, setPage } from "./learn-ui.js";

const view = () => $("#view");
const img = (sku, size = "md") => `/images/${encodeURIComponent(sku)}/${size}.webp`;
const stockText = (n) => n === undefined ? "" : n <= 0 ? `<span class="stock out">Out of stock</span>` : n < 5 ? `<span class="stock low">Only ${n} left</span>` : `<span class="stock ok">In stock</span>`;
const stars = (r) => "★".repeat(Math.round(r || 0)) + "☆".repeat(5 - Math.round(r || 0));
const served = (...ids) => `<div class="served-by" aria-label="Served by">Served by ${ids.map(svcTag).join("")}</div>`;
function card(p) {
  return `<a class="card" href="/p/${encodeURIComponent(p.sku)}" data-link data-sku="${esc(p.sku)}">
    <img src="${img(p.sku)}" alt="" loading="lazy" width="480" height="480">
    <div class="body"><span class="name">${esc(p.name)}</span><span class="meta">${esc(p.brand || "")} · ${esc(p.category || "")}</span>
    ${p.rating ? `<span class="meta" aria-label="${p.rating} of 5">${stars(p.rating)}</span>` : ""}
    <span class="price">${eur(p.price)}</span>${stockText(p.available)}</div></a>`;
}
function errorBox(err) { return `<div class="notice bad">${esc(err.message || err)}</div>`; }

/* ---------------- cart badge */
function setCartCount(n) { localStorage.setItem("vt_cart", String(n)); $("#cart-count").textContent = n; }

/* ---------------- persona */
function showPersona() {
  const p = persona();
  $("#persona-name").textContent = p ? p.name : "Choose a persona";
  $("#persona-avatar").textContent = p ? p.name[0] : "?";
}
function openPersonas() {
  const cur = localStorage.getItem("vt_persona");
  const all = [...CONFIG.personas, { ...CONFIG.demoAdmin, admin: true }];
  $("#persona-list").innerHTML = all.map((p) => `<button type="button" data-key="${p.key}" aria-current="${p.key === cur}">
    <strong>${esc(p.name)}${p.admin ? " · admin" : ""}</strong><small>${esc(p.city || "")}${p.smsOptIn ? " · SMS on" : ""}</small><span>${esc(p.story)}</span></button>`).join("");
  $$("#persona-list button").forEach((b) => b.addEventListener("click", async () => {
    $("#persona-dialog").close();
    const p = all.find((x) => x.key === b.dataset.key);
    try { await signIn(p, `Sign in as ${p.name}`); showPersona(); toast(`You are ${p.name} now.`, "ok"); route(); }
    catch (e) { toast(e.message, "bad"); }
  }));
  $("#persona-dialog").showModal();
}

/* ---------------- router */
const routes = [
  [/^\/$/, home], [/^\/search$/, search], [/^\/p\/([^/]+)$/, product], [/^\/cart$/, cart], [/^\/checkout$/, checkout],
  [/^\/orders$/, orders], [/^\/inbox$/, inbox], [/^\/admin$/, admin], [/^\/reports$/, reports], [/^\/lessons$/, lessons],
];
function navigate(href) { history.pushState({}, "", href); route(); window.scrollTo(0, 0); }
window.addEventListener("vt:navigate", (e) => navigate(e.detail));
async function route() {
  const path = location.pathname;
  for (const [re, fn] of routes) {
    const m = path.match(re);
    if (m) {
      view().innerHTML = `<p class="empty"><span class="spinner"></span> Loading…</p>`;
      const id = fn.name;
      try { await fn(...m.slice(1)); } catch (e) { view().innerHTML = errorBox(e); }
      setPage(id === "product" ? "product" : id);
      document.title = `${$("#view h1")?.textContent || "Voltaj"} · Voltaj`;
      return;
    }
  }
  view().innerHTML = `<h1>Page not found</h1><p><a href="/" data-link>Go to the home page</a></p>`;
}
document.addEventListener("click", (e) => {
  const a = e.target.closest("a[data-link]");
  if (a && !e.metaKey && !e.ctrlKey && a.origin === location.origin) { e.preventDefault(); navigate(a.pathname + a.search); }
});
addEventListener("popstate", route);

/* ---------------- pages */
async function home() {
  view().innerHTML = `
    <section class="hero" id="hero">
      <h1>Electronics with <span class="bolt">energy</span>. Built on events.</h1>
      <p>Voltaj is a fast-growing online shop. A 3PL warehouse with an old WMS ships the parcels, a payment provider confirms the payments,
      and the marketing team reads every click. Every action on this site runs on real AWS services in Frankfurt. The violet panel shows each call.</p>
      <div class="hero-actions"><a class="btn volt" href="/search" data-link>Shop now</a>
      <button id="hero-journey" type="button">Take the guided journey</button></div>
    </section>
    <section class="section" id="cats"><div class="section-head"><h2>Categories</h2><p>Each category is a search in OpenSearch Serverless.</p></div>
      <div class="cats">${CONFIG.categories.map((c) => `<a class="chip" data-link href="/search?category=${encodeURIComponent(c)}">${esc(c)}</a>`).join("")}</div></section>
    <section class="section" id="popular"><div class="section-head"><h2>Popular now</h2>${served("msk", "lambda", "ddb")}</div>
      <p class="meta">The clickstream goes to Amazon MSK. A consumer group counts the product views in DynamoDB. This list reads the counters.</p>
      <div class="grid" id="popular-grid"><p class="empty"><span class="spinner"></span></p></div></section>
    <section class="section"><div class="section-head"><h2>New arrivals</h2>${served("aoss", "ddb")}</div><div class="grid" id="new-grid"></div></section>`;
  $("#hero-journey").addEventListener("click", () => import("./learn-ui.js").then((m) => m.startJourney()));
  click("page_view");
  const [pop, all] = await Promise.allSettled([api("/products/popular", { label: "Popular products", source: "#popular" }),
    api("/products?size=8", { label: "New arrivals", source: "#new-grid" })]);
  $("#popular-grid").innerHTML = pop.status === "fulfilled" ? (pop.value.map(card).join("") || `<p class="empty">No views counted yet.</p>`) : errorBox(pop.reason);
  $("#new-grid").innerHTML = all.status === "fulfilled" ? all.value.items.map(card).join("") : errorBox(all.reason);
}

async function search() {
  const q = new URLSearchParams(location.search);
  const term = q.get("q") || "", cat = q.get("category") || "";
  const fuzzy = localStorage.getItem("vt_fuzzy") !== "0";
  $("#header-q").value = term;
  view().innerHTML = `<h1>${term ? `Results for “${esc(term)}”` : cat ? esc(cat) : "All products"}</h1>${served("cf", "apigw", "lambda", "aoss", "ddb")}
    <div class="cats" id="cat-filter"><a class="chip" data-link href="/search${term ? `?q=${encodeURIComponent(term)}` : ""}" aria-current="${!cat}">All</a>
      ${CONFIG.categories.map((c) => `<a class="chip" data-link aria-current="${c === cat}" href="/search?${new URLSearchParams({ ...(term ? { q: term } : {}), category: c })}">${esc(c)}</a>`).join("")}</div>
    <div class="exp" id="exp-fuzzy" style="margin:14px 0"><h3>Experiment: fuzzy search</h3>
      <p>OpenSearch can forgive typing errors (fuzziness AUTO). Search for “hedphones” with fuzzy on and off, then compare the request in the panel.</p>
      <label><input type="checkbox" id="fuzzy" ${fuzzy ? "checked" : ""}> Fuzzy matching on</label></div>
    <p id="count" class="meta"></p><div class="grid" id="results"><p class="empty"><span class="spinner"></span></p></div>`;
  $("#fuzzy").addEventListener("change", (e) => { localStorage.setItem("vt_fuzzy", e.target.checked ? "1" : "0"); search(); });
  if (term) click("search", { q: term });
  try {
    const params = new URLSearchParams({ size: "24", ...(term ? { q: term } : {}), ...(cat ? { category: cat } : {}), fuzzy: fuzzy ? "1" : "0" });
    const r = await api(`/products?${params}`, { label: term ? `Search “${term}”` : `List ${cat || "products"}`, source: "#results" });
    $("#count").textContent = `${r.total} product(s) in the index. ${term ? (fuzzy ? "Fuzzy matching is on." : "Fuzzy matching is off.") : ""}`;
    $("#results").innerHTML = r.items.map(card).join("") || `<p class="empty">No product matches. Try fuzzy matching or another word.</p>`;
  } catch (e) { $("#results").innerHTML = errorBox(e); }
}

async function product(sku) {
  sku = decodeURIComponent(sku);
  const p = await api(`/products/${encodeURIComponent(sku)}`, { label: "Product detail", source: "#view" });
  click("product_view", { sku });
  let qty = 1;
  view().innerHTML = `<p><a href="/search?category=${encodeURIComponent(p.category)}" data-link>← ${esc(p.category)}</a></p>
    <div class="pdp"><img src="${img(p.sku, "lg")}" alt="${esc(p.name)}" width="960" height="960">
    <div><h1>${esc(p.name)}</h1><p class="meta">${esc(p.brand)} · SKU ${esc(p.sku)} · ${stars(p.rating)} ${p.rating}</p>
      ${served("ddb")}<p>${esc(p.short || "")}</p>
      <p class="big-price">${eur(p.price)}</p><p>${stockText(p.available)}</p>
      <div class="row" id="buy"><div class="qty" role="group" aria-label="Quantity"><button type="button" id="minus" aria-label="Less">−</button><output id="q">1</output><button type="button" id="plus" aria-label="More">+</button></div>
        <button class="primary" id="add" type="button" ${p.available <= 0 ? "disabled" : ""}>Add to cart</button></div>
      <p id="add-msg" role="status"></p>
      <div class="panel" style="margin-top:18px"><h2>What happens when you add it</h2>
        <p class="meta">CloudFront sends the request to API Gateway. The Cognito authorizer checks your ID token. The cart function writes one item with UpdateItem ADD and a condition (at most 5 pieces per line), and a TTL of 7 days.</p></div>
    </div></div>`;
  $("#minus").addEventListener("click", () => { qty = Math.max(1, qty - 1); $("#q").textContent = qty; });
  $("#plus").addEventListener("click", () => { qty = Math.min(5, qty + 1); $("#q").textContent = qty; });
  $("#add").addEventListener("click", async () => {
    if (!persona()) return openPersonas();
    try {
      const c = await api("/cart/items", { body: { sku: p.sku, qty }, auth: true, label: "Add to cart", source: "#buy" });
      setCartCount(c.count);
      click("add_to_cart", { sku: p.sku });
      $("#add-msg").innerHTML = `<span class="stock ok">Added.</span> <a href="/cart" data-link>Go to the cart (${c.count})</a>`;
    } catch (e) { $("#add-msg").innerHTML = errorBox(e); }
  });
}

async function cart() {
  if (!persona()) { view().innerHTML = `<h1>Your cart</h1><div class="empty">Choose a persona first. <button id="pick" type="button">Choose a persona</button></div>`; $("#pick").onclick = openPersonas; return; }
  const c = await api("/cart", { auth: true, label: "Read the cart", source: "#view" });
  setCartCount(c.count);
  const p = persona();
  view().innerHTML = `<h1>Your cart</h1>${served("cognito", "apigw", "lambda", "ddb")}
    ${c.lines.length ? `<table class="table" id="lines"><thead><tr><th>Product</th><th>Qty</th><th>Price</th><th></th></tr></thead><tbody>
      ${c.lines.map((l) => `<tr><td><a data-link href="/p/${encodeURIComponent(l.sku)}">${esc(l.name)}</a><br><small class="meta">${esc(l.sku)}</small></td><td>${l.qty}</td>
        <td>${eur(l.qty * l.price)}</td><td><button class="quiet small" data-del="${esc(l.sku)}" type="button">Remove</button></td></tr>`).join("")}
      </tbody></table>
      <div class="row" style="justify-content:space-between;margin-top:16px"><p class="big-price">${eur(c.total)}</p>
      <div class="row"><label><input type="checkbox" id="sms" ${p.smsOptIn ? "checked" : ""}> Send me SMS updates</label>
      <button class="volt" id="checkout" type="button">Checkout</button></div></div>
      <div class="panel" style="margin-top:16px" id="checkout-info"><h2>What happens at checkout</h2>
      <p class="meta">API Gateway starts the Step Functions workflow directly (no Lambda) and answers at once. The workflow reserves the stock,
      asks VoltPay for the payment, and waits for the webhook. The result comes back over the WebSocket.</p></div>`
      : `<div class="empty">The cart is empty. <a href="/search" data-link>Find a product</a>.</div>`}`;
  $$("[data-del]").forEach((b) => b.addEventListener("click", async () => {
    await api(`/cart/items/${encodeURIComponent(b.dataset.del)}`, { method: "DELETE", auth: true, label: "Remove a line", source: "#lines" });
    cart();
  }));
  $("#checkout")?.addEventListener("click", async (e) => {
    e.target.disabled = true;
    const orderId = "o-" + crypto.randomUUID().replace(/-/g, "").slice(0, 10);
    const cid = newCid("chk");
    try {
      ws.connect();
      await api("/checkout", { body: { smsOptIn: $("#sms").checked }, auth: true, cid, headers: { "Idempotency-Key": orderId }, label: `Checkout ${orderId}`, source: "#checkout" });
      click("checkout", { orderId });
      localStorage.setItem(`vt_order_${orderId}`, JSON.stringify({ cid, at: Date.now() }));
      panel.wait(cid, "The saga runs. Entries arrive here over the WebSocket…");
      navigate(`/checkout?order=${orderId}&cid=${cid}`);
    } catch (err) { e.target.disabled = false; toast(err.message, "bad"); }
  });
}

/* Checkout progress: built from the live trace entries of this cid */
const CHECKOUT_STEPS = [
  ["start", "Workflow started", "API Gateway → Step Functions (StartExecution)"],
  ["reserve", "Stock reserved", "DynamoDB TransactWriteItems with conditions"],
  ["pay", "Payment created", "Lambda payment → NAT gateway → VoltPay"],
  ["paid", "Payment result", "VoltPay webhook → Lambda webhook → SendTaskSuccess / SendTaskFailure"],
  ["order", "Order written", "Lambda order → RDS Proxy → Aurora (one transaction)"],
  ["placed", "OrderPlaced published", "Step Functions → EventBridge bus voltaj-commerce"],
  ["result", "Result pushed", "Lambda ws → API Gateway WebSocket → this page"],
  ["fulfil", "Fulfillment sent to the 3PL", "SQS order buffer → Lambda → Amazon MQ → VPN → 3PL"],
  ["ship", "Shipment dispatched", "3PL → Amazon MQ → EventBridge Pipes → bus"],
  ["notify", "Email and SMS", "SNS → SQS → Lambda → SES / End User Messaging"],
];
function checkoutState(entries) {
  const st = {}; let failed = null, payUrl = null;
  for (const e of entries) {
    const k = `${e.sc}:${e.st}`;
    if (e.op === "StartExecution") st.start = "done";
    if (e.op === "TransactWriteItems" && e.sc === "p3s1") st.reserve = e.ok === false ? "fail" : "done";
    if (e.ui === "open-payment" || (e.op === "POST /v1/payments" && e.ok !== false)) { st.pay = "done"; payUrl = (e.data || {}).checkoutUrl || payUrl; }
    if (k === "p3s2:5") st.paid = "done";
    if (e.op === "States.Timeout" || e.op === "SendTaskFailure received") { st.paid = "fail"; failed = e.op === "States.Timeout" ? "No webhook before the timeout." : "VoltPay declined the payment."; }
    if (e.op === "COMMIT") st.order = "done";
    if (k === "p3s3:4") st.placed = "done";
    if (k === "p3s3:8" || k === "p3s4:5") st.result = "done";
    if (k === "p3s4:1" && e.op === "TransactWriteItems") st.reserve = "undone";
    if (e.op === "Limit reached") { failed = e.note; st.start = "fail"; }
    if (k === "p4s1:2" || k === "p4s1:4") st.fulfil = k === "p4s1:4" ? "done" : st.fulfil || "now";
    if (e.sc === "p4s2") st.ship = "done";
    if (k === "p4s3:4" || k === "p4s4:4") st.notify = "done";
  }
  return { st, failed, payUrl };
}
async function checkout() {
  const q = new URLSearchParams(location.search);
  const orderId = q.get("order"), cid = q.get("cid") || (JSON.parse(localStorage.getItem(`vt_order_${orderId}`) || "{}").cid);
  if (!orderId || !cid) { view().innerHTML = `<h1>Checkout</h1><div class="empty">No checkout is open. <a href="/cart" data-link>Go to the cart</a>.</div>`; return; }
  const entries = [];
  view().innerHTML = `<h1>Order ${esc(orderId)}</h1>${served("sfn", "lambda", "ddb", "aurora", "eb", "apigw")}
    <div id="banner" class="notice" role="status"><span class="spinner"></span> The checkout workflow runs.</div>
    <div class="row" style="margin:14px 0" id="pay-row"></div>
    <ol class="steps" id="progress"></ol>
    <div class="exp" id="exp-dup" style="margin-top:16px"><h3>Experiment: the same event twice</h3>
      <p>At-least-once delivery means that a consumer can get the same event again. Send OrderPlaced for this order a second time.
      Each consumer finds its idempotency key in DynamoDB and stops, so the 3PL gets no second parcel and you get no second email.</p>
      <button type="button" id="dup" class="primary" disabled>Send OrderPlaced again</button></div>`;
  const draw = () => {
    const { st, failed, payUrl } = checkoutState(entries);
    $("#progress").innerHTML = CHECKOUT_STEPS.map(([k, t, d]) => {
      const s = st[k]; const cls = s === "done" ? "done" : s === "fail" ? "fail" : s === "undone" ? "fail" : s === "now" ? "now" : "";
      return `<li class="${cls}"><span class="dot">${s === "done" ? "✓" : s === "fail" || s === "undone" ? "!" : ""}</span><div><strong>${t}${s === "undone" ? " — released again (compensation)" : ""}</strong><small>${d}</small></div></li>`;
    }).join("");
    if (payUrl && !st.paid && !failed) $("#pay-row").innerHTML = `<a class="btn volt" href="${esc(payUrl)}" target="_blank" rel="noopener">Pay with VoltPay ↗</a>
      <span class="meta">The workflow waits for the webhook (task token). Choose Pay, Decline or No answer on the VoltPay page.</span>`;
    else $("#pay-row").innerHTML = "";
    if (failed) $("#banner").outerHTML = `<div id="banner" class="notice bad" role="status">${esc(failed)} The saga released the stock and published PaymentFailed.</div>`;
    else if (st.result === "done") $("#banner").outerHTML = `<div id="banner" class="notice ok" role="status">Order confirmed. The confirmation came over the WebSocket. Shipping and email follow in the background.</div>`;
    $("#dup").disabled = st.placed !== "done";
  };
  draw();
  try {
    const old = await api(`/learn/trace?cid=${encodeURIComponent(cid)}`, { label: "Load the trace of this checkout", background: true });
    old.forEach((e) => { panel.add(cid, e); });
  } catch { /* the live channel still works */ }
  const sync = (e) => { if (e.cid === cid && !entries.find((x) => x.id === e.id)) { entries.push(e); entries.sort((a, b) => (a.sk || "").localeCompare(b.sk || "")); draw(); } };
  panel.on(sync);
  Object.values(JSON.parse(localStorage.getItem("vt_learn") || "{}")).filter((e) => e.cid === cid).forEach(sync);
  ws.on((m) => { if (m.type === "checkout.result" && m.orderId === orderId) { panel.unwait(cid); draw(); if (m.status === "CONFIRMED") setCartCount(0); } });
  $("#dup").addEventListener("click", async () => {
    try { await api("/learn/experiments/duplicate", { body: { cid }, label: "Experiment: OrderPlaced again", source: "#exp-dup" }); toast("Sent again. Watch the consumers in the panel.", "ok"); }
    catch (e) { toast(e.message, "bad"); }
  });
}

async function orders() {
  if (!persona()) { view().innerHTML = `<h1>Orders</h1><div class="empty">Choose a persona first.</div>`; return; }
  const rows = await api("/orders", { auth: true, label: "Order history", source: "#view" });
  view().innerHTML = `<h1>Your orders</h1>${served("lambda", "aurora")}<p class="meta">Rows from Aurora PostgreSQL through RDS Proxy. Orders marked “you” were placed from this browser.</p>
    ${rows.length ? `<table class="table" id="orders"><thead><tr><th>Order</th><th>Date</th><th>Lines</th><th>Total</th><th>Status</th></tr></thead><tbody>
    ${rows.map((o) => `<tr><td><code>${esc(o.order_id)}</code>${o.mine ? ' <span class="pill">you</span>' : ""}</td><td>${new Date(o.created_at).toLocaleDateString("en-GB")}</td>
      <td>${(o.lines || []).map((l) => `${l.qty} × ${esc(l.name)}`).join("<br>")}</td><td>${eur(o.total)}</td><td>${esc(o.status)}</td></tr>`).join("")}</tbody></table>` : `<div class="empty">No orders yet.</div>`}`;
}

async function inbox() {
  view().innerHTML = `<h1>Inbox</h1>${served("sns", "sqs", "ses", "eum")}
    <p class="meta">Emails go to the SES mailbox simulator and SMS go to an End User Messaging simulator number: real API calls, but nothing reaches a real inbox or phone.
    This page shows what was sent for this browser.</p><div id="msgs" style="display:grid;gap:14px"><p class="empty"><span class="spinner"></span></p></div>`;
  const entries = await api("/learn/recent", { label: "Read the recent trace", background: true });
  const msgs = entries.filter((e) => e.ui === "inbox" && e.data);
  const render = () => {
    $("#msgs").innerHTML = msgs.length ? msgs.slice().reverse().map((e) => e.data.kind === "email"
      ? `<article class="mail"><header><b>${esc(e.data.subject)}</b><br>From ${esc(e.data.from)} · To ${esc(e.data.to)} · ${new Date(e.ts).toLocaleString("en-GB")}</header>
         <div class="mail-body">${e.data.html}</div></article>`
      : `<article><p class="meta">SMS to ${esc(e.data.to)} from ${esc(e.data.from)} · ${new Date(e.ts).toLocaleString("en-GB")}</p><div class="sms">${esc(e.data.body)}</div></article>`).join("")
      : `<div class="empty">No message yet. Finish a checkout: the confirmation email arrives here in a few seconds.</div>`;
    $("#inbox-count").hidden = !msgs.length; $("#inbox-count").textContent = msgs.length;
  };
  render();
  panel.on((e) => { if (e.ui === "inbox" && e.data && location.pathname === "/inbox" && !msgs.find((m) => m.id === e.id)) { msgs.push(e); render(); } });
}

async function admin() {
  const p = persona();
  if (!p || !p.admin) {
    view().innerHTML = `<h1>Back office</h1><div class="panel"><p>The back office needs a user in the Cognito group <b>admins</b> with MFA.</p>
      <p class="meta">The demo admin (${esc(CONFIG.demoAdmin.name)}) has a TOTP authenticator. This page computes the code for you, so you can see the MFA challenge in the panel.</p>
      <button class="primary" id="as-admin" type="button">Sign in as the demo admin (password + TOTP)</button></div>`;
    $("#as-admin").addEventListener("click", async () => {
      try { await signIn({ ...CONFIG.demoAdmin, admin: true }, "Sign in as the demo admin (MFA)"); showPersona(); admin(); } catch (e) { toast(e.message, "bad"); }
    });
    return;
  }
  const sku = localStorage.getItem("vt_demo_sku") || `demo-${vid.slice(2, 8)}`;
  view().innerHTML = `<h1>Back office</h1>${served("cognito", "apigw", "lambda", "ddb", "osis", "aoss", "s3")}
    <div class="panel" id="product-form"><h2>1 · Save a product</h2>
      <p class="meta">The product function writes the item to DynamoDB. The table stream feeds the zero-ETL pipeline, which indexes the change in OpenSearch Serverless in a few seconds.</p>
      <div class="form-grid">
        <label class="f">SKU (demo- prefix)<input id="f-sku" value="${esc(sku)}" pattern="demo-[a-z0-9-]+"></label>
        <label class="f">Name<input id="f-name" value="Voltaj Demo Speaker ${esc(sku.slice(-4))}"></label>
        <label class="f">Price (EUR)<input id="f-price" type="number" step="0.01" value="79.90"></label>
        <label class="f">Category<select id="f-cat">${CONFIG.categories.map((c) => `<option ${c === "Speakers" ? "selected" : ""}>${esc(c)}</option>`).join("")}</select></label>
        <label class="f">Short text<input id="f-short" value="A demo product made in the back office."></label>
      </div><div class="row" style="margin-top:12px"><button class="primary" id="save" type="button">Save the product</button><span id="save-msg" role="status"></span></div></div>
    <div class="panel" id="image-form" style="margin-top:14px"><h2>2 · Upload an image</h2>
      <p class="meta">The function signs a presigned URL. The browser puts the file directly in S3. S3 sends Object Created to EventBridge, and the resize function writes three WebP sizes to the web bucket.</p>
      <div class="row"><input type="file" id="file" accept="image/jpeg,image/png,image/webp"><button id="upload" type="button" class="primary">Upload</button></div>
      <p id="up-msg" role="status"></p><img id="preview" alt="" hidden style="max-width:240px;border-radius:12px;border:1px solid var(--line)"></div>`;
  $("#save").addEventListener("click", async () => {
    const s = $("#f-sku").value.trim();
    localStorage.setItem("vt_demo_sku", s);
    try {
      await api(`/admin/products/${encodeURIComponent(s)}`, { method: "PUT", auth: true, label: "Save a product (admin)", source: "#product-form",
        body: { name: $("#f-name").value, price: $("#f-price").value, category: $("#f-cat").value, short: $("#f-short").value } });
      $("#save-msg").innerHTML = `<span class="stock ok">Saved.</span> In about 10 seconds: <a data-link href="/search?q=${encodeURIComponent($("#f-name").value)}">search for it</a>.`;
    } catch (e) { $("#save-msg").innerHTML = errorBox(e); }
  });
  $("#upload").addEventListener("click", async () => {
    const f = $("#file").files[0];
    if (!f) return toast("Choose an image file first.", "bad");
    if (f.size > 2_000_000) return toast("The limit is 2 MB.", "bad");
    const s = $("#f-sku").value.trim();
    const cid = newCid("img");
    try {
      const u = await api("/admin/images/upload-url", { body: { sku: s, contentType: f.type }, auth: true, cid, label: "Get a presigned upload URL", source: "#image-form" });
      const t0 = performance.now();
      const r = await fetch(u.url, { method: "PUT", headers: u.headers, body: f });
      panel.add(cid, { svc: "s3", engine: "Amazon S3", op: "PUT (presigned)", sc: "p5s4", st: "1", ms: Math.round(performance.now() - t0), ok: r.ok,
        request: `HTTPS PUT ${u.url.split("?")[0]}\nContent-Type: ${f.type}\nx-amz-meta-cid: ${cid}`, items: 1,
        path: "Browser → S3 regional endpoint (no CloudFront, no Lambda)", auth: "Presigned URL (SigV4 in the query string, valid 5 minutes)",
        note: r.ok ? "S3 stored the original. The bucket sends Object Created to the default event bus." : `S3 answered HTTP ${r.status}.` });
      panel.wait(cid, "Waiting for the resize function…");
      $("#up-msg").textContent = "Uploaded. The resize runs now…";
      panel.on((e) => { if (e.cid === cid && e.ui === "image-ready") { panel.unwait(cid); $("#preview").src = `/images/${encodeURIComponent(s)}/md.webp?t=${Date.now()}`; $("#preview").hidden = false; $("#up-msg").textContent = "Done: CloudFront serves the new image."; } });
    } catch (e) { $("#up-msg").innerHTML = errorBox(e); }
  });
}

async function reports() {
  view().innerHTML = `<h1>Reports and experiments</h1><p class="meta">The analytic side of the shop. Each report is a real call: Step Functions, CloudWatch Logs, SQS, CloudWatch metrics, S3, DynamoDB.</p>
    <div class="cats" id="tabs">${["Saga executions", "Events", "Queues and DLQ", "Clickstream", "Schemas"].map((t, i) => `<button class="chip" data-tab="${i}" aria-current="${i === 0}" type="button">${t}</button>`).join("")}</div>
    <div id="tab" style="margin-top:14px"></div>`;
  const tabs = [repSaga, repEvents, repQueues, repClicks, repSchemas];
  $$("#tabs [data-tab]").forEach((b) => b.addEventListener("click", () => {
    $$("#tabs [data-tab]").forEach((x) => x.setAttribute("aria-current", x === b ? "true" : "false"));
    tabs[b.dataset.tab]().catch((e) => { $("#tab").innerHTML = errorBox(e); });
  }));
  await repSaga();
}
async function repSaga() {
  const rows = await api("/learn/reports/executions", { label: "Saga executions", source: "#tab" });
  $("#tab").innerHTML = `${served("sfn")}<table class="table"><thead><tr><th>Execution (order)</th><th>Status</th><th>Start</th><th>Duration</th></tr></thead><tbody>
    ${rows.map((r) => `<tr><td><code>${esc(r.name)}</code></td><td>${esc(r.status)}</td><td>${new Date(r.start).toLocaleTimeString("en-GB")}</td>
    <td>${r.stop ? Math.round((new Date(r.stop) - new Date(r.start)) / 1000) + " s" : "running"}</td></tr>`).join("")}</tbody></table>`;
}
async function repEvents() {
  const rows = await api("/learn/reports/events", { label: "Events on the bus (last hour)", source: "#tab" });
  $("#tab").innerHTML = `${served("eb", "cw")}<div class="exp" style="margin-bottom:12px"><h3>Experiment: replay from the archive</h3>
    <p>The bus archive keeps every event for 7 days. Replay sends the events of the last 10 minutes again, only to the log rule (no email, no 3PL message repeats). Max 2 per hour.</p>
    <button class="primary" id="replay" type="button">Replay the last 10 minutes</button></div>
    <table class="table"><thead><tr><th>Time</th><th>Source</th><th>Detail-type</th><th>Order</th></tr></thead><tbody>
    ${rows.map((r) => `<tr><td>${esc((r.time || "").slice(11, 19))}</td><td>${esc(r.source)}</td><td>${esc(r.detailType)}</td><td><code>${esc(r.orderId || "")}</code></td></tr>`).join("") || `<tr><td colspan="4">No event in the last hour.</td></tr>`}</tbody></table>`;
  $("#replay").addEventListener("click", () => api("/learn/experiments/replay", { body: { minutes: 10 }, label: "Experiment: replay", source: "#replay" }).then(() => toast("Replay started.", "ok")).catch((e) => toast(e.message, "bad")));
}
async function repQueues() {
  const [q, d] = await Promise.all([api("/learn/reports/queues", { label: "Queue depth", source: "#tab" }), api("/learn/reports/dlq", { label: "Dead-letter queues", source: "#tab" })]);
  $("#tab").innerHTML = `${served("sqs")}<div class="row" style="align-items:stretch">
    <div class="exp" style="flex:1"><h3>Experiment: a broken consumer</h3><p>Break the email consumer for 10 minutes. New emails fail; after 3 receives SQS moves the message to voltaj-email-dlq. Then fix it and redrive.</p>
      <div class="row"><button id="break" class="primary" type="button">Break the email consumer</button><button id="fix" type="button">Fix it</button><button id="redrive" type="button">Redrive email-dlq</button></div></div>
    <div class="exp" style="flex:1"><h3>Experiment: event burst (capped)</h3><p>Send up to 200 OrderPlaced events. The rules fan them out to SNS, the order buffer and the log. Max 5 bursts per hour.</p>
      <div class="row"><button id="burst" class="primary" type="button">Send 50 OrderPlaced</button><button id="refresh" type="button">Refresh depth</button></div></div></div>
    <table class="table" style="margin-top:12px"><thead><tr><th>Queue</th><th>Visible</th><th>In flight</th></tr></thead><tbody>
    ${q.map((r) => `<tr><td>${esc(r.name)}</td><td>${r.visible}</td><td>${r.inFlight}</td></tr>`).join("")}</tbody></table>
    <h2 style="margin-top:18px">DLQ messages</h2>${d.map((x) => `<h3>${esc(x.name)} (${x.count})</h3>${x.messages.map((m) => `<pre class="panel" style="white-space:pre-wrap;font-size:.75rem">receive count ${esc(m.receiveCount)}\n${esc(m.body.slice(0, 800))}</pre>`).join("") || "<p class='meta'>Empty.</p>"}`).join("")}`;
  $("#break").onclick = () => api("/learn/experiments/break-email", { body: { on: true }, label: "Experiment: break the email consumer", source: "#break" }).then(() => toast("The email consumer is broken for 10 minutes.", "ok"));
  $("#fix").onclick = () => api("/learn/experiments/break-email", { body: { on: false }, label: "Experiment: fix the email consumer", source: "#fix" }).then(() => toast("Fixed.", "ok"));
  $("#redrive").onclick = () => api("/learn/experiments/redrive", { body: { queue: "email-dlq" }, label: "Experiment: redrive", source: "#redrive" }).then(() => toast("Redrive started.", "ok")).catch((e) => toast(e.message, "bad"));
  $("#burst").onclick = () => api("/learn/experiments/burst", { body: { kind: "orders", n: 50 }, label: "Experiment: burst of 50 OrderPlaced", source: "#burst" }).then(() => toast("Sent.", "ok")).catch((e) => toast(e.message, "bad"));
  $("#refresh").onclick = () => repQueues();
}
async function repClicks() {
  const [lag, lake, counters] = await Promise.all([api("/learn/reports/lag", { label: "MSK consumer lag", source: "#tab" }),
    api("/learn/reports/lake", { label: "Data lake objects", source: "#tab" }), api("/learn/reports/counters", { label: "Popular-product counters", source: "#tab" })]);
  $("#tab").innerHTML = `${served("msk", "lambda", "s3", "ddb")}<div class="exp" style="margin-bottom:12px"><h3>Experiment: clickstream burst</h3>
    <p>Send 500 page_view events to the topic clickstream. Two consumer groups (archive, counters) read them independently. Watch the lag.</p>
    <button class="primary" id="clicks" type="button">Send 500 clicks</button></div>
    <h2>Consumer lag (max offset lag, 1 h)</h2>${lag.map((g) => `<p><b>${esc(g.group)}</b>: ${g.points.length ? g.points.slice(0, 10).map((p) => p[1]).join(", ") : "no data yet"}</p>`).join("")}
    <h2>Data lake (latest files)</h2><table class="table"><tbody>${lake.slice(0, 15).map((o) => `<tr><td><code>${esc(o.key)}</code></td><td>${o.size} B</td><td>${esc(o.at.slice(11, 19))}</td></tr>`).join("") || "<tr><td>No file yet.</td></tr>"}</tbody></table>
    <h2>Top counters</h2><table class="table"><tbody>${counters.slice(0, 10).map((c) => `<tr><td><a data-link href="/p/${encodeURIComponent(c.sku)}">${esc(c.sku)}</a></td><td>${c.views} views</td></tr>`).join("")}</tbody></table>`;
  $("#clicks").onclick = () => api("/learn/experiments/burst", { body: { kind: "clicks", n: 500 }, label: "Experiment: 500 clicks", source: "#clicks" }).then(() => toast("Sent.", "ok")).catch((e) => toast(e.message, "bad"));
}
async function repSchemas() {
  const rows = await api("/learn/reports/schemas", { label: "Discovered schemas", source: "#tab" });
  $("#tab").innerHTML = `${served("eb")}<p class="meta">Schema discovery on the bus writes an OpenAPI schema for each new event shape.</p>
    ${rows.map((s) => `<h3>${esc(s.name)} (version ${esc(s.version)})</h3><pre class="panel" style="font-size:.75rem;max-height:300px;overflow:auto">${esc(JSON.stringify(s.content, null, 1))}</pre>`).join("") || "<p class='empty'>No schema yet. Discovery needs a few minutes after the first events.</p>"}`;
}

async function lessons() {
  const idx = await fetch("/data/lessons/index.json").then((r) => r.json());
  view().innerHTML = `<h1>101 lessons</h1><p class="meta">Türkçe, başlangıç seviyesi. Her ders senin gerçek çağrınla dolar: önce mağazada bir şey yap, sonra paneldeki “101” linkine tıkla.</p>
    <div class="grid" style="grid-template-columns:repeat(auto-fill,minmax(260px,1fr))">${idx.map((l, i) => `<a class="card" href="/learn/${l.id}" target="_blank" rel="noopener">
      <div class="body"><span class="meta">Ders ${i + 1}${l.sample ? " · örnek ders" : ""}</span><span class="name">${esc(l.title)}</span><span class="meta">${esc(l.summary)}</span></div></a>`).join("")}</div>`;
}

/* ---------------- header search with suggestions */
function initSearch() {
  const q = $("#header-q"), sug = $("#suggest");
  let timer;
  $("#search-form").addEventListener("submit", (e) => { e.preventDefault(); navigate(`/search?q=${encodeURIComponent(q.value.trim())}`); sug.hidden = true; });
  q.addEventListener("input", () => {
    clearTimeout(timer);
    if (q.value.trim().length < 3) { sug.hidden = true; return; }
    timer = setTimeout(async () => {
      try {
        const rows = await api(`/products/suggest?q=${encodeURIComponent(q.value.trim())}`, { label: "Search suggestions", source: "#header-q" });
        sug.innerHTML = rows.map((r) => `<a href="/p/${encodeURIComponent(r.sku)}" data-link>${esc(r.name)} <small>${esc(r.category)}</small></a>`).join("");
        sug.hidden = !rows.length;
      } catch { sug.hidden = true; }
    }, 300);
  });
  document.addEventListener("click", (e) => { if (!sug.contains(e.target)) sug.hidden = true; });
}

/* ---------------- start */
(async function start() {
  await loadConfig();
  await initLearnUi();
  $("#persona-chip").addEventListener("click", openPersonas);
  $("#bts-clear").addEventListener("click", () => panel.clear());
  setCartCount(Number(localStorage.getItem("vt_cart") || 0));
  showPersona();
  initSearch();
  if (session()) ws.connect();
  ws.on((m) => { if (m.type === "checkout.result") toast(`Order ${m.orderId}: ${m.status}`, m.status === "CONFIRMED" ? "ok" : "bad"); });
  await route();
  if (!persona()) openPersonas();
})();
