"""Lambda archive: MSK consumer group archive → one gzip JSON-lines file per batch in the S3 data lake (partitioned by date and hour)."""
import collections
import gzip
import json
import os
import time
import uuid

from voltaj import trace
from voltaj.events import kafka_headers, kafka_value

LAKE = os.environ["LAKE_BUCKET"]
s3 = trace.client("s3")


def lambda_handler(event, context):
    groups = collections.defaultdict(list)
    first = {}
    for tp, recs in event.get("records", {}).items():
        topic = tp.rsplit("-", 1)[0]
        for r in recs:
            groups[topic].append(dict(kafka_value(r), _partition=r["partition"], _offset=r["offset"]))
            first.setdefault(topic, (kafka_headers(r), tp, r["offset"]))
    for topic, rows in groups.items():
        h, tp, off = first[topic]
        trace.begin(h.get("cid"), h.get("vid"), fn="archive")
        trace.note("msk", "Poll (consumer group archive)", f"{len(rows)} record(s) from {tp}, first offset {off}.", sc="p5s7", st="1")
        trace.step("p5s7", "2")
        t = time.gmtime()
        key = f"{topic}/dt={time.strftime('%Y-%m-%d', t)}/hour={t.tm_hour:02d}/part-{uuid.uuid4().hex[:8]}.json.gz"
        body = gzip.compress("\n".join(json.dumps(r) for r in rows).encode())
        s3.put_object(Bucket=LAKE, Key=key, Body=body, ContentType="application/json", ContentEncoding="gzip")
        trace.flush()
    return {"files": len(groups)}
