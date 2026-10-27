"""VoltPay - the payment provider simulator (an external actor in the story). Hosted checkout page, HMAC-signed webhooks.

POST /v1/payments              (Bearer API key, Idempotency-Key)  → {id, checkoutUrl}
GET  /checkout/<id>            the hosted payment page
POST /checkout/<id>/decide     {decision: pay | decline | none}   → sends the webhook (none sends nothing: the saga times out)
"""
import hashlib
import hmac
import html
import json
import os
import time
import urllib.request
import uuid

import boto3

TABLE = os.environ["PAYMENTS_TABLE"]
SECRET_ARN = os.environ["PAY_SECRET_ARN"]
WEBHOOK = os.environ["WEBHOOK_URL"]
PUBLIC = os.environ["PUBLIC_URL"]
TRACE = os.environ.get("TRACE_TABLE", "voltaj-trace")
ddb = boto3.client("dynamodb")
_sec = {}


def secret():
    if not _sec:
        _sec.update(json.loads(boto3.client("secretsmanager").get_secret_value(SecretId=SECRET_ARN)["SecretString"]))
    return _sec


def note(meta, sc, st, op, text, request=""):
    """The simulator also writes to the learning trace, so the visitor sees the provider side."""
    if not meta.get("cid"):
        return
    now = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime()) + f".{int(time.time() * 1000) % 1000:03d}+00:00"
    item = {"cid": meta["cid"], "sk": f"{now}#paysim#{uuid.uuid4().hex[:4]}", "id": uuid.uuid4().hex[:10], "vid": meta.get("vid", "-"),
            "fn": "paysim", "svc": "pay", "engine": "Payment provider (VoltPay)", "op": op, "note": text, "request": request,
            "sc": sc, "st": st, "ts": now, "ms": 0, "ok": True, "path": "Internet (VoltPay is outside AWS in the story)",
            "expiresAt": int(time.time()) + 86400}
    ddb.put_item(TableName=TRACE, Item={k: ({"S": v} if isinstance(v, str) else {"BOOL": v} if isinstance(v, bool) else {"N": str(v)})
                                        for k, v in item.items()})


def resp(status, body, ctype="application/json"):
    return {"statusCode": status, "headers": {"Content-Type": ctype, "Cache-Control": "no-store"},
            "body": body if isinstance(body, str) else json.dumps(body)}


def create(event, body):
    auth = (event.get("headers") or {}).get("authorization", "")
    if auth != f"Bearer {secret()['apiKey']}":
        return resp(401, {"error": "bad API key"})
    key = (event.get("headers") or {}).get("idempotency-key") or str(uuid.uuid4())
    got = ddb.get_item(TableName=TABLE, Key={"pk": {"S": f"IDEM#{key}"}})
    if "Item" in got:
        pid = got["Item"]["paymentId"]["S"]
        return resp(200, {"id": pid, "checkoutUrl": f"{PUBLIC}/checkout/{pid}", "idempotent": True})
    pid = "pay_" + uuid.uuid4().hex[:10]
    meta = body.get("metadata") or {}
    rec = {"pk": {"S": pid}, "status": {"S": "pending"}, "amount": {"N": str(body.get("amount", 0))}, "currency": {"S": body.get("currency", "EUR")},
           "orderId": {"S": body.get("orderId", "")}, "returnUrl": {"S": body.get("returnUrl", "")}, "meta": {"S": json.dumps(meta)},
           "expiresAt": {"N": str(int(time.time()) + 86400)}}
    ddb.put_item(TableName=TABLE, Item=rec)
    ddb.put_item(TableName=TABLE, Item={"pk": {"S": f"IDEM#{key}"}, "paymentId": {"S": pid}, "expiresAt": {"N": str(int(time.time()) + 86400)}})
    note(meta, "p3s1", "6", "Create the payment", f"VoltPay created {pid} for {body.get('amount')} {body.get('currency', 'EUR')}. The "
         "request came from the NAT gateway Elastic IP of the shop.", f"POST /v1/payments  Idempotency-Key: {key}")
    return resp(201, {"id": pid, "status": "pending", "checkoutUrl": f"{PUBLIC}/checkout/{pid}"})


