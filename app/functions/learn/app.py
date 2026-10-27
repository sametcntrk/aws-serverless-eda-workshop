"""Learning layer API: trace lookup, 101 lesson data (big picture → selected record), report screens, experiments, capped bursts."""
import gzip
import json
import os
import time
import uuid
from datetime import datetime, timedelta, timezone

import boto3
from boto3.dynamodb.types import TypeDeserializer

from voltaj import aoss, guard, trace
from voltaj.api import HttpError, dumps, handler as api_handler

E = os.environ
TRACE, GUARD, IDEM = E["TRACE_TABLE"], E["GUARD_TABLE"], E["IDEMPOTENCY_TABLE"]
CATALOG, STOCK, CART, COUNTERS, CONN = E["CATALOG_TABLE"], E["STOCK_TABLE"], E["CART_TABLE"], E["COUNTERS_TABLE"], E["WS_TABLE"]
BUS, LOG_GROUP, SFN_ARN = E["BUS_NAME"], E["EVENT_LOG_GROUP"], E["STATE_MACHINE_ARN"]
LAKE, WEB, POOL = E["LAKE_BUCKET"], E["WEB_BUCKET"], E["USER_POOL_ID"]
DLQS = json.loads(E.get("DLQS", "{}"))           # {name: url}
QUEUES = json.loads(E.get("QUEUES", "{}"))       # {name: url}
ARCHIVE_ARN = E.get("ARCHIVE_ARN", "")
MSK_CLUSTER = E.get("MSK_CLUSTER_NAME", "voltaj-msk")
PERSONAS = json.loads(E.get("PERSONAS", "[]"))   # [{username, password}]
ddb, sfn, logs, s3, sqs, events = (trace.client(n) for n in ("dynamodb", "stepfunctions", "logs", "s3", "sqs", "events"))
cw, idp, lam, schemas = trace.client("cloudwatch"), trace.client("cognito-idp"), trace.client("lambda"), trace.client("schemas")
raw_ddb = boto3.client("dynamodb")
_d = TypeDeserializer()


def plain(item):
    return {k: _d.deserialize(v) for k, v in item.items()}


def jsonable(v):
    return json.loads(dumps(v))


# ------------------------------------------------------------------ trace
def get_trace(req):
    cid = req.query.get("cid")
    if not cid:
        raise HttpError(400, "Send cid.")
    out = raw_ddb.query(TableName=TRACE, KeyConditionExpression="cid = :c", ExpressionAttributeValues={":c": {"S": cid}})
    return [jsonable(plain(i)) for i in out["Items"]]


def recent_trace(req):
    out = raw_ddb.query(TableName=TRACE, IndexName="by-visitor", KeyConditionExpression="vid = :v", ScanIndexForward=False, Limit=200,
                        ExpressionAttributeValues={":v": {"S": req.vid}})
    return [jsonable(plain(i)) for i in reversed(out["Items"])]


# ------------------------------------------------------------------ big picture sources
def _recent_events(minutes=60, limit=200):
    start = int((time.time() - minutes * 60) * 1000)
    out = logs.filter_log_events(logGroupName=LOG_GROUP, startTime=start, limit=limit)
    rows = []
    for ev in out.get("events", []):
        try:
            rows.append(json.loads(ev["message"]))
        except ValueError:
            pass
    return rows


def _rules():
    out = events.list_rules(EventBusName=BUS)
    return [{"name": r["Name"], "pattern": json.loads(r.get("EventPattern") or "{}")} for r in out["Rules"] if r.get("EventPattern")]


def _matches(pattern, evt):
    def m(p, v):
        if isinstance(p, dict):
            return isinstance(v, dict) and all(m(pp, v.get(k)) for k, pp in p.items())
        if isinstance(p, list):
            return any((x == v) or (isinstance(x, dict) and "prefix" in x and str(v).startswith(x["prefix"])) for x in p)
        return p == v
    return m(pattern, evt)


