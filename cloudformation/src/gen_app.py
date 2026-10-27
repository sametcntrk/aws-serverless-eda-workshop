"""Generates cloudformation/app.json: the Voltaj application (Cognito, REST and WebSocket APIs, Lambda, Step Functions,
EventBridge, Pipes, SNS, SQS, SES, event source mappings) plus the learning functions that need the APIs.

Lambda code paths are local; `aws cloudformation package` uploads them. Run from the repository root:
    python3 cloudformation/src/gen_app.py cloudformation/app.json
"""
import json
import sys

R = {}          # resources
O = {}          # outputs


def sub(s, **kw):
    return {"Fn::Sub": [s, kw]} if kw else {"Fn::Sub": s}


def imp(stack_param, name):
    return {"Fn::ImportValue": {"Fn::Sub": "${" + stack_param + "}-" + name}}


def ref(x):
    return {"Ref": x}


def att(x, a):
    return {"Fn::GetAtt": [x, a]}


ACC, REG = "${AWS::AccountId}", "${AWS::Region}"
KEY = imp("Base", "KeyArn")
TABLES = {"CATALOG_TABLE": "voltaj-catalog", "CART_TABLE": "voltaj-cart", "STOCK_TABLE": "voltaj-stock",
          "IDEMPOTENCY_TABLE": "voltaj-idempotency", "COUNTERS_TABLE": "voltaj-counters", "WS_TABLE": "voltaj-ws-connections",
          "TRACE_TABLE": "voltaj-trace", "GUARD_TABLE": "voltaj-guard"}


def table_arn(name):
    return sub(f"arn:aws:dynamodb:{REG}:{ACC}:table/{name}")


def table_arns(*names):
    out = []
    for n in names:
        out += [table_arn(n), sub(f"arn:aws:dynamodb:{REG}:{ACC}:table/{n}/index/*")]
    return out


TRACE_STMTS = [{"Effect": "Allow", "Action": ["dynamodb:BatchWriteItem", "dynamodb:PutItem"], "Resource": table_arn("voltaj-trace")},
               {"Effect": "Allow", "Action": ["kms:Decrypt", "kms:GenerateDataKey", "kms:DescribeKey"], "Resource": KEY}]

# ------------------------------------------------------------------ parameters
P = {
    "Base": {"Type": "String", "Default": "voltaj-base"}, "Network": {"Type": "String", "Default": "voltaj-network"},
    "Data": {"Type": "String", "Default": "voltaj-data"}, "Integration": {"Type": "String", "Default": "voltaj-integration"},
    "Learning": {"Type": "String", "Default": "voltaj-learning"},
    "ShopDomain": {"Type": "String", "Default": "shop.tdsynnexlab.link"},
    "PayApiUrl": {"Type": "String", "Default": "https://pay.tdsynnexlab.link"},
    "MailDomain": {"Type": "String", "Default": "shop.tdsynnexlab.link"},
    "HostedZoneId": {"Type": "String", "Default": "Z03414782ECSLICW59USM"},
    "PaymentTimeout": {"Type": "Number", "Default": 120, "Description": "Seconds the saga waits for the payment webhook"},
    "CheckoutLimit": {"Type": "Number", "Default": 5, "Description": "Checkouts per minute per visitor"},
    "MskBootstrap": {"Type": "String", "Description": "Bootstrap brokers (SASL IAM) of MSK Serverless"},
    "EnableMskConsumers": {"Type": "String", "Default": "false", "AllowedValues": ["true", "false"]},
    "EnablePipe": {"Type": "String", "Default": "false", "AllowedValues": ["true", "false"]},
    "SmsOrigin": {"Type": "String", "Default": "", "Description": "Simulator origination phone number (End User Messaging)"},
    "SmsTo": {"Type": "String", "Default": "+14254147755"},
    "Personas": {"Type": "String", "Default": "[]", "NoEcho": True, "Description": "JSON [{username, password}] for the persona guard"},
    "DemoAdminEmail": {"Type": "String", "Default": "demo-admin@voltaj.shop"},
}
COND = {"MskConsumers": {"Fn::Equals": [ref("EnableMskConsumers"), "true"]}, "PipeOn": {"Fn::Equals": [ref("EnablePipe"), "true"]}}

# ------------------------------------------------------------------ layers
R["CommonLayer"] = {"Type": "AWS::Lambda::LayerVersion", "Properties": {"LayerName": "voltaj-common", "Content": "../app/layers/common",
                    "CompatibleRuntimes": ["python3.13"], "Description": "voltaj trace, api, guard helpers"}}
R["DepsLayer"] = {"Type": "AWS::Lambda::LayerVersion", "Properties": {"LayerName": "voltaj-deps", "Content": "../build/deps",
                  "CompatibleRuntimes": ["python3.13"], "Description": "pg8000, pika, kafka-python, MSK IAM signer"}}
R["PillowLayer"] = {"Type": "AWS::Lambda::LayerVersion", "Properties": {"LayerName": "voltaj-pillow", "Content": "../build/pillow",
                    "CompatibleRuntimes": ["python3.13"], "Description": "Pillow"}}
POWERTOOLS = sub(f"arn:aws:lambda:{REG}:017000801446:layer:AWSLambdaPowertoolsPythonV3-python313-x86_64:40")

WS_MGMT = sub("https://${WsApi}.execute-api.${AWS::Region}.amazonaws.com/prod")


def fn(name, code_dir, env=None, stmts=None, vpc=False, timeout=15, memory=512, layers=("common",), reserved=None, desc=""):
    """One function, its role (voltaj-fn-<name>) and log group."""
    lid = "Fn" + "".join(p.capitalize() for p in name.split("-"))
    role_stmts = list(TRACE_STMTS) + list(stmts or [])
    managed = ["arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole", "arn:aws:iam::aws:policy/AWSXRayDaemonWriteAccess"]
    if vpc:
        managed.append("arn:aws:iam::aws:policy/service-role/AWSLambdaVPCAccessExecutionRole")
    R[lid + "Role"] = {"Type": "AWS::IAM::Role", "Properties": {
        "RoleName": f"voltaj-fn-{name}",
        "AssumeRolePolicyDocument": {"Version": "2012-10-17", "Statement": [
            {"Effect": "Allow", "Principal": {"Service": "lambda.amazonaws.com"}, "Action": "sts:AssumeRole"}]},
        "ManagedPolicyArns": managed,
        "Policies": [{"PolicyName": "fn", "PolicyDocument": {"Version": "2012-10-17", "Statement": role_stmts}}]}}
    R[lid + "Logs"] = {"Type": "AWS::Logs::LogGroup", "Properties": {"LogGroupName": f"/aws/lambda/voltaj-{name}", "RetentionInDays": 14}}
    lay = {"common": ref("CommonLayer"), "deps": ref("DepsLayer"), "pillow": ref("PillowLayer"), "powertools": POWERTOOLS}
    e = {"TRACE_TABLE": "voltaj-trace", "GUARD_TABLE": "voltaj-guard", "POWERTOOLS_SERVICE_NAME": name, **(env or {})}
    if vpc:
        e["IN_VPC"] = "1"
    props = {"FunctionName": f"voltaj-{name}", "Description": desc, "Runtime": "python3.13", "Handler": "app.lambda_handler",
             "Code": f"../app/functions/{code_dir}", "Role": att(lid + "Role", "Arn"), "Timeout": timeout, "MemorySize": memory,
             "Architectures": ["x86_64"], "TracingConfig": {"Mode": "Active"},
             "Layers": [lay[x] for x in layers] + [POWERTOOLS], "Environment": {"Variables": e},
             "LoggingConfig": {"LogGroup": ref(lid + "Logs")}}
    if vpc:
        props["VpcConfig"] = {"SubnetIds": {"Fn::Split": [",", imp("Network", "AppSubnets")]},
                              "SecurityGroupIds": [imp("Network", "SgLambda")]}
    if reserved:
        props["ReservedConcurrentExecutions"] = reserved
    R[lid] = {"Type": "AWS::Lambda::Function", "Properties": props}
    return lid


