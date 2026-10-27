"""Generates checkout.asl.json: the checkout saga (Step Functions Standard, JSONata).

Every direct service integration is followed by a small DynamoDB PutItem into the trace table, so the learning panel
shows the step live. Task states that invoke Lambda functions do not need it: the functions trace themselves.
"""
import json
import sys

S = {}


def j(expr):
    return "{% " + expr + " %}"


def trace(name, nxt, svc, engine, op, request, sc, st, path, auth="State machine role (SigV4)", note=None, event=None, data=None, ok=True,
          items=None):
    item = {
        "cid": {"S": j("$cid")}, "sk": {"S": j(f"$now() & '#checkout-saga#{name}'")}, "id": {"S": j("$substring($uuid(), 0, 10)")},
        "vid": {"S": j("$vid")}, "fn": {"S": "checkout-saga"}, "svc": {"S": svc}, "engine": {"S": engine}, "op": {"S": op},
        "request": {"S": request if request.startswith("{%") else request}, "sc": {"S": sc}, "st": {"S": st}, "ts": {"S": j("$now()")},
        "ms": {"N": j("$string($toMillis($states.context.State.EnteredTime) - $toMillis($t0))")}, "ok": {"BOOL": ok},
        "path": {"S": path}, "auth": {"S": auth}, "expiresAt": {"N": j("$string($floor($millis() / 1000) + 86400)")},
    }
    if note:
        item["note"] = {"S": note}
    if items:
        item["items"] = {"N": items}
    if event:
        item["event"] = {"M": event}
    if data:
        item["data"] = {"M": data}
    S[name] = {"Type": "Task", "Resource": "arn:aws:states:::dynamodb:putItem", "Arguments": {"TableName": "${TraceTable}", "Item": item},
               "Output": j("$states.input"), "Retry": [{"ErrorEquals": ["States.ALL"], "MaxAttempts": 2, "IntervalSeconds": 1}],
               "Catch": [{"ErrorEquals": ["States.ALL"], "Next": nxt}], "Next": nxt}


def ws(name, nxt, status, scenario, reason=None):
    payload = {"customerId": j("$customerId"), "vid": j("$vid"), "cid": j("$cid"), "orderId": j("$orderId"), "status": status,
               "total": j("$total"), "scenario": scenario}
    if reason:
        payload["reason"] = j(reason)
    S[name] = {"Type": "Task", "Resource": "arn:aws:states:::lambda:invoke", "Arguments": {"FunctionName": "${WsFn}", "Payload": payload},
               "Output": j("$states.input"), "Retry": [{"ErrorEquals": ["Lambda.ServiceException", "Lambda.TooManyRequestsException"],
                                                         "MaxAttempts": 3, "IntervalSeconds": 1, "BackoffRate": 2}],
               "Catch": [{"ErrorEquals": ["States.ALL"], "Next": nxt}], "Next": nxt}


def tx(sign):
    upd = ("SET available = available - :q, reserved = if_not_exists(reserved, :z) + :q" if sign < 0
           else "SET available = available + :q, reserved = reserved - :q")
    cond = "'ConditionExpression': 'available >= :q', " if sign < 0 else ""
    return j("$append([], $map($lines, function($l) { {'Update': {'TableName': '${StockTable}', 'Key': {'pk': {'S': 'SKU#' & $l.sku}}, "
             f"'UpdateExpression': '{upd}', {cond}'ExpressionAttributeValues': {{':q': {{'N': $string($l.qty)}}, ':z': {{'N': '0'}}}}}}}} }}))")


SFN_PATH = "Step Functions service → regional endpoint"
S["Init"] = {"Type": "Pass", "Assign": {
    "cid": j("$states.input.cid"), "vid": j("$states.input.vid"), "orderId": j("$states.input.orderId"),
    "customerId": j("$states.input.customerId"), "name": j("$states.input.name"), "email": j("$states.input.email"),
    "smsOptIn": j("$states.input.smsOptIn = 'true' or $states.input.smsOptIn = true"), "t0": j("$states.context.Execution.StartTime"),
    "total": 0, "lines": []}, "Next": "TraceStart"}
trace("TraceStart", "Guard", "sfn", "AWS Step Functions", "StartExecution",
      j("'states.start_execution(stateMachineArn=voltaj-checkout, name=' & $orderId & ', input={orderId, customerId, vid, cid})'"),
      "p2s6", "3", "CloudFront → REST API → Step Functions (direct integration, no Lambda)", auth="API Gateway integration role (SigV4)",
      note="API Gateway started the Standard workflow and answered 200 with the executionArn at once. The result comes later on the WebSocket.")