def ov_events(focus):
    rows = _recent_events()
    groups = {}
    for e in rows:
        d = e.get("detail") or {}
        hit = bool(focus & {e.get("id"), d.get("orderId"), d.get("cid")})
        groups.setdefault(e.get("detail-type", "?"), []).append({"id": e["id"], "title": d.get("orderId") or e["id"][:8], "hit": hit})
    types = sorted(groups)
    return {"title": f"{BUS} bus'ındaki event'ler (son bir saat)", "text": "Her kutu bus'a gelen bir event. "
            "commerce-event-log kuralı her event'i CloudWatch Logs'a kopyalar; bu sayfa onları oradan okur.",
            "facts": [[len(rows), "event"], [len(types), "detail-type"], [len(_rules()), "kural"]],
            "groups": [{"label": t, "items": groups[t][:60]} for t in types], "hit_label": "senin çağrın"}


def it_events(item_id):
    for e in _recent_events():
        if e.get("id") == item_id:
            matched = [r["name"] for r in _rules() if _matches(r["pattern"], e)]
            return {"title": e.get("detail-type"), "sub": f"source {e.get('source')} · {e.get('time')}", "record": e,
                    "marks": {"detail-type": "kural bunu eşleştirir", "source": "kural bunu eşleştirir"}, "extra": {"matchedRules": matched}}
    raise HttpError(404, "Bu event artık son bir saatin içinde değil.")


def _execution(focus):
    for f in focus:
        if f.startswith("o-"):
            return f"{SFN_ARN.replace(':stateMachine:', ':execution:')}:{f}"
    ex = sfn.list_executions(stateMachineArn=SFN_ARN, maxResults=1)["executions"]
    return ex[0]["executionArn"] if ex else None


def ov_saga(focus):
    arn = _execution(focus)
    if not arn:
        return {"title": "Checkout execution'ları", "text": "Henüz execution yok. Önce mağazada bir checkout yap.", "groups": [], "facts": []}
    hist = sfn.get_execution_history(executionArn=arn, maxResults=200)["events"]
    states, failed = [], []
    for h in hist:
        if h["type"].endswith("StateEntered"):
            states.append({"id": f"{h['id']}", "title": h["stateEnteredEventDetails"]["name"], "hit": True})
        if h["type"].endswith("Failed") or h["type"].endswith("TimedOut"):
            failed.append({"id": f"{h['id']}", "title": h["type"], "hit": False})
    desc = sfn.describe_execution(executionArn=arn)
    return {"title": f"Execution {arn.rsplit(':', 1)[-1]}", "text": "Her kutu execution'ın sırayla girdiği bir state.",
            "facts": [[desc["status"], "durum"], [len(states), "state"], [len(hist), "history event"]],
            "groups": [{"label": "Girilen state'ler", "items": states}] + ([{"label": "Hatalar ve timeout'lar", "items": failed}] if failed else []),
            "hit_label": "bu execution", "ref": arn}


def it_saga(item_id, focus):
    arn = _execution(focus)
    hist = sfn.get_execution_history(executionArn=arn, maxResults=200)["events"]
    by = {str(h["id"]): h for h in hist}
    h = by.get(item_id)
    if not h:
        raise HttpError(404, "No such history event.")
    det = h.get("stateEnteredEventDetails") or {}
    nxt = next((x for x in hist if x["id"] > h["id"] and x["type"].endswith("StateExited")), {})
    rec = {"state": det.get("name"), "input": json.loads(det.get("input") or "null"),
           "output": json.loads((nxt.get("stateExitedEventDetails") or {}).get("output") or "null"), "enteredAt": h["timestamp"].isoformat()}
    if not det:
        rec = jsonable({k: v for k, v in h.items() if k not in ("timestamp",)})
    return {"title": det.get("name") or h["type"], "sub": h["timestamp"].isoformat(), "record": rec, "marks": {"input": "in", "output": "out"}}


