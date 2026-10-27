"""Lambda order (VPC): writes the order to Aurora PostgreSQL through RDS Proxy (IAM auth); reads order history; runs the migration."""
import json
import os
import ssl
import time

import pg8000.native

from voltaj import trace
from voltaj.api import HttpError, handler as api_handler

PROXY = os.environ["PROXY_ENDPOINT"]
DB = os.environ.get("DB_NAME", "voltaj")
CART = os.environ["CART_TABLE"]
REGION = os.environ.get("AWS_REGION", "eu-central-1")
rds, ddb, sm = trace.client("rds"), trace.client("dynamodb"), trace.client("secretsmanager")
_conn = {}
PATH = "Lambda ENI (private-app) → RDS Proxy ENI (private-data, TLS 5432) → Aurora writer"

SCHEMA = """
CREATE TABLE IF NOT EXISTS customers (customer_id text PRIMARY KEY, name text NOT NULL, email text NOT NULL, city text,
  sms_opt_in boolean NOT NULL DEFAULT false, created_at timestamptz NOT NULL DEFAULT now());
CREATE TABLE IF NOT EXISTS orders (order_id text PRIMARY KEY, customer_id text NOT NULL, visitor_id text NOT NULL DEFAULT '-',
  status text NOT NULL, total numeric(10,2) NOT NULL, currency text NOT NULL DEFAULT 'EUR', payment_id text,
  created_at timestamptz NOT NULL DEFAULT now());
CREATE TABLE IF NOT EXISTS order_lines (order_id text NOT NULL REFERENCES orders(order_id) ON DELETE CASCADE, sku text NOT NULL,
  name text NOT NULL, qty int NOT NULL CHECK (qty > 0), price numeric(10,2) NOT NULL, PRIMARY KEY (order_id, sku));
CREATE INDEX IF NOT EXISTS orders_customer ON orders (customer_id, created_at DESC);
"""


def _connect(user):
    key = user
    c = _conn.get(key)
    if c is not None:
        return c
    with trace.call("aurora", "Connect (IAM token)", f"rds.generate_db_auth_token(host=proxy, port=5432, user='{user}')\n"
                    f"pg8000.connect(host=proxy, user='{user}', password=<15-minute token>, ssl=TLS)", {"user": user}, path=PATH,
                    auth="IAM database authentication at RDS Proxy") as t:
        token = rds.generate_db_auth_token(DBHostname=PROXY, Port=5432, DBUsername=user, Region=REGION)
        c = pg8000.native.Connection(user, host=PROXY, database=DB, password=token, ssl_context=ssl.create_default_context(), timeout=15)
        t.result(note="RDS Proxy checks the token with IAM, then lends a pooled connection to the Aurora writer.")
    _conn[key] = c
    return c


def _sql(cx, op, sql, **params):
    with trace.call("aurora", op, " ".join(sql.split()), {k: v for k, v in params.items() if not isinstance(v, (list, dict))},
                    path=PATH, auth="IAM token (user order_svc)") as t:
        rows = cx.run(sql, **params)
        cols = [col["name"] for col in (cx.columns or [])]
        t.result(items=cx.row_count if cx.row_count >= 0 else len(rows or []))
        return [dict(zip(cols, r)) for r in (rows or [])]


def write_order(event):
    trace.begin(event.get("cid"), event.get("vid"), fn="order")
    trace.step("p3s3", "2")
    c = _connect("order_svc")
    trace.step("p3s3", "3")
    lines = event["lines"]
    total = round(sum(x["qty"] * x["price"] for x in lines), 2)
    try:
        _sql(c, "BEGIN", "BEGIN")
        _sql(c, "INSERT orders", "INSERT INTO orders (order_id, customer_id, visitor_id, status, total, currency, payment_id) "
             "VALUES (:o, :c, :v, 'CONFIRMED', :t, 'EUR', :p)", o=event["orderId"], c=event["customerId"], v=event.get("vid", "-"),
             t=total, p=event.get("paymentId"))
        for x in lines:
            _sql(c, "INSERT order_lines", "INSERT INTO order_lines (order_id, sku, name, qty, price) VALUES (:o, :s, :n, :q, :p)",
                 o=event["orderId"], s=x["sku"], n=x["name"], q=x["qty"], p=x["price"])
        _sql(c, "COMMIT", "COMMIT")
    except Exception:
        try:
            c.run("ROLLBACK")
        except Exception:  # noqa: BLE001
            _conn.clear()
        trace.flush()
        raise
    # The cart is empty after a confirmed order.
    ddb.batch_write_item(RequestItems={CART: [{"DeleteRequest": {"Key": {"pk": {"S": f"CART#{event['customerId']}~{event.get('vid', '-')}"},
                                                                        "sk": {"S": f"SKU#{x['sku']}"}}}} for x in lines[:25]]})
    trace.flush()
    return {"orderId": event["orderId"], "total": total}


