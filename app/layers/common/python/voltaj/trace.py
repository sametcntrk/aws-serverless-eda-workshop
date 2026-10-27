"""Live trace: every AWS call (and every non-AWS call wrapped by hand) becomes one trace entry.

Entries go to the DynamoDB table voltaj-trace (pk = cid). Its stream feeds the trace-push function, which sends each
entry over the WebSocket to the browser of the visitor. Synchronous API responses also return their entries.

Usage in a handler:
    trace.begin(cid, vid, fn="product")
    trace.step("p2s3", "4")                      # diagram scenario and step of the next calls
    resp = aws.client("dynamodb").get_item(...)  # traced automatically by botocore hooks
    with trace.call("aurora", "INSERT", "INSERT INTO orders ...", {"orderId": oid}) as t:
        cur.execute(...)
        t.result(items=1)
    entries = trace.flush()
"""
import json
import os
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from decimal import Decimal

import boto3

TABLE = os.environ.get("TRACE_TABLE", "voltaj-trace")
TTL_S = 24 * 3600
FN = os.environ.get("TRACE_FN") or os.environ.get("AWS_LAMBDA_FUNCTION_NAME", "local").replace("voltaj-", "")
IN_VPC = os.environ.get("IN_VPC") == "1"

# Service id (colour in the panel) and label per botocore service name.
SERVICES = {
    "dynamodb": ("ddb", "Amazon DynamoDB"), "states": ("sfn", "AWS Step Functions"), "events": ("eb", "Amazon EventBridge"),
    "sns": ("sns", "Amazon SNS"), "sqs": ("sqs", "Amazon SQS"), "s3": ("s3", "Amazon S3"), "sesv2": ("ses", "Amazon SES"),
    "ses": ("ses", "Amazon SES"), "apigatewaymanagementapi": ("apigw", "API Gateway (WebSocket)"),
    "cognito-idp": ("cognito", "Amazon Cognito"), "secretsmanager": ("sm", "AWS Secrets Manager"), "kafka": ("msk", "Amazon MSK"),
    "pinpoint-sms-voice-v2": ("eum", "AWS End User Messaging"), "rds": ("aurora", "Amazon RDS"), "lambda": ("lambda", "AWS Lambda"),
    "cloudwatch": ("cw", "Amazon CloudWatch"), "pipes": ("pipes", "EventBridge Pipes"), "mq": ("mq", "Amazon MQ"),
}
LABELS = {sid: label for sid, label in SERVICES.values()}
LABELS.update({"aoss": "OpenSearch Serverless", "aurora": "Aurora PostgreSQL", "mq": "Amazon MQ (RabbitMQ)", "msk": "Amazon MSK",
               "pay": "Payment provider", "3pl": "3PL WMS", "lambda": "AWS Lambda", "apigw": "Amazon API Gateway", "guard": "Cost guard",
               "osis": "OpenSearch Ingestion", "cf": "Amazon CloudFront"})
GATEWAY_EP = {"dynamodb", "s3"}
INTERFACE_EP = {"events", "states", "sns", "sqs", "secretsmanager", "sts", "logs", "lambda"}
# DynamoDB on-demand prices in eu-central-1 (USD per request unit).
WRU_USD, RRU_USD = 0.7625 / 1e6, 0.1525 / 1e6
DDB_CAPACITY_OPS = {"GetItem", "PutItem", "UpdateItem", "DeleteItem", "Query", "Scan", "BatchGetItem", "BatchWriteItem",
                    "TransactWriteItems", "TransactGetItems"}

_ctx = {"cid": None, "vid": None, "sc": None, "st": None, "entries": [], "seq": 0}
_writer = boto3.client("dynamodb")      # not traced: writes the trace itself


def begin(cid=None, vid=None, fn=None, sc=None, st=None):
    """Start a new trace context for one invocation (or one record of a batch)."""
    global FN
    if fn:
        FN = fn
    _ctx.update(cid=cid or f"c-{uuid.uuid4().hex[:12]}", vid=vid or "-", sc=sc, st=st, entries=[], seq=0)
    return _ctx["cid"]


def cid():
    return _ctx["cid"]


def vid():
    return _ctx["vid"]


def step(sc, st=None):
    """Set the diagram scenario (for example p3s1) and step (for example 2) of the next entries."""
    _ctx["sc"], _ctx["st"] = sc, st


def _plain(v):
    """DynamoDB typed value → plain value, for a readable request text."""
    if isinstance(v, dict) and len(v) == 1:
        (t, x), = v.items()
        if t in ("S", "N", "BOOL"):
            return x
        if t == "M":
            return {k: _plain(y) for k, y in x.items()}
        if t == "L":
            return [_plain(y) for y in x]
        if t == "NULL":
            return None
    if isinstance(v, dict):
        return {k: _plain(y) for k, y in v.items()}
    if isinstance(v, list):
        return [_plain(y) for y in v]
    return v