def ov_idempotency(focus):
    out = raw_ddb.scan(TableName=IDEM, Limit=400)
    groups = {}
    labels = {"PAY": "Task token'lar (ödeme)", "EVT": "Webhook event'leri", "FUL": "Fulfillment (3PL)", "MAIL": "E-posta", "SMS": "SMS"}
    for i in out["Items"]:
        pk = i["pk"]["S"]
        kind = pk.split("#", 1)[0]
        groups.setdefault(labels.get(kind, kind), []).append({"id": pk, "title": pk.split("#", 1)[1][:14],
                                                               "hit": any(f and f in pk for f in focus)})
    return {"title": "Idempotency anahtarları (voltaj-idempotency tablosu)", "text": "Her tüketici event başına bir anahtarı "
            "attribute_not_exists(pk) koşuluyla yazar. Aynı event ikinci kez gelirse koşul tutmaz ve tüketici durur.",
            "facts": [[len(out["Items"]), "anahtar"]], "groups": [{"label": k, "items": v[:80]} for k, v in sorted(groups.items())],
            "hit_label": "senin siparişin"}


def ov_table(table, label, group_attr=None, focus=frozenset(), limit=300, title_attr="pk"):
    out = raw_ddb.scan(TableName=table, Limit=limit)
    groups = {}
    for i in out["Items"]:
        p = plain(i)
        g = str(p.get(group_attr, "items")) if group_attr else "items"
        key = p.get("pk") + ("|" + p["sk"] if "sk" in p else "")
        groups.setdefault(g, []).append({"id": key, "title": str(p.get(title_attr) or key)[:16],
                                         "hit": any(f and f in key for f in focus)})
    return {"title": f"Table {table}", "text": label, "facts": [[len(out["Items"]), "item (örnek)"]],
            "groups": [{"label": k, "items": v[:60]} for k, v in sorted(groups.items())], "hit_label": "senin çağrın"}


def it_table(table, item_id):
    pk, _, sk = item_id.partition("|")
    key = {"pk": {"S": pk}} | ({"sk": {"S": sk}} if sk else {})
    got = raw_ddb.get_item(TableName=table, Key=key)
    if "Item" not in got:
        raise HttpError(404, "Bu item yok (TTL silmiş olabilir).")
    return {"title": pk, "sub": f"table {table}", "record": jsonable(plain(got["Item"])), "typed": jsonable(got["Item"]), "marks": {}}


def ov_search(focus):
    out = aoss.request("POST", "/products/_search", {"size": 120, "_source": ["sku", "name", "category"], "query": {"match_all": {}}})
    groups = {}
    for h in out["hits"]["hits"]:
        s = h["_source"]
        groups.setdefault(s.get("category", "?"), []).append({"id": h["_id"], "title": s.get("name", "")[:18],
                                                              "hit": h["_id"] in focus or s.get("sku") in focus})
    return {"title": "voltaj-search koleksiyonundaki products index'i", "text": "Her kutu bir doküman. Zero-ETL pipeline'ı onu "
            "DynamoDB'deki voltaj-catalog tablosundan kopyaladı.", "facts": [[out["hits"]["total"]["value"], "doküman"], [len(groups), "kategori"]],
            "groups": [{"label": k, "items": v} for k, v in sorted(groups.items())], "hit_label": "senin sonucunda"}


def it_search(item_id):
    doc = aoss.request("POST", "/products/_search", {"size": 1, "query": {"ids": {"values": [item_id]}}})["hits"]["hits"]
    if not doc:
        raise HttpError(404, "No such document.")
    got = raw_ddb.get_item(TableName=CATALOG, Key={"pk": {"S": item_id}})
    return {"title": doc[0]["_source"].get("name"), "sub": f"_id {item_id}", "record": doc[0]["_source"],
            "source": jsonable(got.get("Item") or {}), "marks": {"name": "analyzer'dan geçen metin", "category": "keyword + text"}}


