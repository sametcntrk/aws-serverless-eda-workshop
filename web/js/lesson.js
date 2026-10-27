/* 101 lesson page (Turkish): the lesson text from lessons.json, filled with the visitor's real call and the service's real data. */
const $ = (s, r = document) => r.querySelector(s);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const vid = localStorage.getItem("vt_vid") || "-";
const id = location.pathname.split("/")[2] || "fanout";
const q = new URLSearchParams(location.search);
const SVC = { cf: "CloudFront", apigw: "API Gateway", lambda: "Lambda", sfn: "Step Functions", eb: "EventBridge", sns: "SNS", sqs: "SQS", pipes: "Pipes",
  ddb: "DynamoDB", aurora: "Aurora", aoss: "OpenSearch", osis: "OpenSearch Ingestion", s3: "S3", mq: "Amazon MQ", msk: "MSK", ses: "SES",
  eum: "End User Messaging", cognito: "Cognito", sm: "Secrets Manager", pay: "VoltPay", "3pl": "3PL WMS", guard: "Cost guard" };

/* Turkish explanation of each operation (by op name, then by service) */
const OP_TR = {
  StartExecution: "API Gateway, Step Functions iş akışını doğrudan başlattı ve hemen cevap verdi; iş arka planda sürüyor.",
  Query: "DynamoDB'den bir partition key'e ait satırlar okundu (Query sadece o anahtarın verisine dokunur).",
  GetItem: "Tek bir item anahtarıyla okundu.", PutItem: "Bir item yazıldı (aynı anahtar varsa üzerine yazar, koşul varsa önce kontrol eder).",
  UpdateItem: "Item'ın sadece belirli alanları değiştirildi; ADD gibi işlemler atomiktir.", DeleteItem: "Bir item silindi.",
  BatchGetItem: "Tek istekte birden çok item (burada iki tablodan) okundu.", BatchWriteItem: "Tek istekte birden çok item yazıldı veya silindi.",
  TransactWriteItems: "Birden çok yazma tek transaction'da: ya hepsi olur ya hiçbiri. Koşullardan biri tutmazsa hiçbir şey yazılmaz.",
  Search: "OpenSearch index'inde tam metin arama yapıldı; sonuçlar alaka puanına (score) göre sıralandı.",
  PutEvents: "Event bus'a bir event yazıldı. Kurallar şimdi bu event'i eşleştirip hedeflere kopyalayacak.",
  "Rule matched": "Bir EventBridge kuralının pattern'i event ile eşleşti; event kuralın hedefine gönderildi.",
  "Fan-out": "SNS mesajı bir aboneye (burada bir SQS kuyruğu) kopyaladı.",
  "Receive (event source mapping)": "Lambda servisi kuyruğu yokladı (polling) ve mesajı fonksiyona verdi; fonksiyon kuyruğu kendisi okumaz.",
  "basic.publish": "Mesaj RabbitMQ exchange'ine AMQP ile yazıldı; routing key mesajın hangi kuyruğa gideceğini belirler.",
  "Duplicate stopped": "Idempotency anahtarı zaten vardı; tüketici işi tekrar yapmadan durdu.",
  "Verify HMAC": "Webhook gövdesinin imzası paylaşılan gizli anahtarla yeniden hesaplandı ve karşılaştırıldı.",
  SendTaskSuccess: "Bekleyen task token'a başarı bildirildi; iş akışı kaldığı yerden devam etti.",
  SendTaskFailure: "Bekleyen task token'a hata bildirildi; iş akışı Catch bloğuna gitti.",
  "States.Timeout": "Ödeme adımının süresi doldu; Catch bloğu compensation'ı başlattı.",
  InitiateAuth: "Tarayıcı Cognito'ya kullanıcı adı ve şifreyle giriş isteği gönderdi.", RespondToAuthChallenge: "İkinci adım (TOTP kodu) gönderildi; Cognito token'ları verdi.",
  Produce: "Kayıtlar Kafka topic'ine yazıldı; her kayıt bir partition'a ve bir offset'e düşer.", SendEmail: "SES e-postayı template ile hazırladı ve gönderdi.",
  SendTextMessage: "End User Messaging SMS'i gönderdi (simülatör numarasına).", PostToConnection: "API Gateway açık WebSocket bağlantısına bir mesaj gönderdi.",
  "Presign PutObject": "Fonksiyon bir URL imzaladı; ağ çağrısı yok, imza fonksiyonun içinde hesaplanır.", "PUT (presigned)": "Tarayıcı dosyayı imzalı URL ile doğrudan S3'e yükledi.",
  PutObject: "S3'e bir nesne yazıldı.", GetObject: "S3'ten bir nesne okundu.", "Limit reached": "Maliyet koruması devreye girdi ve isteği durdurdu.",
  COMMIT: "PostgreSQL transaction'ı tamamlandı; sipariş ve satırları artık kalıcı.", BEGIN: "PostgreSQL transaction'ı başladı.",
};
const SVC_TR = { aurora: "Aurora PostgreSQL'e RDS Proxy üzerinden bir SQL komutu gitti.", mq: "Amazon MQ (RabbitMQ) ile AMQP üzerinden konuşuldu.",
  "3pl": "Depo simülatörü (3PL WMS) VPN'in diğer ucunda bir işlem yaptı.", pay: "Ödeme sağlayıcısı (VoltPay) tarafında bir işlem oldu.",
  lambda: "Bir Lambda fonksiyonu çalıştı veya çağrıldı.", eb: "EventBridge üzerinden bir event geçti.", sfn: "Step Functions iş akışında bir adım.",
  msk: "Kafka (MSK) üzerinde bir işlem.", apigw: "API Gateway üzerinden bir mesaj geçti.", pipes: "EventBridge Pipe bir mesajı işledi." };
