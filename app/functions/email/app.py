"""Lambda email: SNS → SQS email → SESv2 SendEmail with a template. Receivers are SES mailbox simulator addresses."""
import json
import os
import time

from voltaj import trace
from voltaj.events import unwrap

IDEM, GUARD = os.environ["IDEMPOTENCY_TABLE"], os.environ["GUARD_TABLE"]
FROM = os.environ["MAIL_FROM"]
CONFIG_SET = os.environ["CONFIG_SET"]
TO = os.environ.get("MAIL_TO", "success@simulator.amazonses.com")
ddb, ses = trace.client("dynamodb"), trace.client("sesv2")
SUBJECTS = {"OrderPlaced": ("OrderConfirmed", "Voltaj: order {{orderId}} is confirmed"),
            "ShipmentDispatched": ("ShipmentDispatched", "Voltaj: order {{orderId}} is on the way")}


def _broken():
    got = ddb.get_item(TableName=GUARD, Key={"pk": {"S": "FLAG#break-email"}})
    return "Item" in got and int(got["Item"].get("expiresAt", {}).get("N", 0)) > time.time()


def _render(kind, data):
    if kind == "OrderPlaced":
        rows = "".join(f"<tr><td>{x['qty']} × {x['name']}</td><td>€{x['price']:.2f}</td></tr>" for x in data.get("lines", []))
        html = (f"<h1>Thank you, {data.get('name', 'customer')}!</h1><p>We received order <b>{data['orderId']}</b>.</p>"
                f"<table>{rows}</table><p>Total: <b>€{data.get('total', 0):.2f}</b></p><p>We tell you when the order ships.</p>")
    else:
        html = (f"<h1>Your order is on the way</h1><p>Order <b>{data['orderId']}</b> left the warehouse.</p>"
                f"<p>Carrier: {data.get('carrier', '-')}<br>Tracking number: <b>{data.get('trackingNo', '-')}</b></p>")
    return SUBJECTS[kind][1].replace("{{orderId}}", data["orderId"]), html


def _one(record):
    evt = unwrap(record["body"])
    d = evt.get("detail") or {}
    kind = evt.get("detail-type")
    trace.begin(d.get("cid"), d.get("vid"), fn="email")
    trace.note("sqs", "Receive (event source mapping)", f"SNS put the event in the email queue (raw delivery). Receive count "
               f"{record['attributes'].get('ApproximateReceiveCount')}.", sc="p4s3", st="2",
               event={"queue": "voltaj-email", "detailType": kind, "keys": {"orderId": d.get("orderId")},
                      "receiveCount": int(record["attributes"].get("ApproximateReceiveCount", 1))})
    if _broken():
        trace.note("lambda", "Consumer error", "Experiment: the email consumer is broken. The message goes back to the queue. After 3 "
                   "receives SQS moves it to the DLQ voltaj-email-dlq.", ok=False, error="RuntimeError: email consumer is broken (experiment)",
                   sc="p4s3", st="2")
        raise RuntimeError("email consumer is broken (experiment)")
    key = f"MAIL#{d.get('eventId') or evt.get('id')}"
    try:
        ddb.put_item(TableName=IDEM, Item={"pk": {"S": key}, "expiresAt": {"N": str(int(time.time()) + 86400)}},
                     ConditionExpression="attribute_not_exists(pk)")
    except ddb.exceptions.ConditionalCheckFailedException:
        trace.note("ddb", "Duplicate stopped", "This event ID got an email before. The idempotency key stops a second email.",
                   sc="p4s3", st="2")
        return
    subject, html = _render(kind, d)
    trace.step("p4s3", "3")
    template, _ = SUBJECTS[kind]
    out = ses.send_email(FromEmailAddress=FROM, Destination={"ToAddresses": [TO]}, ConfigurationSetName=CONFIG_SET,
                         Content={"Template": {"TemplateName": f"voltaj-{template}",
                                               "TemplateData": json.dumps({"orderId": d["orderId"], "name": d.get("name", "customer"),
                                                                           "total": f"{d.get('total', 0):.2f}",
                                                                           "trackingNo": d.get("trackingNo", ""),
                                                                           "carrier": d.get("carrier", "")})}},
                         EmailTags=[{"Name": "cid", "Value": (d.get("cid") or "none")[:200]}])
    trace.note("ses", "Delivery", f"SES delivered the message to {TO} (mailbox simulator, no real inbox). The Inbox page shows it.",
               sc="p4s3", st="4", ui="inbox", data={"kind": "email", "to": TO, "from": FROM, "subject": subject, "html": html,
                                                    "messageId": out.get("MessageId"), "orderId": d.get("orderId")})


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