def ov_lake(focus):
    out = s3.list_objects_v2(Bucket=LAKE, MaxKeys=300)
    groups = {}
    for o in out.get("Contents", []):
        k = o["Key"]
        topic, dt = k.split("/")[0], "/".join(k.split("/")[1:3])
        groups.setdefault(f"{topic} · {dt}", []).append({"id": k, "title": k.rsplit("/", 1)[-1][5:13], "hit": False})
    return {"title": f"Data lake bucket'ı {LAKE}", "text": "archive tüketicisi her batch için bir gzip JSON-lines dosyası yazar; "
            "dosyalar topic, tarih ve saate göre bölümlenir.", "facts": [[out.get("KeyCount", 0), "dosya"]],
            "groups": [{"label": k, "items": v[-40:]} for k, v in sorted(groups.items())][-8:], "hit_label": "-"}


def it_lake(item_id):
    body = s3.get_object(Bucket=LAKE, Key=item_id)["Body"].read()
    lines = gzip.decompress(body).decode().splitlines()
    return {"title": item_id.rsplit("/", 1)[-1], "sub": f"{len(lines)} kayıt", "record": {"records": [json.loads(x) for x in lines[:20]]},
            "marks": {}}


def ov_dlq(focus):
    groups = []
    facts = []
    for name, url in DLQS.items():
        attrs = sqs.get_queue_attributes(QueueUrl=url, AttributeNames=["ApproximateNumberOfMessages"])["Attributes"]
        n = int(attrs["ApproximateNumberOfMessages"])
        facts.append([n, name])
        msgs = sqs.receive_message(QueueUrl=url, MaxNumberOfMessages=10, VisibilityTimeout=0, MessageSystemAttributeNames=["All"],
                                   MessageAttributeNames=["All"]).get("Messages", []) if n else []
        groups.append({"label": name, "items": [{"id": f"{name}|{m['MessageId']}", "title": m["MessageId"][:8], "hit": False,
                                                 "record": m} for m in msgs]})
    return {"title": "Dead-letter queue'lar", "text": "Tüketici maxReceiveCount kez başarısız olunca mesaj buraya taşınır.",
            "facts": facts, "groups": groups, "hit_label": "-"}


def ov_users(focus):
    out = idp.list_users(UserPoolId=POOL, Limit=60)
    admins = {u["Username"] for u in idp.list_users_in_group(UserPoolId=POOL, GroupName="admins")["Users"]}
    groups = {"admins": [], "customers": []}
    for u in out["Users"]:
        a = {x["Name"]: x["Value"] for x in u.get("Attributes", [])}
        groups["admins" if u["Username"] in admins else "customers"].append(
            {"id": u["Username"], "title": a.get("name", u["Username"])[:16], "hit": a.get("sub") in focus})
    return {"title": f"User pool {POOL}", "text": "Personalar gerçek Cognito kullanıcıları. admins grubu admin API'lerini açar.",
            "facts": [[len(out["Users"]), "kullanıcı"], [len(admins), "admin"]], "groups": [{"label": k, "items": v} for k, v in groups.items()],
            "hit_label": "sen"}


def it_users(item_id):
    u = idp.admin_get_user(UserPoolId=POOL, Username=item_id)
    rec = {"Username": u["Username"], "UserStatus": u["UserStatus"], "Enabled": u["Enabled"],
           "UserAttributes": {a["Name"]: a["Value"] for a in u["UserAttributes"]}, "PreferredMfaSetting": u.get("PreferredMfaSetting"),
           "UserCreateDate": u["UserCreateDate"].isoformat()}
    return {"title": rec["UserAttributes"].get("name", item_id), "sub": item_id, "record": rec, "marks": {}}


def ov_images(focus):
    out = s3.list_objects_v2(Bucket=WEB, Prefix="images/", MaxKeys=400)
    groups = {}
    for o in out.get("Contents", []):
        parts = o["Key"].split("/")
        if len(parts) == 3:
            groups.setdefault(parts[1], []).append({"id": o["Key"], "title": parts[2], "hit": parts[1] in focus})
    items = [{"id": k + "/md.webp", "title": k, "hit": k in focus} for k in sorted(groups)]
    return {"title": f"Web bucket'ındaki görseller ({WEB})", "text": "Her ürünün images/<sku>/ altında sm, md ve lg WebP dosyaları var.",
            "facts": [[len(items), "görselli ürün"]], "groups": [{"label": "images/", "items": items[:150]}], "hit_label": "seninki"}