const explain = (e) => OP_TR[e.op] || (e.op && e.op.startsWith("INSERT") ? "Bir satır tabloya eklendi (transaction'ın içinde)." : null) || SVC_TR[e.svc] || "Bir AWS çağrısı.";

async function getJson(path) {
  const r = await fetch(`/api${path}`, { headers: { "X-Vid": vid } });
  const j = await r.json();
  if (!j.ok) throw new Error(j.error || `HTTP ${r.status}`);
  return j.data;
}

/* ---------------- nested tree with type labels */
function typeOf(v) { return v === null ? "null" : Array.isArray(v) ? "array" : typeof v; }
function tree(v, key = null, marks = {}, path = "") {
  const t = typeOf(v);
  const label = key !== null ? `<span class="k">${esc(key)}</span>` : "";
  const mark = marks[path] ? `<span class="mark">${esc(marks[path])}</span>` : "";
  if (t === "object" || t === "array") {
    const entries = t === "array" ? v.map((x, i) => [i, x]) : Object.entries(v);
    return `<details open><summary>${label}<span class="t t-${t}">${t === "array" ? `array[${v.length}]` : "object"}</span>${mark}</summary>
      <ul>${entries.map(([k, x]) => `<li>${tree(x, k, marks, path ? `${path}.${k}` : String(k))}</li>`).join("")}</ul></details>`;
  }
  return `<div class="leaf">${label}<span class="t t-${t}">${t}</span><span class="v">${esc(t === "string" ? `"${v}"` : String(v))}</span>${mark}</div>`;
}

function stepBadge(e, sc) {
  const s = sc[e.sc];
  return s ? `<a class="step" style="--sc:${s.color}" href="/diagram?page=${s.page}&sc=${e.sc}&st=${encodeURIComponent(e.st || "")}" target="_blank" rel="noopener">P${s.page} · S${s.no}${e.st ? " · " + esc(e.st) : ""}</a>` : "";
}

