"""Learning layer: trace table stream → push each new entry over the WebSocket to the connections of the same visitor."""
import json
import os
from decimal import Decimal

import boto3
from boto3.dynamodb.types import TypeDeserializer

CONN = os.environ["WS_TABLE"]
mgmt = boto3.client("apigatewaymanagementapi", endpoint_url=os.environ["WS_MANAGEMENT_URL"])
ddb = boto3.client("dynamodb")
_d = TypeDeserializer()


def _plain(v):
    if isinstance(v, Decimal):
        return int(v) if v == v.to_integral_value() else float(v)
    if isinstance(v, dict):
        return {k: _plain(x) for k, x in v.items()}
    if isinstance(v, list):
        return [_plain(x) for x in v]
    return v


def lambda_handler(event, context):
    conns = {}
    sent = 0
    for r in event["Records"]:
        img = r["dynamodb"].get("NewImage")
        if r["eventName"] != "INSERT" or not img:
            continue
        e = _plain({k: _d.deserialize(v) for k, v in img.items()})
        vid = e.get("vid")
        if not vid or vid in ("-", "seed"):
            continue
        if vid not in conns:
            out = ddb.query(TableName=CONN, IndexName="by-visitor", KeyConditionExpression="vid = :v",
                            ExpressionAttributeValues={":v": {"S": vid}})
            conns[vid] = [(i["pk"]["S"], i["sk"]["S"]) for i in out["Items"]]
        e.pop("expiresAt", None)
        data = json.dumps({"type": "trace", "entry": e}, ensure_ascii=False).encode()
        if len(data) > 120_000:
            e.pop("data", None)
            data = json.dumps({"type": "trace", "entry": e}, ensure_ascii=False).encode()
        for pk, conn in list(conns[vid]):
            try:
                mgmt.post_to_connection(ConnectionId=conn, Data=data)
                sent += 1
            except mgmt.exceptions.GoneException:
                ddb.delete_item(TableName=CONN, Key={"pk": {"S": pk}, "sk": {"S": conn}})
                conns[vid].remove((pk, conn))
            except Exception as ex:  # noqa: BLE001
                print(f"push failed: {ex}")
    return {"sent": sent}