def it_images(item_id):
    h = s3.head_object(Bucket=WEB, Key=item_id)
    return {"title": item_id, "sub": h["ContentType"], "record": {"Key": item_id, "ContentLength": h["ContentLength"],
            "ContentType": h["ContentType"], "CacheControl": h.get("CacheControl"), "LastModified": h["LastModified"].isoformat(),
            "ETag": h["ETag"]}, "image": "/" + item_id, "marks": {}}


def ov_aurora(focus):
    r = json.loads(lam.invoke(FunctionName=E["ORDER_FN"], Payload=json.dumps({"action": "report"}).encode())["Payload"].read())
    groups = {}
    for o in r.get("orders", []):
        groups.setdefault(o["status"], []).append({"id": o["order_id"], "title": o["order_id"][:12], "hit": o["order_id"] in focus,
                                                   "record": o})
    return {"title": "orders ve order_lines tabloları (Aurora PostgreSQL)", "text": "Her kutu orders tablosunun bir satırı. "
            "Birini seç: satırı order_lines ile birlikte görürsün.", "facts": [[r.get("count", 0), "sipariş"], [r.get("lines", 0), "sipariş satırı"]],
            "groups": [{"label": k, "items": v[:80]} for k, v in sorted(groups.items())], "hit_label": "senin siparişin"}


def ov_mq(focus):
    r = json.loads(lam.invoke(FunctionName=E["FULFILLMENT_FN"], Payload=json.dumps({"action": "queues"}).encode())["Payload"].read())
    items = [{"id": q["name"], "title": q["name"], "hit": True, "record": q} for q in r.get("queues", [])]
    return {"title": "RabbitMQ kuyrukları (Amazon MQ cluster)", "text": "Quorum kuyruklar her mesajın bir kopyasını 3 node'da tutar.",
            "facts": [[len(items), "kuyruk"]], "groups": [{"label": "vhost /", "items": items}], "hit_label": "-"}


OVERVIEW = {
    "fanout": ov_events, "eb": ov_events, "replay": ov_events, "schema-registry": ov_events, "pipes": ov_events,
    "messaging-compare": ov_events, "saga": ov_saga, "task-token": ov_saga, "sfn": ov_saga, "idempotency": ov_idempotency,
    "notifications": ov_idempotency, "dlq": ov_dlq, "sqs": ov_dlq, "sns": ov_idempotency, "ses": ov_idempotency,
    "zero-etl": ov_search, "aoss": ov_search, "clickstream": ov_lake, "msk": ov_lake, "s3": ov_images, "upload-resize": ov_images,
    "cognito": ov_users, "edge": ov_images, "aurora": ov_aurora, "mq": ov_mq,
    "ddb-conditional": lambda f: ov_table(STOCK, "Ürün başına stok. Checkout stoğu bir koşulla ayırır.", focus=f, title_attr="pk"),
    "ddb": lambda f: ov_table(CATALOG, "Katalog: ürün başına bir item, kategoriye göre gruplu.", "category", f, title_attr="name"),
    "websocket": lambda f: ov_table(CONN, "Açık WebSocket bağlantısı başına bir item (TTL 2 saat).", focus=f, title_attr="sk"),
    "lambda": ov_events, "apigw": ov_events, "cf": ov_images,
}
ITEM_TABLE = {"ddb-conditional": STOCK, "ddb": CATALOG, "websocket": CONN, "idempotency": IDEM, "notifications": IDEM, "sns": IDEM,
              "ses": IDEM}


def overview(req):
    lesson = req.query.get("lesson", "")
    focus = frozenset(x for x in (req.query.get("focus") or "").split(",") if x)
    fn = OVERVIEW.get(lesson)
    if not fn:
        raise HttpError(404, f"No big picture for lesson {lesson}.")
    return fn(focus)