def allow(actions, resource):
    return {"Effect": "Allow", "Action": actions if isinstance(actions, list) else [actions], "Resource": resource}


DDB_RW = ["dynamodb:GetItem", "dynamodb:PutItem", "dynamodb:UpdateItem", "dynamodb:DeleteItem", "dynamodb:Query", "dynamodb:Scan",
          "dynamodb:BatchGetItem", "dynamodb:BatchWriteItem", "dynamodb:ConditionCheckItem"]
GUARD_STMT = allow(["dynamodb:UpdateItem", "dynamodb:GetItem", "dynamodb:PutItem", "dynamodb:DeleteItem"], table_arn("voltaj-guard"))
SECRET = lambda n: sub(f"arn:aws:secretsmanager:{REG}:{ACC}:secret:{n}-*")  # noqa: E731

# ------------------------------------------------------------------ Cognito
R["UserPool"] = {"Type": "AWS::Cognito::UserPool", "Properties": {
    "UserPoolName": "voltaj-users", "UsernameAttributes": ["email"], "AutoVerifiedAttributes": ["email"],
    "MfaConfiguration": "OPTIONAL", "EnabledMfas": ["SOFTWARE_TOKEN_MFA"],
    "Policies": {"PasswordPolicy": {"MinimumLength": 10, "RequireLowercase": True, "RequireUppercase": True, "RequireNumbers": True,
                                    "RequireSymbols": False}},
    "Schema": [{"Name": "name", "AttributeDataType": "String", "Mutable": True, "Required": True},
               {"Name": "email", "AttributeDataType": "String", "Mutable": True, "Required": True}],
    "AccountRecoverySetting": {"RecoveryMechanisms": [{"Name": "verified_email", "Priority": 1}]},
    "UserPoolTier": "ESSENTIALS", "DeletionProtection": "INACTIVE"}}
R["UserPoolClient"] = {"Type": "AWS::Cognito::UserPoolClient", "Properties": {
    "UserPoolId": ref("UserPool"), "ClientName": "voltaj-spa", "GenerateSecret": False,
    "ExplicitAuthFlows": ["ALLOW_USER_PASSWORD_AUTH", "ALLOW_USER_SRP_AUTH", "ALLOW_REFRESH_TOKEN_AUTH"],
    "PreventUserExistenceErrors": "ENABLED", "AccessTokenValidity": 60, "IdTokenValidity": 60, "RefreshTokenValidity": 7,
    "TokenValidityUnits": {"AccessToken": "minutes", "IdToken": "minutes", "RefreshToken": "days"},
    "EnableTokenRevocation": True}}
R["AdminsGroup"] = {"Type": "AWS::Cognito::UserPoolGroup", "Properties": {"UserPoolId": ref("UserPool"), "GroupName": "admins",
                    "Description": "Back office. The admin APIs check this group claim."}}

# ------------------------------------------------------------------ SQS (KMS) and SNS
def queue(lid, name, vis=30, dlq=None, max_receive=3):
    props = {"QueueName": name, "KmsMasterKeyId": KEY, "VisibilityTimeout": vis, "MessageRetentionPeriod": 345600}
    if dlq:
        props["RedrivePolicy"] = {"deadLetterTargetArn": att(dlq, "Arn"), "maxReceiveCount": max_receive}
    R[lid] = {"Type": "AWS::SQS::Queue", "Properties": props}


queue("RuleDlq", "voltaj-rule-dlq")
queue("OrderBufferDlq", "voltaj-order-buffer-dlq")
queue("OrderBuffer", "voltaj-order-buffer", vis=60, dlq="OrderBufferDlq", max_receive=5)
queue("EmailDlq", "voltaj-email-dlq")
queue("EmailQueue", "voltaj-email", vis=20, dlq="EmailDlq", max_receive=3)
queue("SmsDlq", "voltaj-sms-dlq")
queue("SmsQueue", "voltaj-sms", vis=30, dlq="SmsDlq", max_receive=3)
queue("BackofficeQueue", "voltaj-backoffice", vis=30)
R["Topic"] = {"Type": "AWS::SNS::Topic", "Properties": {"TopicName": "voltaj-order-notifications", "KmsMasterKeyId": KEY}}
R["TopicPolicy"] = {"Type": "AWS::SNS::TopicPolicy", "Properties": {"Topics": [ref("Topic")], "PolicyDocument": {
    "Version": "2012-10-17", "Statement": [{"Effect": "Allow", "Principal": {"Service": "events.amazonaws.com"}, "Action": "sns:Publish",
                                            "Resource": ref("Topic"), "Condition": {"StringEquals": {"aws:SourceAccount": {"Ref": "AWS::AccountId"}}}}]}}}
for lid, q, flt in [("SubEmail", "EmailQueue", None), ("SubSms", "SmsQueue", {"detail": {"smsOptIn": [True]}}),
                    ("SubBackoffice", "BackofficeQueue", None)]:
    props = {"TopicArn": ref("Topic"), "Protocol": "sqs", "Endpoint": att(q, "Arn"), "RawMessageDelivery": True}
    if flt:
        props.update(FilterPolicy=flt, FilterPolicyScope="MessageBody")
    R[lid] = {"Type": "AWS::SNS::Subscription", "Properties": props}