S["Guard"] = {"Type": "Task", "Resource": "arn:aws:states:::dynamodb:updateItem", "Arguments": {
    "TableName": "${GuardTable}", "Key": {"pk": {"S": j("'checkout#' & $vid & '#' & $string($floor($millis() / 60000))")}},
    "UpdateExpression": "ADD n :one SET expiresAt = :exp", "ConditionExpression": "attribute_not_exists(n) OR n < :limit",
    "ExpressionAttributeValues": {":one": {"N": "1"}, ":limit": {"N": "${CheckoutLimit}"},
                                  ":exp": {"N": j("$string($floor($millis() / 1000) + 180)")}}},
    "Catch": [{"ErrorEquals": ["States.ALL"], "Assign": {"reason": "limit reached: ${CheckoutLimit} checkouts per minute"},
               "Next": "TraceGuard"}], "Output": j("$states.input"), "Next": "ReadCart"}
trace("TraceGuard", "NotifyLimited", "guard", "Cost guard", "Limit reached", "dynamodb.update_item(TableName=voltaj-guard, ADD n :one IF n < limit)",
      "p2s6", "3", "Step Functions optimized integration → DynamoDB", ok=False,
      note="Cost guard: this visitor started too many checkouts in one minute. The workflow stops before it reserves stock.")
ws("NotifyLimited", "Failed", "LIMITED", "p3s4", "$reason")
S["ReadCart"] = {"Type": "Task", "Resource": "arn:aws:states:::aws-sdk:dynamodb:query", "Arguments": {
    "TableName": "${CartTable}", "KeyConditionExpression": "pk = :pk",
    "ExpressionAttributeValues": {":pk": {"S": j("'CART#' & $customerId & '~' & $vid")}}},
    "Assign": {"lines": j("$append([], $map($states.result.Items, function($i) { {'sku': $substringAfter($i.sk.S, 'SKU#'), "
                          "'name': $i.name.S, 'qty': $number($i.qty.N), 'price': $number($i.price.N)} }))"),
               "total": j("$round($sum($map($states.result.Items, function($i) { $number($i.qty.N) * $number($i.price.N) })), 2)"),
               "t0": j("$states.context.State.EnteredTime")}, "Next": "TraceReadCart"}
trace("TraceReadCart", "HasLines", "ddb", "Amazon DynamoDB", "Query",
      j("'dynamodb.query(TableName=voltaj-cart, KeyConditionExpression=pk = :pk, pk=CART#' & $customerId & '~' & $vid & ')'"),
      "p3s1", "1", "Step Functions SDK integration → DynamoDB", items=j("$string($count($lines))"),
      note="The workflow reads the cart lines and computes the total itself (SDK integration, no Lambda).")
S["HasLines"] = {"Type": "Choice", "Choices": [{"Condition": j("$count($lines) > 0"), "Next": "Reserve"}], "Default": "NotifyEmpty"}
S["Reserve"] = {"Type": "Task", "Resource": "arn:aws:states:::aws-sdk:dynamodb:transactWriteItems", "Arguments": {"TransactItems": tx(-1)},
                "Assign": {"t0": j("$states.context.State.EnteredTime")},
                "Catch": [{"ErrorEquals": ["States.ALL"], "Assign": {"reason": "out of stock"}, "Next": "TraceOutOfStock"}],
                "Next": "TraceReserve"}
trace("TraceReserve", "TraceInvokePay", "ddb", "Amazon DynamoDB", "TransactWriteItems",
      j("'dynamodb.transact_write_items(' & $join($map($lines, function($l) { 'Update stock SKU#' & $l.sku & ' SET available = available - ' & $l.qty & ' IF available >= ' & $l.qty }), '; ') & ')'"),
      "p3s1", "1", "Step Functions SDK integration → DynamoDB", items=j("$string($count($lines))"),
      note="All lines are reserved in one transaction. Each Update has the condition available >= qty, so stock never goes below zero.")
trace("TraceOutOfStock", "NotifyOutOfStock", "ddb", "Amazon DynamoDB", "TransactWriteItems",
      "dynamodb.transact_write_items(Update stock ... IF available >= qty)", "p3s1", "1", "Step Functions SDK integration → DynamoDB",
      ok=False, note="TransactionCanceledException: a condition failed. One product does not have enough stock, so nothing was reserved.")