def item(req):
    lesson, item_id = req.query.get("lesson", ""), req.query.get("id", "")
    focus = frozenset(x for x in (req.query.get("focus") or "").split(",") if x)
    src = OVERVIEW.get(lesson)
    if src in (ov_events,):
        return it_events(item_id)
    if src is ov_saga:
        return it_saga(item_id, focus)
    if src is ov_search:
        return it_search(item_id)
    if src is ov_lake:
        return it_lake(item_id)
    if src is ov_users:
        return it_users(item_id)
    if src is ov_images:
        return it_images(item_id)
    if lesson in ITEM_TABLE:
        return it_table(ITEM_TABLE[lesson], item_id)
    if src in (ov_dlq, ov_aurora, ov_mq):
        for g in src(focus)["groups"]:
            for x in g["items"]:
                if x["id"] == item_id:
                    return {"title": x["title"], "sub": g["label"], "record": jsonable(x.get("record")), "marks": {}}
    raise HttpError(404, "Böyle bir kayıt yok.")


# ------------------------------------------------------------------ reports
def rep_executions(req):
    out = sfn.list_executions(stateMachineArn=SFN_ARN, maxResults=40)["executions"]
    return [{"name": e["name"], "status": e["status"], "start": e["startDate"].isoformat(),
             "stop": e.get("stopDate").isoformat() if e.get("stopDate") else None} for e in out]


def rep_events(req):
    rows = _recent_events(int(req.query.get("minutes") or 60))
    return [{"id": e["id"], "time": e.get("time"), "source": e.get("source"), "detailType": e.get("detail-type"),
             "orderId": (e.get("detail") or {}).get("orderId"), "event": e} for e in reversed(rows)]


def rep_dlq(req):
    res = []
    for name, url in DLQS.items():
        a = sqs.get_queue_attributes(QueueUrl=url, AttributeNames=["ApproximateNumberOfMessages", "QueueArn"])["Attributes"]
        msgs = sqs.receive_message(QueueUrl=url, MaxNumberOfMessages=10, VisibilityTimeout=0, MessageSystemAttributeNames=["All"]
                                   ).get("Messages", []) if int(a["ApproximateNumberOfMessages"]) else []
        res.append({"name": name, "arn": a["QueueArn"], "count": int(a["ApproximateNumberOfMessages"]),
                    "messages": [{"id": m["MessageId"], "receiveCount": m["Attributes"].get("ApproximateReceiveCount"),
                                  "body": m["Body"][:4000]} for m in msgs]})
    return res


def rep_lag(req):
    end = datetime.now(timezone.utc)
    q = [{"Id": f"g{i}", "MetricStat": {"Metric": {"Namespace": "AWS/Kafka", "MetricName": "MaxOffsetLag", "Dimensions": [
        {"Name": "Cluster Name", "Value": MSK_CLUSTER}, {"Name": "Consumer Group", "Value": g}, {"Name": "Topic", "Value": "clickstream"}]},
        "Period": 60, "Stat": "Maximum"}, "Label": g} for i, g in enumerate(("archive", "counters"))]
    out = cw.get_metric_data(MetricDataQueries=q, StartTime=end - timedelta(minutes=60), EndTime=end)
    return [{"group": r["Label"], "points": [[t.isoformat(), v] for t, v in zip(r["Timestamps"], r["Values"])]}
            for r in out["MetricDataResults"]]


def rep_lake(req):
    out = s3.list_objects_v2(Bucket=LAKE, MaxKeys=1000)
    rows = sorted(out.get("Contents", []), key=lambda o: o["LastModified"], reverse=True)[:60]
    return [{"key": o["Key"], "size": o["Size"], "at": o["LastModified"].isoformat()} for o in rows]


def rep_counters(req):
    out = raw_ddb.scan(TableName=COUNTERS)
    rows = sorted(((i["pk"]["S"].split("#", 2)[-1], int(i.get("views", {}).get("N", 0))) for i in out["Items"]), key=lambda x: -x[1])
    return [{"sku": s, "views": v} for s, v in rows[:30]]