R["QueuePolicy"] = {"Type": "AWS::SQS::QueuePolicy", "Properties": {
    "Queues": [ref(q) for q in ("EmailQueue", "SmsQueue", "BackofficeQueue", "OrderBuffer", "RuleDlq")],
    "PolicyDocument": {"Version": "2012-10-17", "Statement": [
        {"Effect": "Allow", "Principal": {"Service": "sns.amazonaws.com"}, "Action": "sqs:SendMessage",
         "Resource": [att(q, "Arn") for q in ("EmailQueue", "SmsQueue", "BackofficeQueue")], "Condition": {"ArnEquals": {"aws:SourceArn": ref("Topic")}}},
        {"Effect": "Allow", "Principal": {"Service": "events.amazonaws.com"}, "Action": "sqs:SendMessage",
         "Resource": [att("OrderBuffer", "Arn"), att("RuleDlq", "Arn")], "Condition": {"StringEquals": {"aws:SourceAccount": {"Ref": "AWS::AccountId"}}}}]}}}

# ------------------------------------------------------------------ EventBridge
R["Bus"] = {"Type": "AWS::Events::EventBus", "Properties": {"Name": "voltaj-commerce"}}
R["Archive"] = {"Type": "AWS::Events::Archive", "Properties": {"ArchiveName": "voltaj-commerce-archive", "SourceArn": att("Bus", "Arn"),
                "RetentionDays": 7, "Description": "Every event on the commerce bus, for replay"}}
R["Discoverer"] = {"Type": "AWS::EventSchemas::Discoverer", "Properties": {"SourceArn": att("Bus", "Arn"),
                   "Description": "Schema discovery on the commerce bus"}}
R["EventLog"] = {"Type": "AWS::Logs::LogGroup", "Properties": {"LogGroupName": "/aws/events/voltaj-commerce", "RetentionInDays": 3}}
R["EventLogPolicy"] = {"Type": "AWS::Logs::ResourcePolicy", "Properties": {"PolicyName": "voltaj-events-to-logs", "PolicyDocument": sub(
    json.dumps({"Version": "2012-10-17", "Statement": [{"Effect": "Allow", "Principal": {"Service": ["events.amazonaws.com", "delivery.logs.amazonaws.com"]},
               "Action": ["logs:CreateLogStream", "logs:PutLogEvents"], "Resource": "${EventLog.Arn}"}]}))}}
RETRY = {"MaximumRetryAttempts": 8, "MaximumEventAgeInSeconds": 3600}
DLQ = {"Arn": att("RuleDlq", "Arn")}


def rule(lid, name, pattern, targets, bus=True, desc=""):
    R[lid] = {"Type": "AWS::Events::Rule", "Properties": {"Name": name, "Description": desc, "State": "ENABLED", "EventPattern": pattern,
              "Targets": targets, **({"EventBusName": ref("Bus")} if bus else {})}}


rule("RuleNotify", "order-placed-notify", {"source": ["com.shop.checkout", "com.shop.burst"], "detail-type": ["OrderPlaced"]},
     [{"Id": "sns", "Arn": ref("Topic"), "RetryPolicy": RETRY, "DeadLetterConfig": DLQ}], desc="OrderPlaced → notification topic")
rule("RuleFulfil", "order-placed-fulfil", {"source": ["com.shop.checkout", "com.shop.burst"], "detail-type": ["OrderPlaced"]},
     [{"Id": "buffer", "Arn": att("OrderBuffer", "Arn"), "RetryPolicy": RETRY, "DeadLetterConfig": DLQ}], desc="OrderPlaced → order buffer")
rule("RuleShipment", "shipment-notify", {"source": ["com.shop.3pl"], "detail-type": ["ShipmentDispatched"]},
     [{"Id": "sns", "Arn": ref("Topic"), "RetryPolicy": RETRY, "DeadLetterConfig": DLQ}], desc="ShipmentDispatched → notification topic")
R["RuleEventLog"] = {"Type": "AWS::Events::Rule", "Properties": {
    "Name": "commerce-event-log", "Description": "Learning layer: copy every event to CloudWatch Logs", "EventBusName": ref("Bus"),
    "State": "ENABLED", "EventPattern": {"source": [{"prefix": ""}]},
    "Targets": [{"Id": "logs", "Arn": att("EventLog", "Arn"), "RetryPolicy": RETRY}]}}

# ------------------------------------------------------------------ functions
COMMON_TABLE_STMTS = [allow(DDB_RW, table_arns("voltaj-catalog", "voltaj-stock", "voltaj-counters"))]
fn("product", "product", desc="Search, product detail, admin writes, upload URLs", env={
    **{k: v for k, v in TABLES.items() if k in ("CATALOG_TABLE", "STOCK_TABLE", "COUNTERS_TABLE")},
    "UPLOADS_BUCKET": imp("Data", "UploadsBucket"), "AOSS_ENDPOINT": imp("Data", "CollectionEndpoint"),
    "DEMO_ADMIN_EMAIL": ref("DemoAdminEmail")},
   stmts=COMMON_TABLE_STMTS + [GUARD_STMT, allow(["aoss:APIAccessAll"], imp("Data", "CollectionArn")),
                               allow(["s3:PutObject"], sub("arn:aws:s3:::${B}/*", B=imp("Data", "UploadsBucket")))])
fn("cart", "cart", desc="Cart lines in DynamoDB", env={k: v for k, v in TABLES.items() if k in ("CART_TABLE", "CATALOG_TABLE")},
   stmts=[allow(DDB_RW, table_arns("voltaj-cart", "voltaj-catalog"))])
fn("webhook", "webhook", desc="Payment webhook: HMAC check, idempotency, SendTask*", env={
    "IDEMPOTENCY_TABLE": "voltaj-idempotency", "PAY_SECRET_ARN": imp("Base", "PaySecretArn")},
   stmts=[allow(DDB_RW, table_arns("voltaj-idempotency")), allow(["states:SendTaskSuccess", "states:SendTaskFailure"], "*"),
          allow("secretsmanager:GetSecretValue", imp("Base", "PaySecretArn"))])
fn("wsauth", "wsauth", desc="WebSocket $connect authorizer (Cognito GetUser)")
fn("ws", "ws", desc="WebSocket connections and the checkout result push", env={"WS_TABLE": "voltaj-ws-connections", "WS_MANAGEMENT_URL": WS_MGMT},
   stmts=[allow(DDB_RW, table_arns("voltaj-ws-connections")), allow("execute-api:ManageConnections", sub(f"arn:aws:execute-api:{REG}:{ACC}:${{WsApi}}/*"))])
fn("payment", "payment", vpc=True, desc="Saves the task token, creates the payment at the provider (NAT)", env={
    "IDEMPOTENCY_TABLE": "voltaj-idempotency", "PAY_SECRET_ARN": imp("Base", "PaySecretArn"), "PAY_API_URL": ref("PayApiUrl"),
    "SHOP_URL": sub("https://${ShopDomain}"), "NAT_IPS": imp("Network", "NatIps")},
   stmts=[allow(DDB_RW, table_arns("voltaj-idempotency")), allow("secretsmanager:GetSecretValue", imp("Base", "PaySecretArn"))])