(async function main() {
  const [lessons, index, scData] = await Promise.all([fetch("/data/lessons/lessons.json").then((r) => r.json()),
    fetch("/data/lessons/index.json").then((r) => r.json()), fetch("/data/scenarios.json").then((r) => r.json())]);
  const L = lessons[id] || lessons.fanout;
  const sc = {};
  for (const p of scData.pages) for (const s of p.scenarios) sc[s.id] = { page: p.page, no: s.no, color: s.color, title: s.title };
  document.title = `${L.title} · Voltaj 101`;
  $("#crumb").textContent = L.title;

  // the clicked call (from the shop tab through localStorage) and all entries of the same action
  let store = {};
  try { store = JSON.parse(localStorage.getItem("vt_learn") || "{}"); } catch { store = {}; }
  let entry = store[q.get("id")] || null;
  const cid = q.get("cid") || (entry && entry.cid);
  let entries = [];
  if (cid) { try { entries = await getJson(`/learn/trace?cid=${encodeURIComponent(cid)}`); } catch { entries = Object.values(store).filter((e) => e.cid === cid); } }
  if (!entry && entries.length) entry = entries.find((e) => e.id === q.get("id")) || entries[0];
  entries.sort((a, b) => (a.sk || "").localeCompare(b.sk || ""));

  // values for the hero sentence and the focus of the big picture
  const text = JSON.stringify(entries) + JSON.stringify(entry || {});
  const orderId = (text.match(/o-[a-z0-9]{6,12}/) || [])[0] || "";
  const qv = (text.match(/\\"query\\": \\"([^"\\]+)/) || [])[1] || "";
  const sku = (text.match(/VLT-\d{4}|demo-[a-z0-9-]+/) || [])[0] || "";
  const name = (JSON.parse(localStorage.getItem("vt_session") || "null") || {}).key || "";
  const focus = [cid, orderId, sku, sku && `SKU#${sku}`].filter(Boolean).join(",");
  const hero = L.hero.replace("{orderId}", orderId || "(sipariş)").replace("{q}", qv || "bir ürün").replace("{name}", name || "bir persona");

  $("#lesson").innerHTML = `
    <header class="l-hero"><p class="kicker">101 · ${esc(L.summary)}</p><h1>${esc(L.title)}</h1><p class="question">${esc(hero)}</p>
      ${entry ? `<p class="from">Bu ders şu çağrıdan açıldı: ${stepBadge(entry, sc)} <b>${esc(SVC[entry.svc] || entry.svc)}</b> · ${esc(entry.op)} · ${entry.ms ?? 0} ms</p>`
        : `<p class="from warn">Bu dersi mağazadan açmadın, bu yüzden kendi çağrın yok. Önce mağazada bir şey yap ve paneldeki “101” linkine tıkla. Aşağıdaki büyük resim yine gerçek veriyi gösterir.</p>`}</header>
    <section class="l-sec"><h2>1 · Fikir</h2><p>${esc(L.idea)}</p></section>
    <section class="l-sec" id="big"><h2>2 · Büyük resim → seçili kayıt → iç içe yapı</h2>
      <div class="bp"><div class="bp-left"><div id="bp-head"></div><div id="bp-shelves"><p class="empty"><span class="spinner"></span></p></div></div>
      <div class="bp-right"><div id="bp-item" class="bp-item"><p class="meta">Soldan bir kutuya tıkla. Seçili kaydın tamamı burada iç içe bir ağaç olarak, her alanın tipiyle görünür.</p></div></div></div></section>
    <section class="l-sec"><h2>3 · Kaynakta veri böyleydi, burada böyle duruyor</h2><p>${esc(L.stored)}</p><div id="src-vs" class="src-vs"></div></section>
    <section class="l-sec"><h2>4 · Senin çağrın adım adım</h2>
      ${entries.length ? `<ol class="l-steps">${entries.map((e) => `<li class="${e.id === (entry || {}).id ? "me" : ""} ${e.ok === false ? "bad" : ""}">
        <div class="l-step-head">${stepBadge(e, sc)}<b>${esc(SVC[e.svc] || e.svc)}</b> · <code>${esc(e.op)}</code><span class="ms">${e.ms ?? 0} ms</span></div>
        <p>${esc(explain(e))}</p>${e.note ? `<p class="orig">${esc(e.note)}</p>` : ""}${e.error ? `<p class="bad">${esc(e.error)}</p>` : ""}</li>`).join("")}</ol>`
        : `<p class="meta">Henüz çağrı yok. Mağazada bu konuyla ilgili bir işlem yap.</p>`}</section>
    <section class="l-sec"><h2>5 · Günlük hayattan bir benzetme</h2><p class="analogy">${esc(L.analogy)}</p></section>
    <section class="l-sec"><h2>6 · ${esc(L.compare.title)}</h2>
      <div class="cmp-wrap"><table class="cmp"><thead><tr><th>Seçenek</th>${L.compare.criteria.map((c) => `<th>${esc(c)}</th>`).join("")}</tr></thead>
      <tbody>${L.compare.options.map((o, i) => `<tr class="${i === 0 ? "chosen" : ""}"><th>${esc(o.name)}</th>${o.cells.map((c) => `<td class="${c.startsWith("✓") ? "y" : c.startsWith("✕") ? "n" : c.startsWith("~") ? "m" : ""}">${esc(c)}</td>`).join("")}</tr>`).join("")}</tbody></table></div>
      <p class="legend">✓ destekler · ~ kısmen veya şartlı · ✕ desteklemez</p>
      <div class="decision"><b>Karar</b><p>${esc(L.compare.decision)}</p></div>
      <p class="sources">Kaynaklar (AWS dokümanları): ${L.compare.sources.map((s) => `<a href="${esc(s.url)}" target="_blank" rel="noopener">${esc(s.title)}</a>`).join(" · ")}</p></section>
    <section class="l-sec l-grid"><div><h2>7 · Kendin dene</h2><ul>${L.try.map((t) => `<li><a href="${esc(t.href)}">${esc(t.text)}</a></li>`).join("")}</ul>
      <h2>Sözlük</h2><dl class="gloss">${L.glossary.map(([t, d]) => `<dt>${esc(t)}</dt><dd>${esc(d)}</dd>`).join("")}</dl></div>
      <div><h2>Tüm dersler</h2><ol class="l-index">${index.map((x) => `<li${x.id === id ? ' aria-current="page"' : ""}><a href="/learn/${x.id}${cid ? `?cid=${encodeURIComponent(cid)}` : ""}">${esc(x.title)}</a></li>`).join("")}</ol></div></section>`;

  // section 3: the source form next to the stored form
  const srcVs = $("#src-vs");
  if (entry) srcVs.innerHTML = `<div><h3>Senin isteğin</h3><pre>${esc(entry.request || "-")}</pre></div>
      <div><h3>Kayıt ve event alanları</h3>${tree({ params: entry.params || {}, event: entry.event || {}, data: entry.data || {} })}</div>`;

  // section 2: big picture
  try {
    const ov = await getJson(`/learn/overview?${new URLSearchParams({ lesson: L.overview || id, focus })}`);
    $("#bp-head").innerHTML = `<h3>${esc(ov.title)}</h3><p class="meta">${esc(ov.text)}</p>
      <div class="facts">${(ov.facts || []).map(([v, l]) => `<span><b>${esc(v)}</b> ${esc(l)}</span>`).join("")}</div>
      ${ov.hit_label && ov.hit_label !== "-" ? `<p class="meta"><span class="tile hit sample"></span> = ${esc(ov.hit_label)}</p>` : ""}`;
    $("#bp-shelves").innerHTML = (ov.groups || []).length ? ov.groups.map((g) => `<div class="shelf"><h4>${esc(g.label)} <small>${g.items.length}</small></h4>
      <div class="tiles">${g.items.map((it) => `<button type="button" class="tile ${it.hit ? "hit" : ""}" data-id="${esc(it.id)}" title="${esc(it.title)}">${esc(it.title)}</button>`).join("")
        || `<p class="meta">Bu grup boş. Mağazada ilgili işlemi yap, sonra bu sayfayı yenile.</p>`}</div></div>`).join("")
      : `<p class="empty">Burada henüz kayıt yok. Mağazada ilgili işlemi yap ve sayfayı yenile.</p>`;
    const open = async (btn) => {
      document.querySelectorAll(".tile.sel").forEach((t) => t.classList.remove("sel"));
      btn.classList.add("sel");
      $("#bp-item").innerHTML = `<p class="empty"><span class="spinner"></span></p>`;
      try {
        const it = await getJson(`/learn/item?${new URLSearchParams({ lesson: L.overview || id, id: btn.dataset.id, focus })}`);
        $("#bp-item").innerHTML = `<h3>${esc(it.title)}</h3><p class="meta">${esc(it.sub || "")}</p>${it.image ? `<img src="${esc(it.image)}" alt="" class="bp-img">` : ""}
          ${it.extra && it.extra.matchedRules ? `<p class="meta">Eşleşen kurallar: <b>${it.extra.matchedRules.map(esc).join(", ") || "yok"}</b></p>` : ""}
          <div class="tree">${tree(it.record, null, it.marks || {})}</div>
          ${it.source && Object.keys(it.source).length ? `<h3>Kaynakta (DynamoDB, tipli JSON)</h3><div class="tree">${tree(it.source)}</div>` : ""}
          ${it.typed ? `<details><summary>DynamoDB'nin gördüğü tipli hali (S, N, L, M)</summary><div class="tree">${tree(it.typed)}</div></details>` : ""}`;
        if (it.source && Object.keys(it.source).length) {
          srcVs.innerHTML = `<div><h3>Kaynak: DynamoDB item (tipli)</h3><div class="tree">${tree(it.source)}</div></div><div><h3>Hedef: OpenSearch dokümanı</h3><div class="tree">${tree(it.record)}</div></div>`;
        }
      } catch (e) { $("#bp-item").innerHTML = `<p class="bad">${esc(e.message)}</p>`; }
    };
    document.querySelectorAll(".tile[data-id]").forEach((b) => b.addEventListener("click", () => open(b)));
    const first = document.querySelector(".tile.hit[data-id]") || document.querySelector(".tile[data-id]");
    if (first) open(first);
  } catch (e) {
    $("#bp-shelves").innerHTML = `<p class="bad">Büyük resim okunamadı: ${esc(e.message)}</p>`;
  }
})();
