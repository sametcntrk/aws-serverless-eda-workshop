"""Product service: search (OpenSearch Serverless), product detail and price/stock (DynamoDB), admin writes and image upload URLs."""
import os
import time

from voltaj import aoss, guard, trace
from voltaj.api import HttpError, handler

CATALOG, STOCK, COUNTERS = os.environ["CATALOG_TABLE"], os.environ["STOCK_TABLE"], os.environ["COUNTERS_TABLE"]
UPLOADS = os.environ["UPLOADS_BUCKET"]
DEMO_ADMIN = os.environ.get("DEMO_ADMIN_EMAIL", "demo-admin@voltaj.shop")
ddb = trace.client("dynamodb")
s3 = trace.client("s3", config=__import__("botocore.config").config.Config(signature_version="s3v4", s3={"addressing_style": "virtual"}))
FIELDS = ["sku", "name", "brand", "category", "price", "currency", "rating", "image", "tags", "short"]


def _plain(item):
    from boto3.dynamodb.types import TypeDeserializer
    d = TypeDeserializer()
    return {k: d.deserialize(v) for k, v in item.items()}


def _prices(skus):
    """One BatchGetItem over two tables: the current price (catalog) and the available stock (stock)."""
    if not skus:
        return {}
    keys = [{"pk": {"S": f"SKU#{s}"}} for s in skus]
    out = ddb.batch_get_item(RequestItems={
        CATALOG: {"Keys": keys, "ProjectionExpression": "pk, price"},
        STOCK: {"Keys": keys, "ProjectionExpression": "pk, available"}})
    res = {}
    for item in out["Responses"].get(CATALOG, []):
        res.setdefault(item["pk"]["S"][4:], {})["price"] = float(item["price"]["N"])
    for item in out["Responses"].get(STOCK, []):
        res.setdefault(item["pk"]["S"][4:], {})["available"] = int(item["available"]["N"])
    return res


def search(req):
    q = (req.query.get("q") or "").strip()
    cat = req.query.get("category")
    fuzzy = req.query.get("fuzzy", "1") != "0"
    size = min(int(req.query.get("size") or 24), 48)
    trace.step("p2s3", "4")
    must = []
    if q:
        mm = {"query": q, "fields": ["name^3", "brand^2", "category", "short", "tags"]}
        if fuzzy:
            mm["fuzziness"] = "AUTO"
        must.append({"multi_match": mm})
    body = {"size": size, "_source": FIELDS,
            "query": {"bool": {"must": must or [{"match_all": {}}], "filter": [{"term": {"category.keyword": cat}}] if cat else []}}}
    if not q:
        body["sort"] = [{"rank": "asc"}]
    out = aoss.request("POST", "/products/_search", body, op="Search")
    hits = [dict(h["_source"], score=h.get("_score")) for h in out["hits"]["hits"]]
    trace.step("p2s3", "5")
    live = _prices([h["sku"] for h in hits])
    for h in hits:
        h.update(live.get(h["sku"], {}))
    return {"q": q, "fuzzy": fuzzy, "total": out["hits"]["total"]["value"], "items": hits}


def suggest(req):
    q = (req.query.get("q") or "").strip()
    trace.step("p2s3", "4")
    out = aoss.request("POST", "/products/_search", {"size": 6, "_source": ["sku", "name", "category"],
                       "query": {"match_phrase_prefix": {"name": {"query": q}}}}, op="Search (suggest)")
    return [h["_source"] for h in out["hits"]["hits"]]


def detail(req):
    sku = req.params["sku"]
    trace.step("p2s3", "5")
    out = ddb.get_item(TableName=CATALOG, Key={"pk": {"S": f"SKU#{sku}"}})
    if "Item" not in out:
        raise HttpError(404, f"Product {sku} does not exist.")
    p = _plain(out["Item"])
    p.update(_prices([sku]).get(sku, {}))
    return p


