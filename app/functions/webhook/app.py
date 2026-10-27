"""Payment webhook: check the HMAC signature, find the task token, stop duplicates, call SendTaskSuccess or SendTaskFailure."""
import hashlib
import hmac
import json
import os
import time

from voltaj import trace
from voltaj.api import HttpError, handler

IDEM = os.environ["IDEMPOTENCY_TABLE"]
SECRET_ARN = os.environ["PAY_SECRET_ARN"]
TOLERANCE_S = 300
ddb, sfn, sm = trace.client("dynamodb"), trace.client("stepfunctions"), trace.client("secretsmanager")
_secret = {}


def _webhook_secret():
    if "v" not in _secret:
        _secret["v"] = json.loads(sm.get_secret_value(SecretId=SECRET_ARN)["SecretString"])["webhookSecret"]
    return _secret["v"]


def payment(req):
    try:
        evt = json.loads(req.raw_body)
    except ValueError:
        raise HttpError(400, "The body is not JSON.") from None
    data = evt.get("data") or {}
    trace.begin(data.get("cid"), data.get("vid"), fn="webhook")
    trace.step("p3s2", "3")
    sig = dict(p.split("=", 1) for p in (req.headers.get("payment-signature") or "").split(",") if "=" in p)
    with trace.call("lambda", "Verify HMAC", "hmac.compare_digest(HMAC-SHA256(secret, t + '.' + raw body), v1)",
                    {"t": sig.get("t"), "event": evt.get("id"), "type": evt.get("type")}, path="Inside the function",
                    auth="Shared webhook secret (Secrets Manager)") as t:
        expected = hmac.new(_webhook_secret().encode(), f"{sig.get('t')}.{req.raw_body}".encode(), hashlib.sha256).hexdigest()
        if not sig.get("v1") or not hmac.compare_digest(expected, sig["v1"]):
            t.result(ok=False, note="The signature does not match. The function stops here.")
            raise HttpError(401, "Bad signature.")
        if abs(time.time() - int(sig.get("t") or 0)) > TOLERANCE_S:
            raise HttpError(401, "The signature is too old (replay protection).")
        t.result(note="The signature matches, so the call comes from the payment provider and the body did not change.")
    order_id = data.get("orderId")
    trace.step("p3s2", "4")
    got = ddb.get_item(TableName=IDEM, Key={"pk": {"S": f"PAY#{order_id}"}})
    if "Item" not in got:
        raise HttpError(404, f"No payment is waiting for order {order_id}.")
    token = got["Item"]["taskToken"]["S"]
    try:
        ddb.put_item(TableName=IDEM, Item={"pk": {"S": f"EVT#{evt.get('id')}"}, "expiresAt": {"N": str(int(time.time()) + 86400)}},
                     ConditionExpression="attribute_not_exists(pk)")
    except ddb.exceptions.ConditionalCheckFailedException:
        trace.note("ddb", "Duplicate webhook", "This webhook event was processed before. The idempotency key stops it. "
                   "The answer is still 200, so the provider does not send it again.")
        return {"duplicate": True}
    trace.step("p3s2", "5")
    if evt.get("type") == "payment.succeeded":
        sfn.send_task_success(taskToken=token, output=json.dumps({"paymentId": data.get("paymentId"), "status": "PAID"}))
    else:
        sfn.send_task_failure(taskToken=token, error="PaymentDeclined", cause=str(data.get("reason") or "declined"))
    return {"received": True}


lambda_handler = handler("webhook", {("POST", "/webhooks/payment"): payment})
