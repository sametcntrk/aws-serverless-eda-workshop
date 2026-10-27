"""Lambda ws: stores WebSocket connections ($connect, $disconnect) and pushes the checkout result (invoked by the saga)."""
import json
import os
import time

from voltaj import trace

CONN = os.environ["WS_TABLE"]
WS_URL = os.environ["WS_MANAGEMENT_URL"]
ddb = trace.client("dynamodb")
mgmt = trace.client("apigatewaymanagementapi", endpoint_url=WS_URL)
TTL_S = 2 * 3600


def _route(event):
    ctx = event["requestContext"]
    auth = ctx.get("authorizer") or {}
    sub, vid, conn = auth.get("principalId"), auth.get("vid", "-"), ctx["connectionId"]
    route = ctx["routeKey"]
    trace.begin(None, vid, fn="ws")
    if route == "$connect":
        trace.step("p2s5", "4")
        ddb.put_item(TableName=CONN, Item={"pk": {"S": f"CUST#{sub}"}, "sk": {"S": conn}, "vid": {"S": vid},
                                           "connectedAt": {"N": str(int(time.time()))}, "expiresAt": {"N": str(int(time.time()) + TTL_S)}})
    elif route == "$disconnect":
        ddb.delete_item(TableName=CONN, Key={"pk": {"S": f"CUST#{sub}"}, "sk": {"S": conn}})
    trace.flush()
    return {"statusCode": 200, "body": "ok" if route != "$default" else json.dumps({"type": "pong"})}


def push(msg):
    """Invoked by the saga: {customerId, vid, cid, orderId, status, scenario}."""
    sc = msg.get("scenario", "p3s3")
    steps = {"p3s3": ("6", "7"), "p3s4": ("4", "4")}.get(sc, ("6", "7"))
    trace.begin(msg.get("cid"), msg.get("vid"), fn="ws")
    trace.step(sc, steps[0])
    out = ddb.query(TableName=CONN, KeyConditionExpression="pk = :pk", FilterExpression="vid = :v",
                    ExpressionAttributeValues={":pk": {"S": f"CUST#{msg['customerId']}"}, ":v": {"S": msg.get("vid", "-")}})
    frame = {"type": "checkout.result", "orderId": msg.get("orderId"), "status": msg.get("status"), "reason": msg.get("reason"),
             "total": msg.get("total"), "cid": msg.get("cid")}
    trace.step(sc, steps[1])
    sent = 0
    for item in out["Items"]:
        try:
            mgmt.post_to_connection(ConnectionId=item["sk"]["S"], Data=json.dumps(frame).encode())
            sent += 1
        except mgmt.exceptions.GoneException:
            ddb.delete_item(TableName=CONN, Key={"pk": item["pk"], "sk": item["sk"]})
    trace.note("apigw", "WebSocket frame", f"API Gateway sends the frame on {sent} open connection(s). The page shows the result.",
               request=json.dumps(frame), sc=sc, st="8" if sc == "p3s3" else "5")
    trace.flush()
    return {"sent": sent}


def lambda_handler(event, context):
    if "requestContext" in event and "routeKey" in event.get("requestContext", {}):
        return _route(event)
    return push(event)