def _short(v, n=600):
    s = v if isinstance(v, str) else json.dumps(v, default=str, ensure_ascii=False)
    return s if len(s) <= n else s[: n - 1] + "…"


def _render(service, op, params):
    keep = {k: v for k, v in params.items() if k not in ("ReturnConsumedCapacity",)}
    if "TaskToken" in keep:
        keep["TaskToken"] = keep["TaskToken"][:12] + "…"
    if "Body" in keep and not isinstance(keep["Body"], str):
        keep["Body"] = "<bytes>"
    args = ", ".join(f"{k}={_short(_plain(v), 160)}" for k, v in keep.items())
    method = "".join("_" + c.lower() if c.isupper() else c for c in op).lstrip("_")
    return _short(f"{service}.{method}({args})", 900)


def _path(service):
    src = "Lambda ENI (private-app subnet)" if IN_VPC else "Lambda (AWS network)"
    if IN_VPC and service in GATEWAY_EP:
        return f"{src} → gateway VPC endpoint → {service}"
    if IN_VPC and service in INTERFACE_EP:
        return f"{src} → interface VPC endpoint → {service}"
    if IN_VPC:
        return f"{src} → NAT gateway → {service} public endpoint"
    return f"{src} → {service} regional endpoint"


def _event_fields(service, op, params):
    if service == "events" and op == "PutEvents":
        e = (params.get("Entries") or [{}])[0]
        try:
            detail = json.loads(e.get("Detail") or "{}")
        except ValueError:
            detail = {}
        return {"source": e.get("Source"), "detailType": e.get("DetailType"), "bus": e.get("EventBusName", "default"),
                "keys": {k: v for k, v in detail.items() if k in ("orderId", "customerId", "total", "reason", "trackingNo", "sku")}}
    if service == "sns" and op == "Publish":
        return {"topic": (params.get("TopicArn") or "").split(":")[-1],
                "attributes": {k: v.get("StringValue") for k, v in (params.get("MessageAttributes") or {}).items()}}
    if service == "sqs" and op in ("SendMessage", "DeleteMessage", "ReceiveMessage"):
        return {"queue": (params.get("QueueUrl") or "").rsplit("/", 1)[-1]}
    return None


def _count(parsed):
    for k in ("Items", "Messages", "Entries", "Contents"):
        if isinstance(parsed.get(k), list):
            return len(parsed[k])
    if isinstance(parsed.get("Responses"), dict):
        return sum(len(v) for v in parsed["Responses"].values())
    if "Item" in parsed:
        return 1 if parsed["Item"] else 0
    return None


READ_OPS = {"GetItem", "BatchGetItem", "Query", "Scan", "TransactGetItems"}


def _capacity(parsed, op=""):
    cc = parsed.get("ConsumedCapacity")
    if not cc:
        return None, None
    rows = cc if isinstance(cc, list) else [cc]
    rcu = sum(r.get("ReadCapacityUnits", 0) or 0 for r in rows)
    wcu = sum(r.get("WriteCapacityUnits", 0) or 0 for r in rows)
    total = sum(r.get("CapacityUnits", 0) or 0 for r in rows)
    if not rcu and not wcu and total:
        if op in READ_OPS:
            rcu = total
        else:
            wcu = total
    parts, usd = [], 0.0
    if rcu:
        parts.append(f"{rcu:g} RRU")
        usd += rcu * RRU_USD
    if wcu:
        parts.append(f"{wcu:g} WRU")
        usd += wcu * WRU_USD
    return " + ".join(parts) or None, (f"≈ ${usd:.10f}".rstrip("0") if usd else None)


def _add(entry):
    _ctx["seq"] += 1
    now = datetime.now(timezone.utc)
    entry.setdefault("ts", now.isoformat(timespec="milliseconds"))
    entry.update(id=uuid.uuid4().hex[:10], cid=_ctx["cid"], vid=_ctx["vid"], fn=FN,
                 sk=f"{entry['ts']}#{FN}#{_ctx['seq']:03d}")
    if _ctx["sc"] and "sc" not in entry:
        entry["sc"], entry["st"] = _ctx["sc"], _ctx["st"]
    _ctx["entries"].append(entry)
    return entry


# ------------------------------------------------------------------ botocore hooks
def _before(model=None, params=None, context=None, **kw):
    if context is not None:
        context["voltaj_t0"] = time.perf_counter()


