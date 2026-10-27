"""3PL WMS simulator: reads FulfillOrder from the queue 3pl.orders over the VPN, answers ShipmentDispatched after a short time.

Runs on the 3PL EC2 instance (network 172.16.0.0/16). It also writes trace entries, so the shop visitor sees the 3PL side.
"""
import json
import random
import socket
import ssl
import time
import uuid

import boto3
import pika

REGION = "eu-central-1"
cfg = json.load(open("/etc/wms.json"))
sec = json.loads(boto3.client("secretsmanager", region_name=REGION).get_secret_value(SecretId=cfg["secret"])["SecretString"])
ddb = boto3.client("dynamodb", region_name=REGION)
MY_IP = socket.gethostbyname(socket.gethostname())
CARRIERS = ["Aras Kargo", "Yurtici Kargo", "DHL Express", "MNG Kargo"]


def note(cid, vid, sc, st, op, text, request="", ms=0):
    if not cid:
        return
    t = time.time()
    ts = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(t)) + f".{int(t * 1000) % 1000:03d}+00:00"
    item = {"cid": cid, "sk": f"{ts}#3pl#{uuid.uuid4().hex[:4]}", "id": uuid.uuid4().hex[:10], "vid": vid or "-", "fn": "3pl-wms",
            "svc": "3pl", "engine": "3PL WMS (simulator)", "op": op, "note": text, "request": request, "sc": sc, "st": st, "ts": ts,
            "ms": ms, "ok": True, "path": f"3PL EC2 {MY_IP} (172.16.0.0/16) ⇄ IPsec tunnel ⇄ virtual private gateway ⇄ MQ node (private-data)",
            "auth": "RabbitMQ user wms3pl (read 3pl.orders, write shipments)", "expiresAt": int(t) + 86400}
    try:
        ddb.put_item(TableName="voltaj-trace", Item={k: ({"S": v} if isinstance(v, str) else {"BOOL": v} if isinstance(v, bool) else {"N": str(v)})
                                                      for k, v in item.items()})
    except Exception as e:  # noqa: BLE001
        print("trace failed", e)


def main():
    host = cfg["host"]
    params = pika.ConnectionParameters(host=host, port=5671, credentials=pika.PlainCredentials(sec["username"], sec["password"]),
                                       ssl_options=pika.SSLOptions(ssl.create_default_context(), host), heartbeat=30)
    conn = pika.BlockingConnection(params)
    ch = conn.channel()
    ch.basic_qos(prefetch_count=5)

    def on_msg(chan, method, props, body):
        t0 = time.time()
        msg = json.loads(body)
        h = props.headers or {}
        cid, vid, oid = h.get("cid") or msg.get("cid"), h.get("vid") or msg.get("vid"), msg.get("orderId")
        note(cid, vid, "p4s1", "4", "basic.deliver → basic.ack", f"The WMS got FulfillOrder {oid} through the IPsec tunnel and sent "
             "basic.ack. The broker deletes the message from the quorum queue.", f"basic.consume(queue='3pl.orders') → message_id={oid}")
        chan.basic_ack(method.delivery_tag)
        if str(oid).startswith("o-burst"):
            return
        time.sleep(random.uniform(4, 8))  # picking and packing
        reply = {"type": "ShipmentDispatched", "orderId": oid, "eventId": f"{oid}-shipped", "carrier": random.choice(CARRIERS),
                 "trackingNo": f"VT{random.randint(10**9, 10**10 - 1)}", "cid": cid, "vid": vid}
        chan.basic_publish("shipments", "shipments.events", json.dumps(reply).encode(),
                           pika.BasicProperties(delivery_mode=2, type="ShipmentDispatched", message_id=reply["eventId"],
                                                content_type="application/json", headers={"cid": cid or "", "vid": vid or ""}))
        note(cid, vid, "p4s2", "1", "basic.publish ShipmentDispatched", f"The parcel left the warehouse ({reply['carrier']}, "
             f"{reply['trackingNo']}). The WMS published ShipmentDispatched to the exchange shipments.",
             f"basic_publish(exchange='shipments', routing_key='shipments.events', type='ShipmentDispatched', body={json.dumps(reply)})",
             ms=round((time.time() - t0) * 1000))
        note(cid, vid, "p4s2", "2", "Into the VPC", "The message went through the VPN into the VPC. It waits in the quorum queue "
             "shipments.events for the pipe.")

    ch.basic_consume("3pl.orders", on_msg)
    print("WMS consuming 3pl.orders", flush=True)
    ch.start_consuming()


if __name__ == "__main__":
    while True:
        try:
            main()
        except Exception as e:  # noqa: BLE001 - reconnect (VPN or broker restart)
            print("reconnect after error:", e, flush=True)
            time.sleep(10)
