"""Lambda producer (VPC): writes clickstream (from /api/events) and the commerce event log (EventBridge rule) to MSK Serverless."""
import json
import os
import time

from aws_msk_iam_sasl_signer import MSKAuthTokenProvider
from kafka import KafkaProducer
from kafka.admin import KafkaAdminClient, NewTopic

from voltaj import guard, trace
from voltaj.api import HttpError, handler as api_handler

BOOTSTRAP = os.environ["MSK_BOOTSTRAP"]
REGION = os.environ.get("AWS_REGION", "eu-central-1")
PATH = "Lambda ENI (private-app) → MSK Serverless VPC endpoint (private-data, SASL_SSL 9098)"
AUTH = "IAM (SASL OAUTHBEARER token signed with the function role)"
_state = {}


try:
    from kafka.net.sasl.oauth import AbstractTokenProvider
except ImportError:  # kafka-python 2.x
    from kafka.sasl.oauth import AbstractTokenProvider


class _Token(AbstractTokenProvider):
    def token(self):
        tok, _ = MSKAuthTokenProvider.generate_auth_token(REGION)
        return tok


def _cfg():
    return dict(bootstrap_servers=BOOTSTRAP.split(","), security_protocol="SASL_SSL", sasl_mechanism="OAUTHBEARER",
                sasl_oauth_token_provider=_Token(), client_id="voltaj-producer")


def _producer():
    p = _state.get("p")
    if p is None:
        with trace.call("msk", "Connect", f"KafkaProducer(bootstrap_servers='{BOOTSTRAP.split(',')[0]}', security_protocol='SASL_SSL', "
                        "sasl_mechanism='OAUTHBEARER', acks='all')", path=PATH, auth=AUTH):
            p = KafkaProducer(acks="all", linger_ms=5, value_serializer=lambda v: json.dumps(v).encode(),
                              key_serializer=lambda k: k.encode(), **_cfg())
        _state["p"] = p
    return p


def _send(topic, key, value, headers):
    hdrs = [(k, (v or "").encode()) for k, v in headers.items()]
    fut = _producer().send(topic, key=key, value=value, headers=hdrs)
    return fut


def events(req):
    batch = req.body.get("events") if isinstance(req.body, dict) else None
    if not isinstance(batch, list) or not batch:
        raise HttpError(400, "Send {events: [...]}.")
    batch = batch[:50]
    guard.hit(f"clicks#{req.vid}", 120, 60, "Clickstream batches")
    trace.step("p5s6", "4")
    session = str(req.body.get("session") or req.vid)
    with trace.call("msk", "Produce", f"producer.send('clickstream', key='{session}', value=<{len(batch)} events>, headers=[cid, vid])"
                    f"\nfirst: {json.dumps(batch[0])[:200]}", {"events": len(batch)}, path=PATH, auth=AUTH) as t:
        futs = [_send("clickstream", session, dict(e, session=session, vid=req.vid, at=e.get("ts") or int(time.time() * 1000)),
                      {"cid": trace.cid(), "vid": req.vid}) for e in batch]
        _producer().flush(timeout=10)
        md = futs[-1].get(timeout=10)
        t.result(items=len(batch), note=f"Kafka stored the records on partition {md.partition} at offset {md.offset}. "
                 "Two consumer groups (archive, counters) read the same records independently.",
                 data={"partition": md.partition, "offset": md.offset})
    return {"accepted": len(batch), "partition": md.partition, "offset": md.offset}


def commerce_log(evt):
    d = evt.get("detail") or {}
    trace.begin(d.get("cid"), d.get("vid"), fn="producer")
    trace.note("eb", "Rule commerce-log", "The rule commerce-log invoked this function with the event.", sc="p3s5", st="1c",
               event={"source": evt.get("source"), "detailType": evt.get("detail-type"), "bus": "voltaj-commerce",
                      "keys": {"orderId": d.get("orderId")}})
    trace.step("p3s5", "2")
    key = d.get("orderId") or evt.get("id")
    with trace.call("msk", "Produce", f"producer.send('commerce-events', key='{key}', value=<the event JSON>)", {"key": key},
                    path=PATH, auth=AUTH) as t:
        md = _send("commerce-events", key, evt, {"cid": d.get("cid"), "vid": d.get("vid")}).get(timeout=10)
        t.result(note=f"Partition {md.partition}, offset {md.offset}. The log keeps every commerce event for analytics.")
    trace.flush()
    return {"ok": True}


def setup(event):
    admin = KafkaAdminClient(**_cfg())
    have = set(admin.list_topics())
    new = [NewTopic(t, num_partitions=n, replication_factor=3) for t, n in (("clickstream", 3), ("commerce-events", 3)) if t not in have]
    if new:
        admin.create_topics(new)
    return {"topics": sorted(set(admin.list_topics()))}


_api = api_handler("producer", {("POST", "/events"): events})


def burst(event):
    import random
    trace.begin(event.get("cid"), event.get("vid"), fn="producer")
    n = min(int(event.get("n") or 500), 1000)
    skus = [f"VLT-{1001 + i}" for i in range(200)]
    with trace.call("msk", "Produce (burst)", f"{n} x producer.send('clickstream', key=<session>, value={{type: page_view, sku}})",
                    {"events": n}, path=PATH, auth=AUTH) as t:
        for i in range(n):
            s = f"burst-{i % 40}"
            _send("clickstream", s, {"type": "page_view", "sku": random.choice(skus[:40]), "session": s, "vid": "burst",
                                     "at": int(time.time() * 1000)}, {"cid": event.get("cid") or "", "vid": "burst"})
        _producer().flush(timeout=20)
        t.result(items=n)
    trace.flush()
    return {"sent": n}


def lambda_handler(event, context):
    if event.get("action") == "burst":
        return burst(event)
    if "httpMethod" in event:
        return _api(event, context)
    if event.get("action") == "setup":
        return setup(event)
    return commerce_log(event)
