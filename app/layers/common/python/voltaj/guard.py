"""Cost guard: fixed-window counters in the table voltaj-guard. A blocked call raises HttpError 429."""
import os
import time

from . import trace
from .api import HttpError

TABLE = os.environ.get("GUARD_TABLE", "voltaj-guard")
_ddb = trace.client("dynamodb")


def hit(key, limit, window_s, what):
    """Count one use of `key` in the current window. Raise 429 when the limit is reached."""
    now = int(time.time())
    start = now - now % window_s
    try:
        _ddb.update_item(TableName=TABLE, Key={"pk": {"S": f"{key}#{start}"}},
                         UpdateExpression="ADD n :one SET expiresAt = :exp",
                         ConditionExpression="attribute_not_exists(n) OR n < :limit",
                         ExpressionAttributeValues={":one": {"N": "1"}, ":limit": {"N": str(limit)},
                                                    ":exp": {"N": str(start + window_s + 60)}})
    except _ddb.exceptions.ConditionalCheckFailedException:
        wait = start + window_s - now
        trace.note("guard", "Limit reached", f"Cost guard: {what} is limited to {limit} per {window_s // 60 or window_s} "
                   f"{'min' if window_s >= 60 else 's'}. Try again in {wait} s.", ok=False,
                   error=f"Limit reached: {limit} per {window_s} s")
        raise HttpError(429, f"Limit reached: {what} is limited to {limit} per {window_s} s. Try again in {wait} s.")