fn("order", "order", vpc=True, layers=("common", "deps"), timeout=30, desc="Order write to Aurora through RDS Proxy (IAM)", env={
    "PROXY_ENDPOINT": imp("Data", "ProxyEndpoint"), "CART_TABLE": "voltaj-cart", "ADMIN_SECRET_ARN": imp("Data", "AuroraAdminSecretArn"),
    "ORDER_SECRET_ARN": imp("Base", "OrderSvcSecretArn")},
   stmts=[allow("rds-db:connect", [sub(f"arn:aws:rds-db:{REG}:{ACC}:dbuser:${{P}}/*", P=imp("Data", "ProxyResourceId"))]),
          allow(DDB_RW, table_arns("voltaj-cart")),
          allow("secretsmanager:GetSecretValue", [imp("Data", "AuroraAdminSecretArn"), imp("Base", "OrderSvcSecretArn")])])
fn("fulfillment", "fulfillment", vpc=True, layers=("common", "deps"), timeout=30, desc="Order buffer → RabbitMQ FulfillOrder", env={
    "IDEMPOTENCY_TABLE": "voltaj-idempotency", "AMQP_ENDPOINT": imp("Integration", "AmqpEndpoint"),
    "MQ_SECRET_ARN": imp("Base", "MqSecretArn"), "THREEPL_SECRET_ARN": imp("Base", "ThreePlSecretArn")},
   stmts=[allow(DDB_RW, table_arns("voltaj-idempotency")),
          allow("secretsmanager:GetSecretValue", [imp("Base", "MqSecretArn"), imp("Base", "ThreePlSecretArn")]),
          allow(["sqs:ReceiveMessage", "sqs:DeleteMessage", "sqs:GetQueueAttributes", "sqs:ChangeMessageVisibility"], att("OrderBuffer", "Arn"))])
MSK_STMTS = [allow(["kafka-cluster:Connect", "kafka-cluster:DescribeCluster", "kafka-cluster:WriteData", "kafka-cluster:ReadData",
                    "kafka-cluster:DescribeTopic", "kafka-cluster:CreateTopic", "kafka-cluster:DescribeGroup", "kafka-cluster:AlterGroup"],
                   [imp("Integration", "MskArn"), sub(f"arn:aws:kafka:{REG}:{ACC}:topic/voltaj-msk/*"),
                    sub(f"arn:aws:kafka:{REG}:{ACC}:group/voltaj-msk/*")]),
             allow(["kafka:DescribeClusterV2", "kafka:GetBootstrapBrokers", "kafka:DescribeCluster", "kafka:ListScramSecrets",
                    "ec2:CreateNetworkInterface", "ec2:DescribeNetworkInterfaces", "ec2:DescribeVpcs", "ec2:DeleteNetworkInterface",
                    "ec2:DescribeSubnets", "ec2:DescribeSecurityGroups"], "*")]
fn("producer", "producer", vpc=True, layers=("common", "deps"), timeout=30, desc="Clickstream and commerce log → MSK Serverless (IAM)",
   env={"MSK_BOOTSTRAP": ref("MskBootstrap")}, stmts=MSK_STMTS + [GUARD_STMT])
fn("counters", "counters", desc="MSK consumer group counters → DynamoDB ADD", env={"COUNTERS_TABLE": "voltaj-counters"},
   stmts=MSK_STMTS + [allow(DDB_RW, table_arns("voltaj-counters"))])
fn("archive", "archive", desc="MSK consumer group archive → S3 data lake", env={"LAKE_BUCKET": imp("Data", "LakeBucket")},
   stmts=MSK_STMTS + [allow(["s3:PutObject"], sub("arn:aws:s3:::${B}/*", B=imp("Data", "LakeBucket")))])
fn("email", "email", desc="SQS email → SESv2 SendEmail (template)", env={
    "IDEMPOTENCY_TABLE": "voltaj-idempotency", "MAIL_FROM": sub("Voltaj <orders@${MailDomain}>"), "CONFIG_SET": "voltaj-shop-mail"},
   stmts=[allow(DDB_RW, table_arns("voltaj-idempotency")), GUARD_STMT, allow(["ses:SendEmail", "ses:SendTemplatedEmail"], "*"),
          allow(["sqs:ReceiveMessage", "sqs:DeleteMessage", "sqs:GetQueueAttributes", "sqs:ChangeMessageVisibility"], att("EmailQueue", "Arn"))])
fn("sms", "sms", desc="SQS sms → End User Messaging (simulator)", env={"IDEMPOTENCY_TABLE": "voltaj-idempotency", "SMS_ORIGIN": ref("SmsOrigin"),
                                                                      "SMS_TO": ref("SmsTo")},
   stmts=[allow(DDB_RW, table_arns("voltaj-idempotency")), allow(["sms-voice:SendTextMessage"], "*"),
          allow(["sqs:ReceiveMessage", "sqs:DeleteMessage", "sqs:GetQueueAttributes", "sqs:ChangeMessageVisibility"], att("SmsQueue", "Arn"))])
fn("resize", "resize", layers=("common", "pillow"), memory=1024, timeout=30, desc="S3 upload → WebP sizes in the web bucket",
   env={"WEB_BUCKET": imp("Data", "WebBucket")},
   stmts=[allow(["s3:GetObject"], sub("arn:aws:s3:::${B}/*", B=imp("Data", "UploadsBucket"))),
          allow(["s3:PutObject"], sub("arn:aws:s3:::${B}/images/*", B=imp("Data", "WebBucket")))])
fn("tracepush", "tracepush", desc="Learning: trace stream → WebSocket push", env={"WS_TABLE": "voltaj-ws-connections", "WS_MANAGEMENT_URL": WS_MGMT},
   stmts=[allow(DDB_RW, table_arns("voltaj-ws-connections")), allow("execute-api:ManageConnections", sub(f"arn:aws:execute-api:{REG}:{ACC}:${{WsApi}}/*")),
          allow(["dynamodb:GetRecords", "dynamodb:GetShardIterator", "dynamodb:DescribeStream", "dynamodb:ListStreams"],
                imp("Learning", "TraceStreamArn"))])