def _inject_capacity(params=None, model=None, **kw):
    if model is not None and model.name in DDB_CAPACITY_OPS and "ReturnConsumedCapacity" not in params:
        params["ReturnConsumedCapacity"] = "TOTAL"


def _after(http_response=None, parsed=None, model=None, context=None, event_name=None, **kw):
    if context is None or "voltaj_t0" not in context or _ctx["cid"] is None:
        return
    service = model.service_model.service_name if model else "aws"
    params = context.get("voltaj_params") or {}
    if service == "dynamodb" and params.get("TableName") == TABLE:
        return
    sid, label = SERVICES.get(service, (service, service))
    status = (http_response.status_code if http_response is not None else 0)
    err = (parsed or {}).get("Error") or {}
    capacity, cost = _capacity(parsed or {}, model.name if model else "")
    _add({"svc": sid, "engine": label, "op": model.name, "request": _render(service, model.name, params),
          "ms": round((time.perf_counter() - context["voltaj_t0"]) * 1000, 1), "items": _count(parsed or {}),
          "capacity": capacity, "cost": cost, "path": _path(service), "auth": "IAM role (SigV4)",
          "event": _event_fields(service, model.name, params), "ok": status < 400,
          "error": f"{err.get('Code')}: {err.get('Message')}" if err else None})


def _keep_params(params=None, context=None, **kw):
    if context is not None:
        context["voltaj_params"] = dict(params or {})


_session = boto3.Session()
_session.events.register("provide-client-params.dynamodb.*", _inject_capacity)
_session.events.register("provide-client-params.*.*", _keep_params)
_session.events.register("before-call.*.*", _before)
_session.events.register("after-call.*.*", _after)


def client(name, **kw):
    """A boto3 client whose calls become trace entries."""
    return _session.client(name, **kw)


def resource(name, **kw):
    return _session.resource(name, **kw)


# ------------------------------------------------------------------ manual entries
class Entry:
    def __init__(self, data):
        self.data = data

    def result(self, **fields):
        """Add measured facts: items, note, explain, data, capacity, cost, event, ..."""
        self.data.update({k: v for k, v in fields.items() if v is not None})


@contextmanager
def call(svc, op, request, params=None, path=None, auth=None, **extra):
    """Wrap a non-AWS-SDK call (SQL, AMQP, Kafka, HTTPS, OpenSearch) as one entry."""
    data = {"svc": svc, "engine": LABELS.get(svc, svc), "op": op, "request": _short(request, 900),
            "params": params or {}, "path": path, "auth": auth, "ok": True, **extra}
    t0 = time.perf_counter()
    try:
        yield Entry(data)
    except Exception as e:  # noqa: BLE001 - recorded, then raised again
        data.update(ok=False, error=_short(f"{type(e).__name__}: {e}", 500))
        raise
    finally:
        data["ms"] = round((time.perf_counter() - t0) * 1000, 1)
        _add(data)


def note(svc, op, text, **extra):
    """An entry without a call: the trigger of a function, a decision, a guard result."""
    return _add({"svc": svc, "engine": LABELS.get(svc, svc), "op": op, "request": extra.pop("request", ""), "note": text,
                 "ms": extra.pop("ms", 0), "ok": extra.pop("ok", True), **extra})


def _clean(v):
    if isinstance(v, float):
        return Decimal(str(v))
    if isinstance(v, dict):
        return {k: _clean(x) for k, x in v.items() if x is not None and x != {} and x != ""}
    if isinstance(v, list):
        return [_clean(x) for x in v]
    return v


def flush():
    """Write the collected entries to the trace table and return them (for the API response)."""
    entries = _ctx["entries"]
    _ctx["entries"] = []
    if not entries:
        return []
    from boto3.dynamodb.types import TypeSerializer
    ser = TypeSerializer()
    exp = int(time.time()) + TTL_S
    reqs = []
    for e in entries:
        item = _clean({**e, "expiresAt": exp})
        if len(json.dumps(item, default=str)) > 300_000:
            item.pop("data", None)
        reqs.append({"PutRequest": {"Item": {k: ser.serialize(v) for k, v in item.items()}}})
    for i in range(0, len(reqs), 25):
        batch = {TABLE: reqs[i:i + 25]}
        for _ in range(4):
            try:
                out = _writer.batch_write_item(RequestItems=batch)
            except Exception as e:  # noqa: BLE001 - the trace must never break the shop
                print(f"trace flush failed: {e}")
                break
            batch = out.get("UnprocessedItems") or {}
            if not batch:
                break
            time.sleep(0.05)
    return [{k: v for k, v in e.items() if v is not None} for e in entries]