ws("NotifyOutOfStock", "Failed", "OUT_OF_STOCK", "p3s4", "'out of stock'")
ws("NotifyEmpty", "Failed", "EMPTY_CART", "p3s4", "'the cart is empty'")
trace("TraceInvokePay", "Pay", "lambda", "AWS Lambda", "Invoke (.waitForTaskToken)",
      j("'lambda.invoke(FunctionName=voltaj-payment, Payload={orderId: ' & $orderId & ', amount: ' & $total & ' EUR, taskToken: AQB...})'"),
      "p3s1", "2", SFN_PATH, note="The workflow gives a task token to the payment function and pauses. It pays nothing while it waits.")
S["Pay"] = {"Type": "Task", "Resource": "arn:aws:states:::lambda:invoke.waitForTaskToken", "TimeoutSeconds": j("$number('${PaymentTimeout}')"),
            "Arguments": {"FunctionName": "${PaymentFn}", "Payload": {"orderId": j("$orderId"), "amount": j("$total"), "currency": "EUR",
                                                                       "customerId": j("$customerId"), "cid": j("$cid"), "vid": j("$vid"),
                                                                       "taskToken": j("$states.context.Task.Token")}},
            "Assign": {"paymentId": j("$states.result.paymentId"), "t0": j("$states.context.State.EnteredTime")},
            "Catch": [{"ErrorEquals": ["States.Timeout"], "Assign": {"reason": "timeout"}, "Next": "TraceTimeout"},
                      {"ErrorEquals": ["States.ALL"], "Assign": {"reason": j("$states.errorOutput.Cause ? $states.errorOutput.Cause : 'declined'")},
                       "Next": "TraceDeclined"}],
            "Next": "TraceInvokeOrder"}
trace("TraceTimeout", "Release", "sfn", "AWS Step Functions", "States.Timeout", "Task Pay: TimeoutSeconds reached",
      "p3s4", "1", SFN_PATH, ok=False, note="No webhook came before the timeout. The Catch block starts the compensation.")
trace("TraceDeclined", "Release", "sfn", "AWS Step Functions", "SendTaskFailure received", j("'Task Pay failed: ' & $reason"),
      "p3s4", "1", SFN_PATH, ok=False, note="The webhook called SendTaskFailure. The Catch block starts the compensation.")
trace("TraceInvokeOrder", "WriteOrder", "lambda", "AWS Lambda", "Invoke",
      j("'lambda.invoke(FunctionName=voltaj-order, Payload={orderId: ' & $orderId & ', lines: ' & $count($lines) & ', paymentId: ' & $paymentId & '})'"),
      "p3s3", "1", SFN_PATH, note="The payment is PAID. The workflow continues with the order write.")
S["WriteOrder"] = {"Type": "Task", "Resource": "arn:aws:states:::lambda:invoke", "Arguments": {"FunctionName": "${OrderFn}", "Payload": {
    "orderId": j("$orderId"), "customerId": j("$customerId"), "vid": j("$vid"), "cid": j("$cid"), "lines": j("$lines"),
    "paymentId": j("$paymentId")}},
    "Retry": [{"ErrorEquals": ["Lambda.ServiceException", "Lambda.TooManyRequestsException"], "MaxAttempts": 3, "IntervalSeconds": 1, "BackoffRate": 2}],
    "Catch": [{"ErrorEquals": ["States.ALL"], "Assign": {"reason": "the order write failed (refund needed)"}, "Next": "Release"}],
    "Next": "BuildPlaced"}
S["BuildPlaced"] = {"Type": "Pass", "Assign": {"placed": j(
    "{'orderId': $orderId, 'eventId': $orderId & '-placed', 'customerId': $customerId, 'name': $name, 'email': $email, "
    "'smsOptIn': $smsOptIn, 'total': $total, 'currency': 'EUR', 'lines': $lines, 'paymentId': $paymentId, 'cid': $cid, 'vid': $vid}"),
    "t0": j("$states.context.State.EnteredTime")}, "Next": "PublishPlaced"}
S["PublishPlaced"] = {"Type": "Task", "Resource": "arn:aws:states:::events:putEvents", "Arguments": {"Entries": [{
    "EventBusName": "${BusName}", "Source": "com.shop.checkout", "DetailType": "OrderPlaced", "Detail": j("$placed")}]},
    "Retry": [{"ErrorEquals": ["States.ALL"], "MaxAttempts": 3, "IntervalSeconds": 1, "BackoffRate": 2}], "Next": "TracePlaced"}