def popular(req):
    trace.step("p5s8", "2")
    out = ddb.scan(TableName=COUNTERS, ProjectionExpression="pk, #v", ExpressionAttributeNames={"#v": "views"})
    top = sorted(((i["pk"]["S"].split("#", 2)[-1], int(i.get("views", {}).get("N", 0))) for i in out["Items"]), key=lambda x: -x[1])[:8]
    if not top:
        return []
    keys = [{"pk": {"S": f"SKU#{s}"}} for s, _ in top]
    got = ddb.batch_get_item(RequestItems={CATALOG: {"Keys": keys, "ProjectionExpression": "sku, #n, price, image, category",
                                                     "ExpressionAttributeNames": {"#n": "name"}}})
    by = {i["sku"]["S"]: _plain(i) for i in got["Responses"][CATALOG]}
    return [dict(by[s], views=v) for s, v in top if s in by]


def _admin(req, sku=None):
    if not req.is_admin:
        raise HttpError(403, "This API is for the admins group only.")
    if req.claims.get("email") == DEMO_ADMIN and sku is not None and not sku.startswith("demo-"):
        raise HttpError(403, "The demo admin can change only products whose SKU starts with demo-.")


def save_product(req):
    sku = req.params["sku"]
    _admin(req, sku)
    guard.hit(f"admin-save#{req.sub}", 60, 3600, "Product saves")
    b = req.body
    name = str(b.get("name") or "").strip()[:120]
    try:
        price = round(float(b.get("price")), 2)
    except (TypeError, ValueError):
        raise HttpError(400, "Price must be a number.") from None
    if not name or price <= 0:
        raise HttpError(400, "Name and a positive price are necessary.")
    trace.step("p5s1", "4")
    item = {"pk": {"S": f"SKU#{sku}"}, "sku": {"S": sku}, "name": {"S": name}, "price": {"N": str(price)},
            "currency": {"S": "EUR"}, "category": {"S": str(b.get("category") or "Accessories")[:40]},
            "brand": {"S": str(b.get("brand") or "Voltaj Labs")[:40]}, "short": {"S": str(b.get("short") or "")[:300]},
            "rank": {"N": str(int(b.get("rank") or 9000))}, "rating": {"N": str(b.get("rating") or 0)},
            "image": {"S": f"images/{sku}/md.webp"}, "updatedAt": {"N": str(int(time.time()))}}
    ddb.put_item(TableName=CATALOG, Item=item)
    ddb.update_item(TableName=STOCK, Key={"pk": {"S": f"SKU#{sku}"}}, UpdateExpression="SET available = if_not_exists(available, :n)",
                    ExpressionAttributeValues={":n": {"N": str(int(b.get("stock") or 25))}})
    trace.note("osis", "Stream record", "The table stream now has a MODIFY or INSERT record. The OpenSearch Ingestion pipeline reads it "
               "and indexes the document in a few seconds (zero-ETL). Search for the name to see it.", sc="p5s2", st="1")
    return {"sku": sku, "saved": True}


def upload_url(req):
    sku = str(req.body.get("sku") or "")
    _admin(req, sku)
    guard.hit(f"admin-upload#{req.sub}", 20, 3600, "Image uploads")
    ctype = req.body.get("contentType") or "image/jpeg"
    if ctype not in ("image/jpeg", "image/png", "image/webp"):
        raise HttpError(400, "Use a JPEG, PNG or WebP image.")
    trace.step("p5s3", "3")
    key = f"{sku}/orig.{ctype.split('/')[1]}"
    meta = {"cid": trace.cid(), "vid": trace.vid()}
    with trace.call("s3", "Presign PutObject", f"s3.generate_presigned_url('put_object', Bucket='{UPLOADS}', Key='{key}', ExpiresIn=300)",
                    path="Local signature in the Lambda function (no network call)", auth="SigV4 query string (X-Amz-Signature)") as t:
        url = s3.generate_presigned_url("put_object", Params={"Bucket": UPLOADS, "Key": key, "ContentType": ctype, "Metadata": meta},
                                        ExpiresIn=300)
        t.result(note="The URL is valid for 5 minutes. The browser sends the file straight to S3; the Lambda function never sees the bytes.")
    return {"url": url, "key": key, "headers": {"Content-Type": ctype, **{f"x-amz-meta-{k}": v for k, v in meta.items()}}, "maxBytes": 2_000_000}


lambda_handler = handler("product", {
    ("GET", "/products"): search, ("GET", "/products/suggest"): suggest, ("GET", "/products/popular"): popular,
    ("GET", "/products/{sku}"): detail, ("PUT", "/admin/products/{sku}"): save_product,
    ("POST", "/admin/images/upload-url"): upload_url,
})
