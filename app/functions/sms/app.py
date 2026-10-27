"""Lambda sms: SNS (filter smsOptIn) → SQS sms → End User Messaging SendTextMessage to a simulator number."""
import os
import time

from voltaj import trace
from voltaj.events import unwrap

IDEM = os.environ["IDEMPOTENCY_TABLE"]
ORIGIN = os.environ.get("SMS_ORIGIN", "")
TO = os.environ.get("SMS_TO", "+14254147755")
ddb, sms = trace.client("dynamodb"), trace.client("pinpoint-sms-voice-v2")


def _one(record):
    evt = unwrap(record["body"])
    d = evt.get("detail") or {}
    kind = evt.get("detail-type")
    trace.begin(d.get("cid"), d.get("vid"), fn="sms")
    trace.note("sqs", "Receive (event source mapping)", "The subscription filter policy {smsOptIn: [true]} let the event into the SMS "
               "queue.", sc="p4s4", st="2", event={"queue": "voltaj-sms", "detailType": kind, "keys": {"orderId": d.get("orderId")}})
    try:
        ddb.put_item(TableName=IDEM, Item={"pk": {"S": f"SMS#{d.get('eventId') or evt.get('id')}"}, "expiresAt": {"N": str(int(time.time()) + 86400)}},
                     ConditionExpression="attribute_not_exists(pk)")
    except ddb.exceptions.ConditionalCheckFailedException:
        trace.note("ddb", "Duplicate stopped", "This event ID got an SMS before.", sc="p4s4", st="2")
        return
    body = (f"Voltaj: order {d['orderId']} is confirmed. Total EUR {d.get('total', 0):.2f}." if kind == "OrderPlaced"
            else f"Voltaj: order {d['orderId']} shipped. Tracking {d.get('trackingNo', '-')}.")
    trace.step("p4s4", "3")
    if not ORIGIN:
        trace.note("eum", "SendTextMessage (skipped)", "No simulator origination number is configured.", ok=False)
        return
    out = sms.send_text_message(DestinationPhoneNumber=TO, OriginationIdentity=ORIGIN, MessageBody=body, MessageType="TRANSACTIONAL",
                                Context={"cid": (d.get("cid") or "none")[:100]})
    trace.note("eum", "Delivery", f"The simulator number {TO} received the SMS inside AWS (no carrier network). The Inbox page shows it.",
               sc="p4s4", st="4", ui="inbox", data={"kind": "sms", "to": TO, "from": ORIGIN, "body": body, "messageId": out.get("MessageId"),
                                                    "orderId": d.get("orderId")})


def lambda_handler(event, context):
    failures = []
    for r in event["Records"]:
        try:
            _one(r)
        except Exception as e:  # noqa: BLE001
            print(f"failed {r['messageId']}: {e}")
            failures.append({"itemIdentifier": r["messageId"]})
        finally:
            trace.flush()
    return {"batchItemFailures": failures}