# ------------------------------------------------------------------ experiments
def exp_duplicate(req):
    cid = req.body.get("cid")
    guard.hit(f"dup#{req.vid}", 10, 3600, "Duplicate-event experiments")
    out = raw_ddb.query(TableName=TRACE, KeyConditionExpression="cid = :c", ExpressionAttributeValues={":c": {"S": cid or "-"}})
    src = next((plain(i) for i in out["Items"] if i.get("op", {}).get("S") == "PutEvents" and "detail" in (plain(i).get("data") or {})
                and (plain(i).get("event") or {}).get("detailType") == "OrderPlaced"), None)
    if not src:
        raise HttpError(404, "No OrderPlaced event for this checkout. Finish a checkout first.")
    trace.step("p3s5", "1a")
    detail = json.loads(src["data"]["detail"])
    detail["cid"], detail["vid"] = trace.cid(), req.vid
    events.put_events(Entries=[{"EventBusName": BUS, "Source": "com.shop.checkout", "DetailType": "OrderPlaced", "Detail": json.dumps(detail)}])
    trace.note("eb", "Same event again", f"The bus got OrderPlaced for {detail['orderId']} a second time, with the same eventId "
               f"{detail.get('eventId')}. Watch the consumers: each one finds its idempotency key and stops.")
    return {"orderId": detail["orderId"], "eventId": detail.get("eventId")}


def exp_break(req):
    on = bool(req.body.get("on"))
    if on:
        raw_ddb.put_item(TableName=GUARD, Item={"pk": {"S": "FLAG#break-email"}, "expiresAt": {"N": str(int(time.time()) + 600)}})
    else:
        raw_ddb.delete_item(TableName=GUARD, Key={"pk": {"S": "FLAG#break-email"}})
    trace.note("lambda", "Experiment", "The email consumer is broken for 10 minutes. New emails fail and go to the DLQ after 3 receives."
               if on else "The email consumer works again. Use Redrive to send the DLQ messages back.")
    return {"broken": on}


def exp_redrive(req):
    name = req.body.get("queue") or "email-dlq"
    if name not in DLQS:
        raise HttpError(400, "Unknown DLQ.")
    guard.hit(f"redrive#{req.vid}", 10, 3600, "Redrives")
    arn = sqs.get_queue_attributes(QueueUrl=DLQS[name], AttributeNames=["QueueArn"])["Attributes"]["QueueArn"]
    out = sqs.start_message_move_task(SourceArn=arn, MaxNumberOfMessagesPerSecond=10)
    trace.note("sqs", "Redrive", "SQS moves the messages from the DLQ back to the source queue. The consumer gets them again.")
    return {"taskHandle": out["TaskHandle"]}


def exp_replay(req):
    guard.hit("replay", 2, 3600, "Archive replays")
    minutes = min(int(req.body.get("minutes") or 10), 30)
    end = datetime.now(timezone.utc) - timedelta(seconds=30)
    name = f"voltaj-replay-{int(time.time())}"
    events.start_replay(ReplayName=name, EventSourceArn=ARCHIVE_ARN, EventStartTime=end - timedelta(minutes=minutes), EventEndTime=end,
                        Destination={"Arn": events.describe_event_bus(Name=BUS)["Arn"],
                                     "FilterArns": [r for r in E.get("REPLAY_RULE_ARNS", "").split(",") if r]})
    trace.note("eb", "Replay", f"EventBridge sends the archived events of the last {minutes} minutes again, only to the rule "
               "commerce-event-log (so no email or 3PL message repeats).")
    return {"replay": name}


