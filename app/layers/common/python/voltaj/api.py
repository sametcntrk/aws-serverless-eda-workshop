"""REST API helpers: read the proxy event, answer with {ok, data, trace, cid}."""
import base64
import json
from decimal import Decimal

from . import trace


class HttpError(Exception):
    def __init__(self, status, message, **extra):
        super().__init__(message)
        self.status, self.message, self.extra = status, message, extra


def _default(o):
    if isinstance(o, Decimal):
        return int(o) if o == o.to_integral_value() else float(o)
    if isinstance(o, (set, frozenset)):
        return sorted(o)
    if isinstance(o, bytes):
        return o.decode("utf-8", "replace")
    return str(o)


def dumps(v):
    return json.dumps(v, default=_default, ensure_ascii=False)


class Request:
    def __init__(self, event):
        self.event = event
        h = {k.lower(): v for k, v in (event.get("headers") or {}).items()}
        self.headers = h
        self.method = event.get("httpMethod", "GET")
        self.resource = event.get("resource", "")
        self.path = event.get("path", "")
        self.query = event.get("queryStringParameters") or {}
        self.params = event.get("pathParameters") or {}
        raw = event.get("body") or ""
        if event.get("isBase64Encoded") and raw:
            raw = base64.b64decode(raw).decode()
        self.raw_body = raw
        try:
            self.body = json.loads(raw) if raw else {}
        except ValueError:
            self.body = {}
        auth = (event.get("requestContext") or {}).get("authorizer") or {}
        self.claims = auth.get("claims") or {}
        self.sub = self.claims.get("sub")
        groups = self.claims.get("cognito:groups") or ""
        self.groups = groups if isinstance(groups, list) else [g for g in str(groups).strip("[]").replace(",", " ").split() if g]
        self.cid = h.get("x-cid")
        self.vid = h.get("x-vid") or "-"

    @property
    def is_admin(self):
        return "admins" in self.groups


def respond(status, body):
    return {"statusCode": status, "headers": {"Content-Type": "application/json; charset=utf-8", "Cache-Control": "no-store"},
            "body": dumps(body)}


def handler(fn_name, routes):
    """Build a Lambda handler from {(METHOD, resource): func(req) -> data}."""
    def lambda_handler(event, context):
        req = Request(event)
        trace.begin(req.cid, req.vid, fn=fn_name)
        key = req.path if "{proxy+}" in req.resource else req.resource
        func = routes.get((req.method, key))
        try:
            if func is None:
                raise HttpError(404, f"No route for {req.method} {key}.")
            data = func(req)
            status = 200
            if isinstance(data, tuple):
                status, data = data
            return respond(status, {"ok": True, "data": data, "cid": trace.cid(), "trace": trace.flush()})
        except HttpError as e:
            return respond(e.status, {"ok": False, "error": e.message, **e.extra, "cid": trace.cid(), "trace": trace.flush()})
        except Exception as e:  # noqa: BLE001 - show the error in the panel
            print(f"error: {type(e).__name__}: {e}")
            return respond(500, {"ok": False, "error": f"{type(e).__name__}: {e}"[:400], "cid": trace.cid(), "trace": trace.flush()})
    return lambda_handler
