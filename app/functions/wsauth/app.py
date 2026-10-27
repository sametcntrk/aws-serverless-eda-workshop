"""WebSocket $connect authorizer: the access token must be valid in Cognito (GetUser checks it on the server side)."""
from voltaj import trace

idp = trace.client("cognito-idp")


def lambda_handler(event, context):
    q = event.get("queryStringParameters") or {}
    vid = (q.get("vid") or "-")[:64]
    trace.begin(None, vid, fn="wsauth", sc="p2s5", st="3")
    try:
        user = idp.get_user(AccessToken=q.get("token") or "")
    except Exception as e:  # noqa: BLE001 - deny on any error
        print(f"deny: {e}")
        trace.flush()
        return {"principalId": "anonymous", "policyDocument": {"Version": "2012-10-17", "Statement": [
            {"Action": "execute-api:Invoke", "Effect": "Deny", "Resource": event["methodArn"]}]}}
    sub = next(a["Value"] for a in user["UserAttributes"] if a["Name"] == "sub")
    trace.flush()
    return {"principalId": sub, "context": {"vid": vid, "username": user["Username"]},
            "policyDocument": {"Version": "2012-10-17", "Statement": [
                {"Action": "execute-api:Invoke", "Effect": "Allow", "Resource": event["methodArn"]}]}}