def history(req):
    if not req.sub:
        raise HttpError(401, "Sign in first.")
    c = _connect("order_svc")
    rows = _sql(c, "SELECT orders", "SELECT o.order_id, o.status, o.total, o.created_at, o.visitor_id = :v AS mine, "
                "(SELECT json_agg(json_build_object('sku', l.sku, 'name', l.name, 'qty', l.qty, 'price', l.price)) FROM order_lines l "
                "WHERE l.order_id = o.order_id) AS lines FROM orders o WHERE o.customer_id = :c ORDER BY o.created_at DESC LIMIT 20",
                c=req.sub, v=req.vid)
    for r in rows:
        r["created_at"] = r["created_at"].isoformat()
        r["total"] = float(r["total"])
    return rows


def migrate(event):
    """Create the schema and the role order_svc; load the persona history. Runs as the master user."""
    trace.begin(None, "-", fn="order")
    admin = json.loads(sm.get_secret_value(SecretId=os.environ["ADMIN_SECRET_ARN"])["SecretString"])
    svc = json.loads(sm.get_secret_value(SecretId=os.environ["ORDER_SECRET_ARN"])["SecretString"])
    c = pg8000.native.Connection(admin["username"], host=PROXY, database=DB, password=rds.generate_db_auth_token(
        DBHostname=PROXY, Port=5432, DBUsername=admin["username"], Region=REGION), ssl_context=ssl.create_default_context(), timeout=30)
    for stmt in [s for s in SCHEMA.split(";") if s.strip()]:
        c.run(stmt)
    exists = c.run("SELECT 1 FROM pg_roles WHERE rolname = 'order_svc'")
    pw = svc["password"].replace("'", "''")
    c.run(f"{'ALTER' if exists else 'CREATE'} ROLE order_svc LOGIN PASSWORD '{pw}'")
    c.run("GRANT SELECT, INSERT, UPDATE ON customers, orders, order_lines TO order_svc")
    n = 0
    for cu in event.get("customers", []):
        c.run("INSERT INTO customers (customer_id, name, email, city, sms_opt_in) VALUES (:i, :n, :e, :c, :s) "
              "ON CONFLICT (customer_id) DO UPDATE SET name = EXCLUDED.name, email = EXCLUDED.email, city = EXCLUDED.city, "
              "sms_opt_in = EXCLUDED.sms_opt_in", i=cu["id"], n=cu["name"], e=cu["email"], c=cu.get("city"), s=cu.get("smsOptIn", False))
    for o in event.get("orders", []):
        c.run("INSERT INTO orders (order_id, customer_id, visitor_id, status, total, created_at) VALUES (:o, :c, 'seed', :s, :t, :d) "
              "ON CONFLICT (order_id) DO NOTHING", o=o["id"], c=o["customerId"], s=o.get("status", "DELIVERED"), t=o["total"], d=o["date"])
        for x in o["lines"]:
            c.run("INSERT INTO order_lines (order_id, sku, name, qty, price) VALUES (:o, :s, :n, :q, :p) ON CONFLICT DO NOTHING",
                  o=o["id"], s=x["sku"], n=x["name"], q=x["qty"], p=x["price"])
        n += 1
    count = c.run("SELECT count(*) FROM orders")[0][0]
    c.close()
    trace.flush()
    return {"ok": True, "seededOrders": n, "orders": count}


def report(event):
    """Recent orders with their lines, for the 101 big picture and the admin report."""
    trace.begin(None, "-", fn="order")
    c = _connect("order_svc")
    rows = c.run("SELECT o.order_id, o.customer_id, o.status, o.total, o.created_at, (SELECT json_agg(json_build_object('sku', l.sku, "
                 "'name', l.name, 'qty', l.qty, 'price', l.price)) FROM order_lines l WHERE l.order_id = o.order_id) "
                 "FROM orders o ORDER BY o.created_at DESC LIMIT 120")
    count = c.run("SELECT count(*), (SELECT count(*) FROM order_lines) FROM orders")[0]
    trace.flush()
    return {"count": count[0], "lines": count[1], "orders": [{"order_id": r[0], "customer_id": r[1], "status": r[2], "total": float(r[3]),
            "created_at": r[4].isoformat(), "order_lines": r[5]} for r in rows]}


_api = api_handler("order", {("GET", "/orders"): history})


def lambda_handler(event, context):
    if "httpMethod" in event:
        return _api(event, context)
    if event.get("action") == "migrate":
        return migrate(event)
    if event.get("action") == "report":
        return report(event)
    return write_order(event)