fn("bustap", "bustap", desc="Learning: commerce bus events → trace entries for steps without code")
fn("learn", "learn", timeout=30, memory=1024, desc="Learning API: lessons, reports, experiments", env={
    **TABLES, "BUS_NAME": "voltaj-commerce", "EVENT_LOG_GROUP": "/aws/events/voltaj-commerce", "STATE_MACHINE_ARN": ref("Saga"),
    "LAKE_BUCKET": imp("Data", "LakeBucket"), "WEB_BUCKET": imp("Data", "WebBucket"), "USER_POOL_ID": ref("UserPool"),
    "AOSS_ENDPOINT": imp("Data", "CollectionEndpoint"), "ARCHIVE_ARN": att("Archive", "Arn"), "MSK_CLUSTER_NAME": "voltaj-msk",
    "DLQS": sub(json.dumps({"email-dlq": "${EmailDlq}", "sms-dlq": "${SmsDlq}", "order-buffer-dlq": "${OrderBufferDlq}", "rule-dlq": "${RuleDlq}"})),
    "QUEUES": sub(json.dumps({"order-buffer": "${OrderBuffer}", "email": "${EmailQueue}", "sms": "${SmsQueue}", "backoffice": "${BackofficeQueue}"})),
    "ORDER_FN": "voltaj-order", "FULFILLMENT_FN": "voltaj-fulfillment", "PRODUCER_FN": "voltaj-producer", "PERSONAS": ref("Personas"),
    "REPLAY_RULE_ARNS": att("RuleEventLog", "Arn")},
   stmts=[allow(DDB_RW, table_arns(*TABLES.values())), allow("aoss:APIAccessAll", imp("Data", "CollectionArn")),
          allow(["states:ListExecutions", "states:DescribeExecution", "states:GetExecutionHistory"], "*"),
          allow(["logs:FilterLogEvents"], "*"), allow(["events:ListRules", "events:PutEvents", "events:StartReplay", "events:DescribeEventBus"], "*"),
          allow(["s3:ListBucket", "s3:GetObject"], [sub("arn:aws:s3:::${B}", B=imp("Data", "LakeBucket")), sub("arn:aws:s3:::${B}/*", B=imp("Data", "LakeBucket")),
                                                  sub("arn:aws:s3:::${B}", B=imp("Data", "WebBucket")), sub("arn:aws:s3:::${B}/*", B=imp("Data", "WebBucket"))]),
          allow(["sqs:GetQueueAttributes", "sqs:ReceiveMessage", "sqs:StartMessageMoveTask", "sqs:ListMessageMoveTasks", "sqs:DeleteMessage",
                 "sqs:SendMessage"], sub(f"arn:aws:sqs:{REG}:{ACC}:voltaj-*")),
          allow(["cloudwatch:GetMetricData"], "*"),
          allow(["cognito-idp:ListUsers", "cognito-idp:ListUsersInGroup", "cognito-idp:AdminGetUser", "cognito-idp:AdminSetUserPassword",
                 "cognito-idp:AdminEnableUser"], att("UserPool", "Arn")),
          allow("lambda:InvokeFunction", [sub(f"arn:aws:lambda:{REG}:{ACC}:function:voltaj-{n}") for n in ("order", "fulfillment", "producer")]),
          allow(["schemas:ListSchemas", "schemas:DescribeSchema"], "*"), GUARD_STMT])

# Trigger permissions and mappings
R["FnBustapRule"] = {"Type": "AWS::Events::Rule", "Properties": {
    "Name": "commerce-trace-tap", "Description": "Learning layer: trace entries for steps that run without code", "EventBusName": ref("Bus"),
    "State": "ENABLED", "EventPattern": {"source": [{"prefix": "com.shop"}]}, "Targets": [{"Id": "tap", "Arn": att("FnBustap", "Arn")}]}}
R["FnBustapPerm"] = {"Type": "AWS::Lambda::Permission", "Properties": {"FunctionName": ref("FnBustap"), "Action": "lambda:InvokeFunction",
                     "Principal": "events.amazonaws.com", "SourceArn": att("FnBustapRule", "Arn")}}
rule("RuleCommerceLog", "commerce-log", {"source": ["com.shop.checkout"], "detail-type": ["OrderPlaced"]},
     [{"Id": "producer", "Arn": att("FnProducer", "Arn"), "RetryPolicy": RETRY, "DeadLetterConfig": DLQ}], desc="OrderPlaced → MSK event log")
R["FnProducerPerm"] = {"Type": "AWS::Lambda::Permission", "Properties": {"FunctionName": ref("FnProducer"), "Action": "lambda:InvokeFunction",
                       "Principal": "events.amazonaws.com", "SourceArn": att("RuleCommerceLog", "Arn")}}
rule("RuleImage", "image-uploaded", {"source": ["aws.s3"], "detail-type": ["Object Created"],
                                     "detail": {"bucket": {"name": [imp("Data", "UploadsBucket")]}}},
     [{"Id": "resize", "Arn": att("FnResize", "Arn"), "RetryPolicy": RETRY, "DeadLetterConfig": DLQ}], bus=False, desc="S3 upload → resize")
R["FnResizePerm"] = {"Type": "AWS::Lambda::Permission", "Properties": {"FunctionName": ref("FnResize"), "Action": "lambda:InvokeFunction",
                     "Principal": "events.amazonaws.com", "SourceArn": att("RuleImage", "Arn")}}
R["PersonaGuardRule"] = {"Type": "AWS::Events::Rule", "Properties": {"Name": "voltaj-persona-guard", "ScheduleExpression": "rate(15 minutes)",
                         "State": "ENABLED", "Targets": [{"Id": "learn", "Arn": att("FnLearn", "Arn"), "Input": json.dumps({"action": "persona-guard"})}]}}
R["FnLearnSchedPerm"] = {"Type": "AWS::Lambda::Permission", "Properties": {"FunctionName": ref("FnLearn"), "Action": "lambda:InvokeFunction",
                         "Principal": "events.amazonaws.com", "SourceArn": att("PersonaGuardRule", "Arn")}}
for lid, fname, q, batch in [("EsmFulfil", "FnFulfillment", "OrderBuffer", 10), ("EsmEmail", "FnEmail", "EmailQueue", 5),
                             ("EsmSms", "FnSms", "SmsQueue", 5)]:
    R[lid] = {"Type": "AWS::Lambda::EventSourceMapping", "Properties": {"FunctionName": ref(fname), "EventSourceArn": att(q, "Arn"),
              "BatchSize": batch, "MaximumBatchingWindowInSeconds": 0, "FunctionResponseTypes": ["ReportBatchItemFailures"]}}
R["EsmTrace"] = {"Type": "AWS::Lambda::EventSourceMapping", "Properties": {"FunctionName": ref("FnTracepush"),
                 "EventSourceArn": imp("Learning", "TraceStreamArn"), "StartingPosition": "LATEST", "BatchSize": 100,
                 "MaximumBatchingWindowInSeconds": 0, "ParallelizationFactor": 4, "MaximumRetryAttempts": 2}}
for lid, fname, topic, group in [("EsmArchive", "FnArchive", "clickstream", "archive"), ("EsmArchiveCommerce", "FnArchive", "commerce-events", "archive-commerce"),
                                 ("EsmCounters", "FnCounters", "clickstream", "counters")]:
    R[lid] = {"Type": "AWS::Lambda::EventSourceMapping", "Condition": "MskConsumers", "Properties": {
        "FunctionName": ref(fname), "EventSourceArn": imp("Integration", "MskArn"), "Topics": [topic], "StartingPosition": "LATEST",
        "BatchSize": 300, "MaximumBatchingWindowInSeconds": 5, "AmazonManagedKafkaEventSourceConfig": {"ConsumerGroupId": group},
        "ProvisionedPollerConfig": {"MinimumPollers": 1, "MaximumPollers": 2}}}

