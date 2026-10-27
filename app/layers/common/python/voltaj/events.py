"""Read cid and vid from any event shape (EventBridge, SNS in SQS, SQS body, MSK record)."""
import base64
import json


def unwrap(body):
    """SQS body → the EventBridge event (also through an SNS envelope)."""
    if isinstance(body, str):
        try:
            body = json.loads(body)
        except ValueError:
            return {"raw": body}
    if isinstance(body, dict) and body.get("Type") == "Notification" and "Message" in body:
        return unwrap(body["Message"])
    return body


def ids(evt):
    d = (evt or {}).get("detail") or evt or {}
    return d.get("cid"), d.get("vid")


def kafka_value(rec):
    try:
        return json.loads(base64.b64decode(rec.get("value") or b"").decode())
    except ValueError:
        return {}


def kafka_headers(rec):
    out = {}
    for h in rec.get("headers") or []:
        for k, v in h.items():
            out[k] = bytes(v).decode("utf-8", "replace") if isinstance(v, list) else v
    return out
