# E-Commerce on AWS - Serverless + Decoupled (Pub/Sub, Event-Driven) - shared understanding

Status: grill-me session 2026-10-26, rounds 1-3 decided (Q1-Q25). Only open item: the user confirms the domain names in §9.
First diagram drawn 2026-10-26; the user rejected its layout as unstructured. Second grill-me session (layout,
Q1-Q24) decided the structured layout in §10. Next step: redraw the diagram per §10 (diagram only; estimate and
CloudFormation come later).

## 1. Frame

- One e-commerce application, one architecture. The source headings "A - Paris" and "B - London" are NOT regions; they
  are the two halves of the same design (synchronous serverless core + asynchronous event-driven backbone).
- One account, one Region: **Frankfurt (eu-central-1)**, 3 Availability Zones, no second Region (no DR).
- Design principle (user): **best practice and scalable**. Do not pick services or sizes for low volume or low cost.
  Production deployment models everywhere (Multi-AZ, clusters, standby replicas).
- Output now: **diagram only**.

## 2. Story and actors

A fictional online electronics shop.

| Actor | What it does | Why it exists in the story |
|---|---|---|
| Customer | Browses, searches, uses the cart, checks out on a web SPA | Synchronous core |
| Back-office admin | Manages the catalog (Cognito group) | Admin APIs |
| External warehouse / 3PL | Runs a legacy WMS that speaks AMQP | Reason for Amazon MQ |
| Marketing / analytics team | Uses clickstream and commerce events | Reason for Amazon MSK |
| Payment provider (Stripe-like) | External HTTPS API with webhooks | Checkout saga, callback |

## 3. Services and their roles

Requested: Route 53, API Gateway, Lambda, Step Functions, Cognito, EventBridge (event bus), DynamoDB, Amazon MQ,
Amazon MSK, SNS, SES, S3, Aurora Serverless, OpenSearch. Added and accepted: SQS, CloudFront, WAF.
All services are available in eu-central-1 (checked with the AWS Knowledge MCP, including MSK Serverless,
OpenSearch Serverless, EventBridge Pipes, SES).

| Service | Decision |
|---|---|
| Route 53 | Existing public hosted zone **tdsynnexlab.link** (Z03414782ECSLICW59USM, account 179330777878). New names: `shop.tdsynnexlab.link` (CloudFront: SPA and `/api/*`, one origin domain, no CORS) and `ws.shop.tdsynnexlab.link` (WebSocket API custom domain). ACM certificates: us-east-1 for CloudFront, eu-central-1 for the WebSocket API |
| CloudFront + WAF | CloudFront serves the SPA from S3 (OAC) and fronts the REST API; WAF with managed rules on CloudFront only |
| S3 | SPA assets; product images (admin uploads with a presigned URL → S3 event to EventBridge → Lambda makes the resized images → served by CloudFront); clickstream data lake |
| Cognito | One user pool. Customers: email + password sign-up, optional MFA. Back office: group `admins`, MFA required; the API GW authorizer separates admin APIs by the group claim. No social sign-in |
| API Gateway | **REST API** (regional) behind CloudFront: Cognito authorizer, request validation, usage plans, direct Step Functions integration. A separate **WebSocket API** pushes the checkout result to the customer |
| Lambda | Microservices (product, cart, order, notification, integration); the functions that reach MQ, MSK and RDS Proxy run in the VPC |
| Step Functions | **Standard** workflow for the checkout saga: reserve stock (DynamoDB) → payment (external HTTPS, wait for callback with task token) → write order (Aurora) → publish `OrderPlaced`; compensation on each failure. Payment webhook: provider → `POST /api/webhooks/payment` (through WAF) → Lambda checks the signature → `SendTaskSuccess` / `SendTaskFailure`; the payment wait has a timeout (for example 15 minutes) that starts the compensation |
| EventBridge | One custom bus `commerce` for domain events (`OrderPlaced`, `PaymentFailed`, `ShipmentDispatched`, `UserUpdated`, ...): archive + replay, schema registry, a DLQ (SQS) and a retry policy on every rule target |
| EventBridge Pipes | Inbound 3PL messages: RabbitMQ queue → filter → `commerce` bus (Pipes MQ source concurrency 5; request a quota increase for scale) |
| DynamoDB | Catalog, cart (TTL), stock with conditional-update reservation, idempotency keys, popular-product counters |
| OpenSearch | **OpenSearch Serverless** search collection, standby replicas on; catalog kept in sync by the **DynamoDB zero-ETL integration** (OpenSearch Ingestion pipeline; PITR + DynamoDB Streams) |
| Aurora Serverless v2 | PostgreSQL; orders, customer profile, invoices (relational, reporting); writer + reader in different AZs; Lambda reaches it through **RDS Proxy** |
| Amazon MQ | **RabbitMQ, 3-node cluster** across 3 AZs (production model), **private broker**; the 3PL connects over **Site-to-Site VPN**. Outbound `FulfillOrder`: EventBridge rule → VPC Lambda → exchange. Inbound `ShipmentDispatched`: Pipes (above) |
| Amazon MSK | **MSK Serverless** (IAM auth required); clickstream + commerce event log. Producer: API GW `/events` → VPC Lambda → MSK (the browser cannot speak Kafka). Consumers: Lambda ESM in provisioned mode → S3 data lake, and → DynamoDB popular-product counters |
| SNS | Notification topic for `OrderPlaced` and `ShipmentDispatched`; fan-out to SQS queues (email, SMS, back office) |
| SES | Email: SQS → Lambda → SES template; the configuration set sends bounce/complaint events back to EventBridge |
| SQS | Order buffer and every DLQ; notification fan-out queues |

