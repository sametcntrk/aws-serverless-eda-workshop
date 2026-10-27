"""OpenSearch Serverless client with SigV4 (service aoss), no extra library. Each call is one trace entry."""
import json
import os
import urllib.request

import boto3
from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest

from . import trace

ENDPOINT = os.environ.get("AOSS_ENDPOINT", "")
REGION = os.environ.get("AWS_REGION", "eu-central-1")
_creds = boto3.Session().get_credentials()


def request(method, path, body=None, op=None, sc=None, st=None):
    url = ENDPOINT.rstrip("/") + path
    data = json.dumps(body).encode() if body is not None else None
    import hashlib
    req = AWSRequest(method=method, url=url, data=data, headers={"Content-Type": "application/json",
                                                                 "X-Amz-Content-Sha256": hashlib.sha256(data or b"").hexdigest()})
    SigV4Auth(_creds.get_frozen_credentials(), "aoss", REGION).add_auth(req)
    text = f"{method} {path}" + (f"\n{json.dumps(body, ensure_ascii=False, indent=1)}" if body is not None else "")
    with trace.call("aoss", op or f"{method} {path.split('?')[0]}", text, path=f"{'Lambda (AWS network)'} → collection endpoint (HTTPS)",
                    auth="IAM role (SigV4, service aoss)") as t:
        r = urllib.request.Request(url, data=data, method=method, headers=dict(req.headers))
        try:
            with urllib.request.urlopen(r, timeout=10) as resp:
                out = json.loads(resp.read() or b"{}")
        except urllib.error.HTTPError as e:
            raise RuntimeError(f"OpenSearch HTTP {e.code}: {e.read()[:300].decode('utf-8', 'replace')}") from None
        hits = (out.get("hits") or {}).get("hits")
        t.result(items=len(hits) if hits is not None else None, took=out.get("took"),
                 note=f"OpenSearch took {out.get('took')} ms inside the collection." if "took" in out else None)
        return out