# ------------------------------------------------------------------ Step Functions
R["SagaLogs"] = {"Type": "AWS::Logs::LogGroup", "Properties": {"LogGroupName": "/aws/vendedlogs/states/voltaj-checkout", "RetentionInDays": 14}}
R["SagaRole"] = {"Type": "AWS::IAM::Role", "Properties": {
    "RoleName": "voltaj-sfn-checkout",
    "AssumeRolePolicyDocument": {"Version": "2012-10-17", "Statement": [{"Effect": "Allow", "Principal": {"Service": "states.amazonaws.com"},
                                                                          "Action": "sts:AssumeRole"}]},
    "Policies": [{"PolicyName": "saga", "PolicyDocument": {"Version": "2012-10-17", "Statement": [
        allow(["dynamodb:Query", "dynamodb:PutItem", "dynamodb:UpdateItem", "dynamodb:ConditionCheckItem"],
              table_arns("voltaj-cart", "voltaj-stock", "voltaj-trace", "voltaj-guard")),
        allow(["kms:Decrypt", "kms:GenerateDataKey"], KEY),
        allow("lambda:InvokeFunction", [att(f, "Arn") for f in ("FnPayment", "FnOrder", "FnWs")]),
        allow("events:PutEvents", att("Bus", "Arn")),
        allow(["logs:CreateLogDelivery", "logs:GetLogDelivery", "logs:UpdateLogDelivery", "logs:DeleteLogDelivery", "logs:ListLogDeliveries",
               "logs:PutResourcePolicy", "logs:DescribeResourcePolicies", "logs:DescribeLogGroups"], "*"),
        allow(["xray:PutTraceSegments", "xray:PutTelemetryRecords", "xray:GetSamplingRules", "xray:GetSamplingTargets"], "*")]}}]}}
R["Saga"] = {"Type": "AWS::StepFunctions::StateMachine", "Properties": {
    "StateMachineName": "voltaj-checkout", "StateMachineType": "STANDARD", "RoleArn": att("SagaRole", "Arn"),
    "DefinitionS3Location": "../app/statemachine/checkout.asl.json",
    "DefinitionSubstitutions": {"TraceTable": "voltaj-trace", "CartTable": "voltaj-cart", "StockTable": "voltaj-stock", "GuardTable": "voltaj-guard",
                                "BusName": ref("Bus"), "PaymentFn": att("FnPayment", "Arn"), "OrderFn": att("FnOrder", "Arn"),
                                "WsFn": att("FnWs", "Arn"), "PaymentTimeout": ref("PaymentTimeout"), "CheckoutLimit": ref("CheckoutLimit")},
    "LoggingConfiguration": {"Level": "ERROR", "IncludeExecutionData": True,
                             "Destinations": [{"CloudWatchLogsLogGroup": {"LogGroupArn": att("SagaLogs", "Arn")}}]},
    "TracingConfiguration": {"Enabled": True}}}

# ------------------------------------------------------------------ REST API
R["Api"] = {"Type": "AWS::ApiGateway::RestApi", "Properties": {"Name": "voltaj-api", "EndpointConfiguration": {"Types": ["REGIONAL"]},
            "Description": "Voltaj REST API behind CloudFront (/api/* → /prod/*)"}}
R["ApiAuthorizer"] = {"Type": "AWS::ApiGateway::Authorizer", "Properties": {"Name": "cognito", "RestApiId": ref("Api"), "Type": "COGNITO_USER_POOLS",
                      "IdentitySource": "method.request.header.Authorization", "ProviderARNs": [att("UserPool", "Arn")]}}
R["ApiBodyValidator"] = {"Type": "AWS::ApiGateway::RequestValidator", "Properties": {"RestApiId": ref("Api"), "Name": "body",
                         "ValidateRequestBody": True, "ValidateRequestParameters": True}}
R["ModelCartItem"] = {"Type": "AWS::ApiGateway::Model", "Properties": {"RestApiId": ref("Api"), "Name": "CartItem", "ContentType": "application/json",
                      "Schema": {"$schema": "http://json-schema.org/draft-04/schema#", "type": "object", "required": ["sku", "qty"],
                                 "properties": {"sku": {"type": "string", "pattern": "^[A-Za-z0-9-]{3,40}$"}, "qty": {"type": "integer", "minimum": 1, "maximum": 5}}}}}
RES = {}


def resource(path):
    if path in RES:
        return RES[path]
    parent_path, _, part = path.rpartition("/")
    parent = att("Api", "RootResourceId") if not parent_path else ref(resource(parent_path))
    lid = "Res" + "".join(c for c in path.title() if c.isalnum())
    R[lid] = {"Type": "AWS::ApiGateway::Resource", "Properties": {"RestApiId": ref("Api"), "ParentId": parent, "PathPart": part}}
    RES[path] = lid
    return lid


METHODS = []


def method(verb, path, fn_lid, auth=False, model=None):
    lid = "M" + verb.title() + "".join(c for c in path.title() if c.isalnum())
    props = {"RestApiId": ref("Api"), "ResourceId": ref(resource(path)), "HttpMethod": verb,
             "AuthorizationType": "COGNITO_USER_POOLS" if auth else "NONE",
             "Integration": {"Type": "AWS_PROXY", "IntegrationHttpMethod": "POST",
                             "Uri": sub(f"arn:aws:apigateway:{REG}:lambda:path/2015-03-31/functions/${{F}}/invocations", F=att(fn_lid, "Arn"))}}
    if auth:
        props["AuthorizerId"] = ref("ApiAuthorizer")
    if model:
        props.update(RequestValidatorId=ref("ApiBodyValidator"), RequestModels={"application/json": model})
    R[lid] = {"Type": "AWS::ApiGateway::Method", "Properties": props}
    METHODS.append(lid)


for verb, path, f, a, m in [
        ("GET", "/products", "FnProduct", False, None), ("GET", "/products/suggest", "FnProduct", False, None),
        ("GET", "/products/popular", "FnProduct", False, None), ("GET", "/products/{sku}", "FnProduct", False, None),
        ("GET", "/cart", "FnCart", True, None), ("POST", "/cart/items", "FnCart", True, "CartItem"),
        ("DELETE", "/cart/items/{sku}", "FnCart", True, None), ("GET", "/orders", "FnOrder", True, None),
        ("POST", "/webhooks/payment", "FnWebhook", False, None), ("POST", "/events", "FnProducer", False, None),
        ("PUT", "/admin/products/{sku}", "FnProduct", True, None), ("POST", "/admin/images/upload-url", "FnProduct", True, None),
        ("ANY", "/learn/{proxy+}", "FnLearn", False, None)]:
    method(verb, path, f, a, m)
for f in ("FnProduct", "FnCart", "FnOrder", "FnWebhook", "FnProducer", "FnLearn"):
    R[f + "ApiPerm"] = {"Type": "AWS::Lambda::Permission", "Properties": {"FunctionName": ref(f), "Action": "lambda:InvokeFunction",
                        "Principal": "apigateway.amazonaws.com", "SourceArn": sub(f"arn:aws:execute-api:{REG}:{ACC}:${{Api}}/*")}}
