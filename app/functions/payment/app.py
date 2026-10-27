"""Lambda payment (VPC): saves the task token, then creates the payment at the provider over the NAT gateway."""
import json
import os
import socket
import time
import urllib.request

from voltaj import trace

IDEM = os.environ["IDEMPOTENCY_TABLE"]
SECRET_ARN = os.environ["PAY_SECRET_ARN"]
PAY_API = os.environ["PAY_API_URL"]
SHOP = os.environ["SHOP_URL"]
NAT_IPS = os.environ.get("NAT_IPS", "")
ddb, sm = trace.client("dynamodb"), trace.client("secretsmanager")
_key = {}


def _api_key():
    if "v" not in _key:
        _key["v"] = json.loads(sm.get_secret_value(SecretId=SECRET_ARN)["SecretString"])["apiKey"]
    return _key["v"]


def _my_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("10.0.0.2", 53))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except OSError:
        return "10.0.16.x"


def lambda_handler(event, context):
    order_id, cid, vid = event["orderId"], event.get("cid"), event.get("vid")
    trace.begin(cid, vid, fn="payment")
    trace.step("p3s1", "3")
    ddb.put_item(TableName=IDEM, Item={"pk": {"S": f"PAY#{order_id}"}, "taskToken": {"S": event["taskToken"]},
                                       "expiresAt": {"N": str(int(time.time()) + 86400)}})
    body = {"orderId": order_id, "amount": event["amount"], "currency": event.get("currency", "EUR"),
            "returnUrl": f"{SHOP}/checkout?order={order_id}", "metadata": {"cid": cid, "vid": vid, "orderId": order_id}}
    trace.step("p3s1", "4")
    path = (f"Lambda ENI {_my_ip()} (private-app a/b/c) → NAT gateway (SNAT to Elastic IP, one of {NAT_IPS}) → internet gateway "
            f"→ {PAY_API.split('/')[2]}")
    with trace.call("pay", "POST /v1/payments", f"POST {PAY_API}/v1/payments\nIdempotency-Key: {order_id}\n"
                    f"{json.dumps(body, indent=1)}", {"amount": event["amount"]}, path=path, auth="Bearer API key (Secrets Manager)") as t:
        req = urllib.request.Request(f"{PAY_API}/v1/payments", data=json.dumps(body).encode(), method="POST",
                                     headers={"Content-Type": "application/json", "Authorization": f"Bearer {_api_key()}",
                                              "Idempotency-Key": order_id, "User-Agent": "voltaj-payment/1"})
        with urllib.request.urlopen(req, timeout=10) as r:
            out = json.loads(r.read())
        t.result(data={"paymentId": out.get("id"), "checkoutUrl": out.get("checkoutUrl")}, ui="open-payment",
                 note="The provider created the payment. The workflow now waits for the webhook (task token). "
                      "Open the payment page and choose Pay, Decline or No answer.")
    trace.flush()
    return {"paymentId": out.get("id")}