## 4. Flows (each one becomes its own scenario in the diagram)

1. Product search and listing (OpenSearch + DynamoDB)
2. Add to cart (DynamoDB)
3. Checkout saga (Step Functions Standard, payment callback, compensation); result pushed over WebSocket
4. `OrderPlaced` on the `commerce` bus, fan-out to several targets
5. Fulfillment command to the 3PL over Amazon MQ; `ShipmentDispatched` back to the bus through Pipes
6. Notifications: SNS → SQS → Lambda → SES (email), SMS as second receiver
7. Clickstream → MSK → S3 data lake and popular-product counters

Rules that apply to every flow: at-least-once delivery from MQ, MSK, SQS and Streams, so every consumer is
idempotent (DynamoDB idempotency keys); every async target has a DLQ.

## 5. Network

- VPC in 3 AZs with private subnets for Lambda, RDS Proxy, Aurora, MQ cluster and MSK Serverless.
- Gateway endpoints: S3, DynamoDB. Interface endpoints: EventBridge, Step Functions, SNS, SQS, Secrets Manager, STS,
  CloudWatch Logs.
- One NAT gateway per AZ, only for internet calls (payment provider).
- Site-to-Site VPN to the 3PL network for the private MQ broker.

## 6. Facts found during the session (AWS documentation)

- Lambda event source mapping for Amazon MQ: default concurrency 1 for RabbitMQ, 5 for ActiveMQ per mapping (Support
  can raise it). EventBridge Pipes with an MQ source: 5. Functions behind MQ/MSK mappings: max timeout 14 minutes.
- Amazon MQ for RabbitMQ: 3-node cluster across 3 AZs behind an NLB is the recommended production model.
- MSK Serverless: IAM access control is mandatory; available in Frankfurt. Lambda Kafka ESM has a provisioned mode.
- DynamoDB zero-ETL to OpenSearch Serverless collections uses OpenSearch Ingestion (PITR + Streams).
- API Gateway can start a Step Functions execution directly; the result needs DescribeExecution or a push channel.
- Aurora Serverless (platform v3/v4) scales fast and can scale to zero (not used for production here).

## 7. Security and operations (auxiliary, no arrows in the diagram)

- Secrets Manager: MQ credentials, Aurora credentials, payment provider API key.
- KMS customer managed keys instead of the default keys.
- Lambda Powertools (idempotency, logs, metrics), X-Ray tracing, CloudWatch alarms (DLQ depth, Pipes and ESM errors).

## 8. Diagram plan (skill `aws-arch-diagram-sc`, latest rules)

Five pages; every flow is its own scenario (own color, steps from 1); on pages 2-5 the components that the page's flows
do not use are grey. Instead of IP packet walks, each scenario gets an **event walk**: for each step, the event at that
point (source, detail-type, key fields).

1. Overall architecture, no flows. Layers: users and delivery, API, microservices, event backbone, data, integration.
2. Customer, synchronous: search, cart, start of checkout.
3. Checkout saga and `OrderPlaced` fan-out: Step Functions steps, payment callback, compensation, WebSocket push.
4. Fulfillment and notifications: MQ command out, Pipes reply back, SNS → SQS → SES.
5. Admin and analytics: catalog update with zero-ETL and image processing; clickstream → MSK → S3 and counters.

Apply the skill rules: ASD-STE100 legend sentences with a return path in the last step, `rtb-`/`tgw-rtb-` names if
route tables appear, "VPC endpoint" (not "PrivateLink") for interface/gateway endpoints, every AZ complete or not drawn,
layout lint + 100% crop review before delivery.

## 9. To confirm

- Decided 2026-10-27: `shop.tdsynnexlab.link` and `ws.shop.tdsynnexlab.link` (records not created yet).