# The learn routes are mounted under /learn/{proxy+}, but the function routes by the resource /learn/<name>.
R["FnLearn"]["Properties"]["Environment"]["Variables"]["LEARN_PROXY"] = "1"

# Checkout: direct integration with Step Functions (no Lambda)
R["ApiSfnRole"] = {"Type": "AWS::IAM::Role", "Properties": {
    "RoleName": "voltaj-apigw-sfn",
    "AssumeRolePolicyDocument": {"Version": "2012-10-17", "Statement": [{"Effect": "Allow", "Principal": {"Service": "apigateway.amazonaws.com"},
                                                                          "Action": "sts:AssumeRole"}]},
    "Policies": [{"PolicyName": "start", "PolicyDocument": {"Version": "2012-10-17", "Statement": [allow("states:StartExecution", ref("Saga"))]}}]}}
CHECKOUT_TEMPLATE = r"""#set($oid = $input.params('Idempotency-Key'))
#set($c = $context.authorizer.claims)
#set($name = $util.escapeJavaScript($c.name).replace("\'", "’"))
{"stateMachineArn": "${Saga}", "name": "$oid",
 "input": "{\"orderId\": \"$oid\", \"customerId\": \"$c.sub\", \"name\": \"$name\", \"email\": \"$c.email\", \"vid\": \"$util.escapeJavaScript($input.params('X-Vid'))\", \"cid\": \"$util.escapeJavaScript($input.params('X-Cid'))\", \"smsOptIn\": \"$input.path('$.smsOptIn')\"}"}"""
R["MPostCheckout"] = {"Type": "AWS::ApiGateway::Method", "Properties": {
    "RestApiId": ref("Api"), "ResourceId": ref(resource("/checkout")), "HttpMethod": "POST", "AuthorizationType": "COGNITO_USER_POOLS",
    "AuthorizerId": ref("ApiAuthorizer"), "RequestValidatorId": ref("ApiBodyValidator"),
    "RequestParameters": {"method.request.header.Idempotency-Key": True},
    "Integration": {"Type": "AWS", "IntegrationHttpMethod": "POST", "Uri": sub(f"arn:aws:apigateway:{REG}:states:action/StartExecution"),
                    "Credentials": att("ApiSfnRole", "Arn"), "PassthroughBehavior": "NEVER",
                    "RequestTemplates": {"application/json": sub(CHECKOUT_TEMPLATE)},
                    "IntegrationResponses": [
                        {"StatusCode": "202", "ResponseTemplates": {"application/json":
                            "{\"ok\": true, \"data\": {\"orderId\": \"$input.params('Idempotency-Key')\", \"executionArn\": \"$input.path('$.executionArn')\", "
                            "\"startDate\": \"$input.path('$.startDate')\"}, \"cid\": \"$input.params('X-Cid')\", \"trace\": []}"}},
                        {"StatusCode": "409", "SelectionPattern": "4\\d{2}", "ResponseTemplates": {"application/json":
                            "{\"ok\": false, \"error\": \"Step Functions refused the start: $util.escapeJavaScript($input.path('$.message'))\", \"trace\": []}"}}]},
    "MethodResponses": [{"StatusCode": "202"}, {"StatusCode": "409"}]}}
METHODS.append("MPostCheckout")
api_hash = __import__("hashlib").md5(json.dumps([R[m] for m in METHODS], sort_keys=True, default=str).encode()).hexdigest()[:8]
R["ApiDeployment" + api_hash] = {"Type": "AWS::ApiGateway::Deployment", "DependsOn": METHODS, "Properties": {"RestApiId": ref("Api")}}
R["ApiLogs"] = {"Type": "AWS::Logs::LogGroup", "Properties": {"LogGroupName": "/aws/apigateway/voltaj-api", "RetentionInDays": 14}}
R["ApiStage"] = {"Type": "AWS::ApiGateway::Stage", "Properties": {
    "RestApiId": ref("Api"), "StageName": "prod", "DeploymentId": ref("ApiDeployment" + api_hash), "TracingEnabled": True,
    "MethodSettings": [{"ResourcePath": "/*", "HttpMethod": "*", "ThrottlingRateLimit": 100, "ThrottlingBurstLimit": 200, "MetricsEnabled": True}]}}
R["UsagePlan"] = {"Type": "AWS::ApiGateway::UsagePlan", "Properties": {"UsagePlanName": "voltaj-default",
                  "ApiStages": [{"ApiId": ref("Api"), "Stage": ref("ApiStage")}], "Throttle": {"RateLimit": 100, "BurstLimit": 200},
                  "Quota": {"Limit": 200000, "Period": "DAY"}}}

# ------------------------------------------------------------------ WebSocket API
R["WsApi"] = {"Type": "AWS::ApiGatewayV2::Api", "Properties": {"Name": "voltaj-ws", "ProtocolType": "WEBSOCKET",
              "RouteSelectionExpression": "$request.body.action"}}
R["WsAuthorizer"] = {"Type": "AWS::ApiGatewayV2::Authorizer", "Properties": {
    "ApiId": ref("WsApi"), "Name": "cognito-token", "AuthorizerType": "REQUEST", "IdentitySource": ["route.request.querystring.token"],
    "AuthorizerUri": sub(f"arn:aws:apigateway:{REG}:lambda:path/2015-03-31/functions/${{FnWsauth.Arn}}/invocations")}}
R["WsInteg"] = {"Type": "AWS::ApiGatewayV2::Integration", "Properties": {"ApiId": ref("WsApi"), "IntegrationType": "AWS_PROXY",
                "IntegrationUri": sub(f"arn:aws:apigateway:{REG}:lambda:path/2015-03-31/functions/${{FnWs.Arn}}/invocations")}}
WS_ROUTES = []
for key, lid in [("$connect", "WsRouteConnect"), ("$disconnect", "WsRouteDisconnect"), ("$default", "WsRouteDefault")]:
    props = {"ApiId": ref("WsApi"), "RouteKey": key, "Target": sub("integrations/${WsInteg}")}
    if key == "$connect":
        props.update(AuthorizationType="CUSTOM", AuthorizerId=ref("WsAuthorizer"))
    R[lid] = {"Type": "AWS::ApiGatewayV2::Route", "Properties": props}
    WS_ROUTES.append(lid)
R["WsDeployment" + api_hash] = {"Type": "AWS::ApiGatewayV2::Deployment", "DependsOn": WS_ROUTES, "Properties": {"ApiId": ref("WsApi")}}
R["WsStage"] = {"Type": "AWS::ApiGatewayV2::Stage", "Properties": {"ApiId": ref("WsApi"), "StageName": "prod",
                "DeploymentId": ref("WsDeployment" + api_hash), "DefaultRouteSettings": {"ThrottlingRateLimit": 50, "ThrottlingBurstLimit": 100}}}
