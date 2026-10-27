"""Lambda fulfillment (VPC): reads OrderPlaced from the order buffer queue and publishes FulfillOrder to RabbitMQ for the 3PL."""
import base64
import json
import os
import ssl
import time
import urllib.request

import pika

from voltaj import trace
from voltaj.events import unwrap

IDEM = os.environ["IDEMPOTENCY_TABLE"]
AMQP = os.environ["AMQP_ENDPOINT"]           # amqps://b-xxx.mq.eu-central-1.on.aws:5671
SECRET_ARN, THREEPL_ARN = os.environ["MQ_SECRET_ARN"], os.environ["THREEPL_SECRET_ARN"]
HOST = AMQP.split("//")[1].split(":")[0]
ddb, sm = trace.client("dynamodb"), trace.client("secretsmanager")
PATH = "Lambda ENI (private-app) → MQ cluster NLB (private-data, AMQPS 5671) → RabbitMQ node"
_state = {}


def _creds(arn):
    return json.loads(sm.get_secret_value(SecretId=arn)["SecretString"])


def _channel():
    ch = _state.get("ch")
    if ch is not None and ch.is_open:
        return ch
    c = _state.get("creds") or _creds(SECRET_ARN)
    _state["creds"] = c
    with trace.call("mq", "Connection.Open", f"pika.BlockingConnection(host='{HOST}', port=5671, ssl=TLS, user='{c['username']}')",
                    path=PATH, auth="RabbitMQ user (Secrets Manager)"):
        params = pika.ConnectionParameters(host=HOST, port=5671, virtual_host="/", credentials=pika.PlainCredentials(c["username"], c["password"]),
                                           ssl_options=pika.SSLOptions(ssl.create_default_context(), HOST), heartbeat=30,
                                           blocked_connection_timeout=10, connection_attempts=2, socket_timeout=10)
        conn = pika.BlockingConnection(params)
        ch = conn.channel()
        ch.confirm_delivery()
    _state.update(conn=conn, ch=ch)
    return ch


def _publish(evt, record):
    d = evt.get("detail") or {}
    order_id = d.get("orderId")
    trace.begin(d.get("cid"), d.get("vid"), fn="fulfillment")
    trace.note("sqs", "Receive (event source mapping)", f"Lambda polled the order buffer queue. Receive count "
               f"{record['attributes'].get('ApproximateReceiveCount')}.", sc="p4s1", st="1",
               event={"queue": "voltaj-order-buffer", "detailType": evt.get("detail-type"), "keys": {"orderId": order_id}})
    try:
        ddb.put_item(TableName=IDEM, Item={"pk": {"S": f"FUL#{d.get('eventId') or evt.get('id')}"}, "expiresAt": {"N": str(int(time.time()) + 86400)}},
                     ConditionExpression="attribute_not_exists(pk)")
    except ddb.exceptions.ConditionalCheckFailedException:
        trace.note("ddb", "Duplicate stopped", "This event ID was processed before (at-least-once delivery). The idempotency key "
                   "stops a second FulfillOrder.", sc="p4s1", st="1")
        trace.flush()
        return
    trace.step("p4s1", "2")
    msg = {"type": "FulfillOrder", "orderId": order_id, "lines": d.get("lines", []), "shipTo": d.get("shipTo"), "cid": d.get("cid"),
           "vid": d.get("vid")}
    with trace.call("mq", "basic.publish", f"channel.basic_publish(exchange='fulfillment', routing_key='3pl.orders', "
                    f"properties=BasicProperties(delivery_mode=2, type='FulfillOrder', message_id='{order_id}', "
                    f"headers={{cid, vid}}), body={json.dumps(msg)[:300]})", {"orderId": order_id}, path=PATH,
                    auth="RabbitMQ user (Secrets Manager)") as t:
        _channel().basic_publish(exchange="fulfillment", routing_key="3pl.orders", body=json.dumps(msg).encode(), mandatory=True,
                                 properties=pika.BasicProperties(delivery_mode=2, type="FulfillOrder", message_id=order_id,
                                                                 content_type="application/json",
                                                                 headers={"cid": d.get("cid") or "", "vid": d.get("vid") or ""}))
        t.result(note="Publisher confirms are on: the broker stored the message on a quorum queue (3 nodes) before it answered.")
    trace.note("mq", "To the VPN", "The 3PL WMS reads the queue 3pl.orders over the Site-to-Site VPN: MQ node → virtual private "
               "gateway → IPsec tunnel → 3PL network 172.16.0.0/16.", sc="p4s1", st="3")
    trace.flush()


def handle_sqs(event):
    failures = []
    for r in event["Records"]:
        try:
            _publish(unwrap(r["body"]), r)
        except Exception as e:  # noqa: BLE001 - report only the failed item
            print(f"failed {r['messageId']}: {e}")
            _state.pop("ch", None)
            trace.flush()
            failures.append({"itemIdentifier": r["messageId"]})
    return {"batchItemFailures": failures}


def _mgmt(method, path, body=None):
    c = _creds(SECRET_ARN)
    req = urllib.request.Request(f"https://{HOST}/api{path}", method=method, data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Content-Type": "application/json", "Authorization": "Basic " +
                                          base64.b64encode(f"{c['username']}:{c['password']}".encode()).decode()})
    with urllib.request.urlopen(req, timeout=15, context=ssl.create_default_context()) as r:
        return r.status


def setup(event):
    """Declare exchanges and quorum queues; create the 3PL user with narrow permissions."""
    trace.begin(None, "-", fn="fulfillment")
    ch = _channel()
    ch.exchange_declare("fulfillment", "direct", durable=True)
    ch.exchange_declare("shipments", "direct", durable=True)
    for q, ex, key in [("3pl.orders", "fulfillment", "3pl.orders"), ("shipments.events", "shipments", "shipments.events")]:
        ch.queue_declare(q, durable=True, arguments={"x-queue-type": "quorum"})
        ch.queue_bind(q, ex, routing_key=key)
    t = _creds(THREEPL_ARN)
    _mgmt("PUT", f"/users/{t['username']}", {"password": t["password"], "tags": ""})
    _mgmt("PUT", f"/permissions/%2F/{t['username']}", {"configure": "^$", "write": "^shipments$", "read": "^3pl\\.orders$"})
    trace.flush()
    return {"ok": True}


def queues(event):
    c = _creds(SECRET_ARN)
    req = urllib.request.Request(f"https://{HOST}/api/queues/%2F", headers={"Authorization": "Basic " +
                                 base64.b64encode(f"{c['username']}:{c['password']}".encode()).decode()})
    with urllib.request.urlopen(req, timeout=15, context=ssl.create_default_context()) as r:
        rows = json.loads(r.read())
    return {"queues": [{"name": q["name"], "type": q.get("type"), "messages": q.get("messages"), "consumers": q.get("consumers"),
                        "node": q.get("leader") or q.get("node"), "members": q.get("members"), "durable": q.get("durable"),
                        "arguments": q.get("arguments")} for q in rows if not q["name"].startswith("amq.")]}


def lambda_handler(event, context):
    if event.get("action") == "setup":
        return setup(event)
    if event.get("action") == "queues":
        return queues(event)
    return handle_sqs(event)