PAGE = """<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>VoltPay checkout</title><style>
body{{margin:0;font:16px/1.5 system-ui,sans-serif;background:#f3f1ec;color:#1d1d1f;display:grid;place-items:center;min-height:100vh}}
.card{{background:#fff;border-radius:18px;box-shadow:0 10px 40px #0002;padding:32px;max-width:420px;width:92%}}
.brand{{font-weight:800;letter-spacing:.02em;color:#3d2a8c}} .amt{{font-size:2.2rem;font-weight:700;margin:.2em 0}}
.muted{{color:#6b6b70;font-size:.9rem}} button{{width:100%;padding:14px;border-radius:12px;border:0;font-size:1rem;font-weight:600;margin-top:10px;cursor:pointer}}
.pay{{background:#3d2a8c;color:#fff}} .decline{{background:#fff;border:2px solid #c0392b;color:#c0392b}} .none{{background:#eee;color:#444}}
.note{{background:#fff8e1;border-radius:10px;padding:10px 12px;font-size:.85rem;margin-top:16px}} #done{{font-weight:600;margin-top:14px}}
</style></head><body><main class="card"><div class="brand">VoltPay</div><p class="muted">Payment for order {order}</p>
<div class="amt">€{amount}</div><p class="muted">Card •••• 4242 · test mode</p>
<button class="pay" data-d="pay">Pay</button><button class="decline" data-d="decline">Decline</button>
<button class="none" data-d="none">No answer (let the saga time out)</button><p id="done" role="status"></p>
<p class="note">VoltPay is a simulator. It is the external payment provider of the story. Pay and Decline send an HMAC-signed
webhook to the shop. No answer sends nothing: the workflow waits until its timeout and then runs the compensation.</p>
<p><a href="{ret}">Back to the shop</a></p></main>
<script>
document.querySelectorAll('button').forEach(b => b.addEventListener('click', async () => {{
  document.querySelectorAll('button').forEach(x => x.disabled = true);
  const r = await fetch(location.pathname + '/decide', {{method: 'POST', headers: {{'Content-Type': 'application/json'}},
    body: JSON.stringify({{decision: b.dataset.d}})}});
  const j = await r.json();
  document.getElementById('done').textContent = j.message;
  if (b.dataset.d !== 'none') setTimeout(() => {{ window.close(); }}, 1500);
}}));
</script></body></html>"""


def page(pid):
    got = ddb.get_item(TableName=TABLE, Key={"pk": {"S": pid}})
    if "Item" not in got:
        return resp(404, "<h1>Unknown payment</h1>", "text/html")
    i = got["Item"]
    return resp(200, PAGE.format(order=html.escape(i["orderId"]["S"]), amount=f"{float(i['amount']['N']):.2f}",
                                 ret=html.escape(i["returnUrl"]["S"] or "#")), "text/html; charset=utf-8")


def decide(pid, body):
    got = ddb.get_item(TableName=TABLE, Key={"pk": {"S": pid}})
    if "Item" not in got:
        return resp(404, {"message": "Unknown payment."})
    i = got["Item"]
    if i["status"]["S"] != "pending":
        return resp(409, {"message": f"This payment is already {i['status']['S']}."})
    d = body.get("decision")
    meta = json.loads(i["meta"]["S"])
    status = {"pay": "succeeded", "decline": "failed", "none": "abandoned"}.get(d, "abandoned")
    ddb.update_item(TableName=TABLE, Key={"pk": {"S": pid}}, UpdateExpression="SET #s = :s", ExpressionAttributeNames={"#s": "status"},
                    ExpressionAttributeValues={":s": {"S": status}})
    if d == "none":
        note(meta, "p3s4", "1", "No answer", "VoltPay sends no webhook. The saga waits until the payment task times out.")
        return resp(200, {"message": "No webhook sent. The shop workflow will time out and undo the reservation."})
    evt = {"id": "evt_" + uuid.uuid4().hex[:10], "type": f"payment.{status}", "created": int(time.time()),
           "data": {"paymentId": pid, "orderId": i["orderId"]["S"], "status": status, "reason": None if d == "pay" else "card_declined",
                    "cid": meta.get("cid"), "vid": meta.get("vid")}}
    raw = json.dumps(evt)
    t = str(int(time.time()))
    sig = hmac.new(secret()["webhookSecret"].encode(), f"{t}.{raw}".encode(), hashlib.sha256).hexdigest()
    note(meta, "p3s2", "1", "Send the webhook", f"VoltPay sends {evt['type']} to the shop over the internet. CloudFront and WAF receive it first.",
         f"POST {WEBHOOK}\nPayment-Signature: t={t},v1={sig[:16]}…\n{raw[:300]}")
    req = urllib.request.Request(WEBHOOK, data=raw.encode(), method="POST", headers={
        "Content-Type": "application/json", "Payment-Signature": f"t={t},v1={sig}", "User-Agent": "VoltPay-Webhooks/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            code = r.status
    except urllib.error.HTTPError as e:
        code = e.code
    return resp(200, {"message": f"Webhook sent ({evt['type']}); the shop answered HTTP {code}. You can close this tab."})


def lambda_handler(event, context):
    method = event.get("requestContext", {}).get("http", {}).get("method", "GET")
    path = event.get("rawPath", "/")
    try:
        body = json.loads(event.get("body") or "{}")
    except ValueError:
        body = {}
    parts = [p for p in path.split("/") if p]
    if method == "POST" and parts == ["v1", "payments"]:
        return create(event, body)
    if method == "GET" and len(parts) == 2 and parts[0] == "checkout":
        return page(parts[1])
    if method == "POST" and len(parts) == 3 and parts[0] == "checkout" and parts[2] == "decide":
        return decide(parts[1], body)
    if path in ("/", "/health"):
        return resp(200, {"service": "VoltPay simulator", "ok": True})
    return resp(404, {"error": "not found"})
