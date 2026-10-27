"""Lambda counters: MSK consumer group counters → atomic ADD per product in DynamoDB."""
import collections
import os

from voltaj import trace
from voltaj.events import kafka_headers, kafka_value

COUNTERS = os.environ["COUNTERS_TABLE"]
ddb = trace.client("dynamodb")


def lambda_handler(event, context):
    by_vid = collections.defaultdict(collections.Counter)
    cids = {}
    n = 0
    for tp, recs in event.get("records", {}).items():
        for r in recs:
            v, h = kafka_value(r), kafka_headers(r)
            n += 1
            if v.get("type") in ("page_view", "product_view") and v.get("sku"):
                by_vid[h.get("vid", "-")][v["sku"]] += 1
                cids[h.get("vid", "-")] = h.get("cid")
    for vid, counts in by_vid.items():
        trace.begin(cids.get(vid), vid, fn="counters")
        trace.note("msk", "Poll (consumer group counters)", f"The event source mapping (provisioned mode) delivered {n} record(s) "
                   f"from {', '.join(event.get('records', {}).keys())}.", sc="p5s8", st="1")
        trace.step("p5s8", "2")
        for sku, k in counts.items():
            ddb.update_item(TableName=COUNTERS, Key={"pk": {"S": f"POP#SKU#{sku}"}}, UpdateExpression="ADD #v :n",
                            ExpressionAttributeNames={"#v": "views"}, ExpressionAttributeValues={":n": {"N": str(k)}})
        trace.flush()
    return {"records": n}
