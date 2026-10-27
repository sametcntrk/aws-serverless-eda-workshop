"""Learning layer: a rule on the commerce bus sends every event here. The function writes trace entries for the steps that run
without our code (Pipes polling and filtering, rule matches, SNS fan-out), so the panel can show them."""
from voltaj import trace

RULES = {"OrderPlaced": [("p3s5", "1a", "sns", "Rule order-placed-notify → SNS topic voltaj-order-notifications"),
                         ("p3s5", "1b", "sqs", "Rule order-placed-fulfil → SQS queue voltaj-order-buffer"),
                         ("p3s5", "1c", "lambda", "Rule commerce-log → Lambda producer (VPC) → MSK")],
         "ShipmentDispatched": [("p4s2", "5", "sns", "Rule shipment-notify → SNS topic voltaj-order-notifications")],
         "PaymentFailed": []}
FANOUT = [("p4s3", "1", "sqs", "SNS → SQS voltaj-email (raw message delivery)"),
          ("p4s5", "1", "sqs", "SNS → SQS voltaj-backoffice (raw message delivery)")]


def lambda_handler(event, context):
    d = event.get("detail") or {}
    kind = event.get("detail-type")
    trace.begin(d.get("cid"), d.get("vid"), fn="bus")
    ev = {"source": event.get("source"), "detailType": kind, "bus": "voltaj-commerce",
          "keys": {k: d[k] for k in ("orderId", "trackingNo", "carrier", "reason", "total") if k in d}}
    if event.get("source") == "com.shop.3pl":
        trace.note("pipes", "Poll and filter", "The pipe voltaj-3pl-shipments polled the RabbitMQ queue shipments.events. The filter "
                   "{data: {type: [ShipmentDispatched]}} let this message through.", sc="p4s2", st="3",
                   request="Pipe source: Amazon MQ queue shipments.events; FilterCriteria data.type = ShipmentDispatched")
        trace.note("eb", "PutEvents (by the pipe)", "The pipe published the message on the bus with source com.shop.3pl.", sc="p4s2",
                   st="4", event=ev, request="events.put_events(EventBusName=voltaj-commerce, Source=com.shop.3pl, "
                                             "DetailType=ShipmentDispatched)")
    if d.get("burst"):
        return {"skipped": "burst"}
    for sc, st, svc, text in RULES.get(kind, []):
        trace.note(svc, "Rule matched", text, sc=sc, st=st, event=ev, request=f"event pattern: detail-type = {kind}")
    if kind in ("OrderPlaced", "ShipmentDispatched"):
        for sc, st, svc, text in FANOUT + ([("p4s4", "1", "sqs", "SNS → SQS voltaj-sms (filter policy smsOptIn = true matched)")]
                                           if d.get("smsOptIn") else []):
            trace.note("sns", "Fan-out", text, sc=sc, st=st, event={"topic": "voltaj-order-notifications", "detailType": kind})
    trace.flush()
    return {"ok": True}