for f, src in [("FnWs", "*"), ("FnWsauth", "authorizers/*")]:
    R[f + "WsPerm"] = {"Type": "AWS::Lambda::Permission", "Properties": {"FunctionName": ref(f), "Action": "lambda:InvokeFunction",
                       "Principal": "apigateway.amazonaws.com", "SourceArn": sub(f"arn:aws:execute-api:{REG}:{ACC}:${{WsApi}}/{src}")}}

# ------------------------------------------------------------------ EventBridge Pipes: RabbitMQ shipments.events → commerce bus
R["PipeRole"] = {"Type": "AWS::IAM::Role", "Properties": {
    "RoleName": "voltaj-pipe-3pl",
    "AssumeRolePolicyDocument": {"Version": "2012-10-17", "Statement": [{"Effect": "Allow", "Principal": {"Service": "pipes.amazonaws.com"},
                                                                          "Action": "sts:AssumeRole"}]},
    "Policies": [{"PolicyName": "pipe", "PolicyDocument": {"Version": "2012-10-17", "Statement": [
        allow(["mq:DescribeBroker"], imp("Integration", "BrokerArn")),
        allow("secretsmanager:GetSecretValue", imp("Base", "MqSecretArn")), allow("kms:Decrypt", KEY),
        allow(["ec2:CreateNetworkInterface", "ec2:DescribeNetworkInterfaces", "ec2:DeleteNetworkInterface", "ec2:DescribeVpcs",
               "ec2:DescribeSubnets", "ec2:DescribeSecurityGroups"], "*"),
        allow("events:PutEvents", att("Bus", "Arn"))]}}]}}
R["Pipe"] = {"Type": "AWS::Pipes::Pipe", "Condition": "PipeOn", "Properties": {
    "Name": "voltaj-3pl-shipments", "Description": "3PL replies: RabbitMQ shipments.events → filter → commerce bus", "RoleArn": att("PipeRole", "Arn"),
    "Source": imp("Integration", "BrokerArn"),
    "SourceParameters": {"RabbitMQBrokerParameters": {"QueueName": "shipments.events", "VirtualHost": "/", "BatchSize": 10,
                                                      "Credentials": {"BasicAuth": imp("Base", "MqSecretArn")}},
                         "FilterCriteria": {"Filters": [{"Pattern": json.dumps({"data": {"type": ["ShipmentDispatched"]}})}]}},
    "Target": att("Bus", "Arn"),
    "TargetParameters": {"EventBridgeEventBusParameters": {"Source": "com.shop.3pl", "DetailType": "ShipmentDispatched"},
                         "InputTemplate": '{"orderId": "<$.data.orderId>", "eventId": "<$.data.eventId>", "carrier": "<$.data.carrier>", '
                                          '"trackingNo": "<$.data.trackingNo>", "cid": "<$.data.cid>", "vid": "<$.data.vid>", '
                                          '"smsOptIn": false}'}}}

# ------------------------------------------------------------------ SES: domain identity (DKIM in Route 53), config set, templates
R["MailIdentity"] = {"Type": "AWS::SES::EmailIdentity", "Properties": {"EmailIdentity": ref("MailDomain"),
                     "DkimSigningAttributes": {"NextSigningKeyLength": "RSA_2048_BIT"},
                     "ConfigurationSetAttributes": {"ConfigurationSetName": ref("MailConfigSet")}}}
for i in (1, 2, 3):
    R[f"MailDkim{i}"] = {"Type": "AWS::Route53::RecordSet", "Properties": {"HostedZoneId": ref("HostedZoneId"), "Type": "CNAME", "TTL": "1800",
                         "Name": att("MailIdentity", f"DkimDNSTokenName{i}"), "ResourceRecords": [att("MailIdentity", f"DkimDNSTokenValue{i}")]}}
R["MailConfigSet"] = {"Type": "AWS::SES::ConfigurationSet", "Properties": {"Name": "voltaj-shop-mail"}}
R["MailEvents"] = {"Type": "AWS::SES::ConfigurationSetEventDestination", "Properties": {"ConfigurationSetName": ref("MailConfigSet"),
                   "EventDestination": {"Name": "to-eventbridge", "Enabled": True, "MatchingEventTypes": ["send", "delivery", "bounce", "complaint", "reject"],
                                        "EventBridgeDestination": {"EventBusArn": sub(f"arn:aws:events:{REG}:{ACC}:event-bus/default")}}}}
R["TplOrderConfirmed"] = {"Type": "AWS::SES::Template", "Properties": {"Template": {"TemplateName": "voltaj-OrderConfirmed",
                          "SubjectPart": "Voltaj: order {{orderId}} is confirmed",
                          "HtmlPart": "<h1>Thank you, {{name}}!</h1><p>We received order <b>{{orderId}}</b>.</p><p>Total: <b>€{{total}}</b></p>"
                                      "<p>We tell you when the order ships.</p>",
                          "TextPart": "Thank you, {{name}}! We received order {{orderId}}. Total: EUR {{total}}."}}}
R["TplShipment"] = {"Type": "AWS::SES::Template", "Properties": {"Template": {"TemplateName": "voltaj-ShipmentDispatched",
                    "SubjectPart": "Voltaj: order {{orderId}} is on the way",
                    "HtmlPart": "<h1>Your order is on the way</h1><p>Order <b>{{orderId}}</b> left the warehouse.</p>"
                                "<p>Carrier: {{carrier}}<br>Tracking number: <b>{{trackingNo}}</b></p>",
                    "TextPart": "Order {{orderId}} left the warehouse. Carrier {{carrier}}, tracking {{trackingNo}}."}}}

# ------------------------------------------------------------------ outputs
for k, v in {"ApiId": ref("Api"), "ApiDomain": sub(f"${{Api}}.execute-api.{REG}.amazonaws.com"), "WsApiId": ref("WsApi"),
             "WsUrl": sub(f"wss://${{WsApi}}.execute-api.{REG}.amazonaws.com/prod"), "UserPoolId": ref("UserPool"),
             "UserPoolClientId": ref("UserPoolClient"), "StateMachineArn": ref("Saga"), "BusArn": att("Bus", "Arn"),
             "EmailDlqUrl": ref("EmailDlq")}.items():
    O[k] = {"Value": v, "Export": {"Name": {"Fn::Sub": "${AWS::StackName}-" + k}}}

tpl = {"AWSTemplateFormatVersion": "2010-09-09",
       "Description": "Voltaj app - Cognito, REST + WebSocket API, Lambda, Step Functions saga, EventBridge, Pipes, SNS, SQS, SES, MSK consumers, learning functions.",
       "Parameters": P, "Conditions": COND, "Resources": R, "Outputs": O}
json.dump(tpl, open(sys.argv[1], "w"), indent=1)
print(len(R), "resources")
