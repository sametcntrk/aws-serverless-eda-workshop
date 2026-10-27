"""Cart service: one DynamoDB item per cart line. The cart of a visitor is CART#<persona sub>~<visitor id>, with TTL."""
import os
import time

from voltaj import trace
from voltaj.api import HttpError, handler

CART, CATALOG = os.environ["CART_TABLE"], os.environ["CATALOG_TABLE"]
TTL_DAYS = 7
MAX_QTY = 5
ddb = trace.client("dynamodb")


def _pk(req):
    if not req.sub:
        raise HttpError(401, "Sign in first.")
    return f"CART#{req.sub}~{req.vid}"


def _lines(pk):
    out = ddb.query(TableName=CART, KeyConditionExpression="pk = :pk", ExpressionAttributeValues={":pk": {"S": pk}})
    lines = [{"sku": i["sk"]["S"][4:], "name": i["name"]["S"], "qty": int(i["qty"]["N"]), "price": float(i["price"]["N"]),
              "image": i.get("image", {}).get("S")} for i in out["Items"]]
    return {"lines": lines, "count": sum(x["qty"] for x in lines), "total": round(sum(x["qty"] * x["price"] for x in lines), 2)}


def get_cart(req):
    trace.step("p2s4", "4")
    return _lines(_pk(req))


def add_item(req):
    pk = _pk(req)
    sku = str(req.body.get("sku") or "")
    qty = int(req.body.get("qty") or 1)
    if not sku or not 1 <= qty <= MAX_QTY:
        raise HttpError(400, f"Send a sku and a qty from 1 to {MAX_QTY}.")
    trace.step("p2s4", "4")
    got = ddb.get_item(TableName=CATALOG, Key={"pk": {"S": f"SKU#{sku}"}}, ProjectionExpression="#n, price, image",
                       ExpressionAttributeNames={"#n": "name"})
    if "Item" not in got:
        raise HttpError(404, f"Product {sku} does not exist.")
    p = got["Item"]
    try:
        ddb.update_item(
            TableName=CART, Key={"pk": {"S": pk}, "sk": {"S": f"SKU#{sku}"}},
            UpdateExpression="ADD qty :q SET #n = :n, price = :p, image = :i, expiresAt = :e",
            ConditionExpression="attribute_not_exists(qty) OR qty <= :room",
            ExpressionAttributeNames={"#n": "name"},
            ExpressionAttributeValues={":q": {"N": str(qty)}, ":n": p["name"], ":p": p["price"], ":i": p.get("image", {"S": ""}),
                                       ":e": {"N": str(int(time.time()) + TTL_DAYS * 86400)}, ":room": {"N": str(MAX_QTY - qty)}})
    except ddb.exceptions.ConditionalCheckFailedException:
        raise HttpError(409, f"A cart line can have at most {MAX_QTY} pieces. The condition stopped the write.") from None
    return _lines(pk)


def remove_item(req):
    pk = _pk(req)
    trace.step("p2s4", "4")
    ddb.delete_item(TableName=CART, Key={"pk": {"S": pk}, "sk": {"S": f"SKU#{req.params['sku']}"}})
    return _lines(pk)


lambda_handler = handler("cart", {("GET", "/cart"): get_cart, ("POST", "/cart/items"): add_item,
                                  ("DELETE", "/cart/items/{sku}"): remove_item})