def exp_burst(req):
    kind = req.body.get("kind", "orders")
    guard.hit("burst", 5, 3600, "Event bursts")
    if kind == "clicks":
        n = min(int(req.body.get("n") or 500), 1000)
        r = json.loads(lam.invoke(FunctionName=E["PRODUCER_FN"], Payload=json.dumps({"action": "burst", "n": n, "cid": trace.cid(),
                                                                                     "vid": req.vid}).encode())["Payload"].read())
        trace.note("msk", "Burst", f"{n} clickstream events went to the topic clickstream. Watch the consumer lag report.")
        return r
    n = min(int(req.body.get("n") or 50), 200)
    sent = 0
    for i in range(0, n, 10):
        entries = []
        for _ in range(min(10, n - i)):
            oid = f"o-burst-{uuid.uuid4().hex[:8]}"
            entries.append({"EventBusName": BUS, "Source": "com.shop.burst", "DetailType": "OrderPlaced", "Detail": json.dumps(
                {"orderId": oid, "eventId": f"{oid}-placed", "customerId": "burst", "total": 99.0, "smsOptIn": False, "burst": True,
                 "lines": [{"sku": "VLT-1001", "name": "Burst item", "qty": 1, "price": 99.0}], "cid": trace.cid(), "vid": "burst"})})
        events.put_events(Entries=entries)
        sent += len(entries)
    trace.note("eb", "Burst", f"{sent} OrderPlaced events went to the bus. The fan-out multiplies them: SNS, the order buffer and "
               "the commerce log each get every event. Watch the queue depth.")
    return {"sent": sent}


def queue_depth(req):
    out = []
    for name, url in {**QUEUES, **DLQS}.items():
        a = sqs.get_queue_attributes(QueueUrl=url, AttributeNames=["ApproximateNumberOfMessages", "ApproximateNumberOfMessagesNotVisible"])
        out.append({"name": name, "visible": int(a["Attributes"]["ApproximateNumberOfMessages"]),
                    "inFlight": int(a["Attributes"]["ApproximateNumberOfMessagesNotVisible"])})
    return out


def schema(req):
    try:
        out = schemas.list_schemas(RegistryName="discovered-schemas", Limit=20).get("Schemas", [])
    except schemas.exceptions.NotFoundException:
        trace.note("eb", "No registry yet", "Schema discovery creates the registry discovered-schemas after it sees the first events. "
                   "This can take some minutes.")
        return []
    res = []
    for s in out:
        if "voltaj" in s["SchemaName"] or "com.shop" in s["SchemaName"]:
            d = schemas.describe_schema(RegistryName="discovered-schemas", SchemaName=s["SchemaName"])
            res.append({"name": s["SchemaName"], "version": d.get("SchemaVersion"), "content": json.loads(d["Content"])})
    return res


# ------------------------------------------------------------------ scheduled: keep the persona accounts usable
def persona_guard():
    for p in PERSONAS:
        try:
            boto3.client("cognito-idp").admin_set_user_password(UserPoolId=POOL, Username=p["username"], Password=p["password"], Permanent=True)
            boto3.client("cognito-idp").admin_enable_user(UserPoolId=POOL, Username=p["username"])
        except Exception as e:  # noqa: BLE001
            print(f"persona {p['username']}: {e}")
    return {"ok": True}


_api = api_handler("learn", {
    ("GET", "/learn/trace"): get_trace, ("GET", "/learn/recent"): recent_trace, ("GET", "/learn/overview"): overview,
    ("GET", "/learn/item"): item, ("GET", "/learn/reports/executions"): rep_executions, ("GET", "/learn/reports/events"): rep_events,
    ("GET", "/learn/reports/dlq"): rep_dlq, ("GET", "/learn/reports/lag"): rep_lag, ("GET", "/learn/reports/lake"): rep_lake,
    ("GET", "/learn/reports/counters"): rep_counters, ("GET", "/learn/reports/queues"): queue_depth, ("GET", "/learn/reports/schemas"): schema,
    ("POST", "/learn/experiments/duplicate"): exp_duplicate, ("POST", "/learn/experiments/break-email"): exp_break,
    ("POST", "/learn/experiments/redrive"): exp_redrive, ("POST", "/learn/experiments/replay"): exp_replay,
    ("POST", "/learn/experiments/burst"): exp_burst,
})


def lambda_handler(event, context):
    if event.get("action") == "persona-guard":
        return persona_guard()
    return _api(event, context)