trace("TracePlaced", "TraceInvokeWs", "eb", "Amazon EventBridge", "PutEvents",
      j("'events.put_events(Entries=[{EventBusName: voltaj-commerce, Source: com.shop.checkout, DetailType: OrderPlaced, Detail: {orderId: ' & $orderId & ', total: ' & $total & ', ...}}])'"),
      "p3s3", "4", "Step Functions optimized integration → EventBridge", items="1",
      note="The bus has the event now. Three rules match it: notify (SNS), fulfil (SQS order buffer) and commerce-log (Lambda producer → MSK).",
      event={"source": {"S": "com.shop.checkout"}, "detailType": {"S": "OrderPlaced"}, "bus": {"S": "voltaj-commerce"},
             "keys": {"M": {"orderId": {"S": j("$orderId")}, "total": {"N": j("$string($total)")}}}},
      data={"detail": {"S": j("$string($placed)")}})
trace("TraceInvokeWs", "NotifyConfirmed", "lambda", "AWS Lambda", "Invoke",
      j("'lambda.invoke(FunctionName=voltaj-ws, Payload={customerId, orderId: ' & $orderId & ', status: CONFIRMED})'"), "p3s3", "5", SFN_PATH)
ws("NotifyConfirmed", "Done", "CONFIRMED", "p3s3")
S["Done"] = {"Type": "Succeed"}
S["Release"] = {"Type": "Task", "Resource": "arn:aws:states:::aws-sdk:dynamodb:transactWriteItems", "Arguments": {"TransactItems": tx(+1)},
                "Assign": {"t0": j("$states.context.State.EnteredTime")},
                "Retry": [{"ErrorEquals": ["States.ALL"], "MaxAttempts": 3, "IntervalSeconds": 1, "BackoffRate": 2}], "Next": "TraceRelease"}
trace("TraceRelease", "BuildFailed", "ddb", "Amazon DynamoDB", "TransactWriteItems",
      j("'dynamodb.transact_write_items(' & $join($map($lines, function($l) { 'Update stock SKU#' & $l.sku & ' SET available = available + ' & $l.qty }), '; ') & ')'"),
      "p3s4", "1", "Step Functions SDK integration → DynamoDB", items=j("$string($count($lines))"),
      note="Compensation: the reserved quantity goes back to available. The saga undoes its own earlier step.")
S["BuildFailed"] = {"Type": "Pass", "Assign": {"failed": j(
    "{'orderId': $orderId, 'eventId': $orderId & '-failed', 'customerId': $customerId, 'reason': $reason, 'total': $total, 'cid': $cid, 'vid': $vid}"),
    "t0": j("$states.context.State.EnteredTime")}, "Next": "PublishFailed"}
S["PublishFailed"] = {"Type": "Task", "Resource": "arn:aws:states:::events:putEvents", "Arguments": {"Entries": [{
    "EventBusName": "${BusName}", "Source": "com.shop.checkout", "DetailType": "PaymentFailed", "Detail": j("$failed")}]},
    "Retry": [{"ErrorEquals": ["States.ALL"], "MaxAttempts": 3, "IntervalSeconds": 1, "BackoffRate": 2}], "Next": "TraceFailed"}
trace("TraceFailed", "TraceInvokeWsFail", "eb", "Amazon EventBridge", "PutEvents",
      j("'events.put_events(Entries=[{EventBusName: voltaj-commerce, Source: com.shop.checkout, DetailType: PaymentFailed, Detail: {orderId: ' & $orderId & ', reason: ' & $reason & '}}])'"),
      "p3s4", "2", "Step Functions optimized integration → EventBridge", items="1",
      event={"source": {"S": "com.shop.checkout"}, "detailType": {"S": "PaymentFailed"}, "bus": {"S": "voltaj-commerce"},
             "keys": {"M": {"orderId": {"S": j("$orderId")}, "reason": {"S": j("$reason")}}}})
trace("TraceInvokeWsFail", "NotifyFailed", "lambda", "AWS Lambda", "Invoke",
      j("'lambda.invoke(FunctionName=voltaj-ws, Payload={customerId, orderId: ' & $orderId & ', status: PAYMENT_FAILED})'"), "p3s4", "3", SFN_PATH)
ws("NotifyFailed", "Failed", "PAYMENT_FAILED", "p3s4", "$reason")
S["Failed"] = {"Type": "Fail", "Error": "CheckoutFailed", "Cause": j("$exists($reason) ? $reason : 'failed'")}

asl = {"Comment": "Voltaj checkout saga: reserve stock, wait for the payment callback, write the order, publish OrderPlaced; "
                  "compensate on failure.", "QueryLanguage": "JSONata", "StartAt": "Init", "States": S}
json.dump(asl, open(sys.argv[1], "w"), indent=1, ensure_ascii=False)
print(len(S), "states")