## 10. Diagram layout v2 (grill-me session 2, 2026-10-26, Q1-Q24 all accepted)

Reason: v1 placed the Region services on a loose grid, page 1 had no arrows, and the structure did not read.

### 10.1 Skeleton (same positions on all five pages)
- **Global edge band**: inside AWS Cloud, outside the Region box, at the top: Route 53, WAF, CloudFront.
- **Region bands** top to bottom, each with a title and a light frame (no domain sub-boxes):
  1. API: REST API, WebSocket API, Cognito.
  2. Microservices (Lambda outside the VPC only): product, cart, webhook, ws, resize, email, sms, counters, archive.
  3. Orchestration & event backbone: Step Functions, EventBridge bus `commerce`, default bus, Pipes, SNS, SQS
     (order buffer, email, sms, back office, DLQs). SES and End User Messaging at the right end of this band,
     next to the customer inbox actor.
  4. Data: DynamoDB, OpenSearch Serverless, OpenSearch Ingestion, S3 web, S3 uploads, S3 data lake.
- **One VPC** (10.0.0.0/16) at the bottom: 3 AZs x 3 subnet tiers, every AZ complete, arrows only in AZ-a.
  - Public (10.0.0.0/24, 10.0.1.0/24, 10.0.2.0/24): NAT gateway. Route table: local, 0/0 → IGW.
  - Private-app (10.0.16.0/20, 10.0.32.0/20, 10.0.48.0/20): ENIs of the 4 VPC Lambdas (payment, order, fulfillment,
    producer) and the interface endpoint ENIs. Route table: local, 0/0 → NAT of the same AZ, S3/DynamoDB prefix
    lists → gateway endpoints.
  - Private-data (10.0.64.0/22, 10.0.68.0/22, 10.0.72.0/22): RDS Proxy ENI, MSK ENI, MQ node, Aurora instance.
    Route table: local, 172.16.0.0/16 → VGW, prefix lists → gateway endpoints. No 0/0 (no internet).
  - Gateway endpoints at VPC level. IGW on the right VPC edge (payment provider side), VGW on the bottom edge (3PL).
  - The 4 VPC Lambdas appear only in the VPC (not in the Microservices band).
- **Security & observability** column at the right inside the Region: Secrets Manager, KMS, CloudWatch, X-Ray
  (no arrows).
- **Actors**: Customer and Back-office admin top left (edge band level), Customer inbox/phone top right,
  Payment provider bottom right (IGW side), 3PL bottom (VGW level).
- **Security groups**: no boxes; a table in the legend (for example sg-lambda → sg-proxy 5432, → sg-mq 5671,
  → sg-msk 9098).

### 10.2 Page 1 (overview)
- Grey connection map: every connection without a number; WAF and Cognito authorizer as dotted associations.
- On top, the main customer journey in color with 14 numbered steps (one step can bundle several arrows):
  1 Customer → CloudFront (SPA, /api/*, WAF) · 2 CloudFront → REST API · 3 REST API → Lambda product → OpenSearch ·
  4 REST API → Lambda cart → DynamoDB · 5 REST API → Step Functions · 6 Step Functions → DynamoDB (reserve) ·
  7 Step Functions → Lambda payment → NAT → IGW → provider · 8 provider → CloudFront → Lambda webhook → Step
  Functions · 9 Step Functions → Lambda order → RDS Proxy → Aurora · 10 Step Functions → EventBridge (OrderPlaced) ·
  11 EventBridge → SQS buffer → Lambda fulfillment → MQ → VPN → 3PL · 12 3PL → MQ → Pipes → EventBridge
  (ShipmentDispatched) · 13 EventBridge → SNS → SQS → Lambda email → SES → customer · 14 Lambda ws → WebSocket API →
  customer.
- Left legend: the 14 steps in ASD-STE100 text. Right legend: key decisions, security group table, line styles.
- No event walk on page 1.

### 10.3 Pages 2-5
- Same skeleton; components not used by the page flows stay grey.
- The 24 scenarios, their ASD-STE100 texts and event walks stay as in v1; only the arrows follow the new positions.

### 10.4 Additions from v1 that stay (accepted)
1. Aurora reader 2 in AZ-c (complete AZ). 2. SQS order buffer between the EventBridge rule and Lambda fulfillment.
3. Lambda payment stores the task token in DynamoDB. 4. Two S3 buckets: uploads and web (no resize loop).
5. EventBridge default bus (S3 and SES events). 6. SMS through AWS End User Messaging. 7. WebSocket `$connect`
with a Lambda authorizer. 8. MSK consumer Lambdas outside the VPC (the ESM reaches MSK). 9. Refund, SES feedback
and the back-office consumer are notes only (not drawn).
