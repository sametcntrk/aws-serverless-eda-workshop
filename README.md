# Voltaj: a serverless, event-driven e-commerce shop that teaches its own architecture

**TR:** Voltaj, kurgusal bir Türk elektronik mağazası. Her tıklama Frankfurt'taki (eu-central-1) gerçek bir serverless ve event-driven AWS mimarisinde
çalışır. Sağdaki mor panel, sayfanın arkasındaki her AWS çağrısını canlı gösterir. Ödeme callback'i, OrderPlaced fan-out'u, 3PL cevabı ve e-posta gibi
dakikalar sonra gelen adımlar da panele düşer. Her kayıttan Türkçe bir 101 dersi açılır.

Live: <https://shop.tdsynnexlab.link> · Diagram: <https://shop.tdsynnexlab.link/diagram> · Lessons: <https://shop.tdsynnexlab.link/lessons>

## What is in the box

| Part | Where |
|---|---|
| Architecture decisions (grilling rounds) | `docs/SHARED-UNDERSTANDING.md`, `docs/LEARNING-APP-HANDOFF.md` (§11 = decisions for the app) |
| Architecture diagram (5 pages, draw.io) | `docs/diagram/ecommerce-serverless-eda.drawio`; generator `docs/diagram/gen_ecommerce_eda.py` |
| Infrastructure (CloudFormation, 10 stacks) | `cloudformation/` (`app.json` and `network.yaml` are generated from `cloudformation/src/`) |
| Lambda functions (Python 3.13, Powertools layer) | `app/functions/*/app.py`; shared trace/API/guard code in `app/layers/common/python/voltaj/` |
| Checkout saga (Step Functions Standard, JSONata) | `app/statemachine/gen_checkout.py` → `checkout.asl.json` |
| External actors (simulators) | `app/paysim/` (VoltPay payment provider), `app/threepl/` (3PL WMS + Libreswan VPN on EC2) |
| SPA (plain ES modules, no framework) | `web/` (`js/core.js` panel + WebSocket + sign-in, `js/app.js` pages, `js/lesson.js` 101 lessons) |
| Seed data (200 products, illustrations, personas, history) | `tools/seed.py` |
| Deploy / teardown | `tools/deploy.sh [step|all]`, `tools/destroy.sh`, quick code update `tools/hotfix.sh <fn>` |
| Browser tests (Playwright, real clicks) | `tests/` |

## Stacks

| Stack | Region | Kept between workshop days | Contents |
|---|---|---|---|
| `voltaj-global` | us-east-1 | yes | ACM certificate (shop, pay), WAF web ACL (CloudFront) |
| `voltaj-base` | eu-central-1 | yes | KMS key, secrets |
| `voltaj-learning` | eu-central-1 | yes | `voltaj-trace` (live trace, stream), `voltaj-guard` (cost guard counters) |
| `voltaj-network` | eu-central-1 | no | VPC 3 AZ x 3 tiers, NAT per AZ, VPC endpoints, security groups, Site-to-Site VPN |
| `voltaj-data` | eu-central-1 | no | DynamoDB, Aurora Serverless v2 (writer + 2 readers) + RDS Proxy, OpenSearch Serverless + zero-ETL pipeline, S3 |
| `voltaj-integration` | eu-central-1 | no | Amazon MQ for RabbitMQ (3-node cluster), MSK Serverless |
| `voltaj-app` | eu-central-1 | no | Cognito, REST + WebSocket API, 18 Lambda functions, saga, EventBridge, Pipes, SNS, SQS, SES |
| `voltaj-edge` | eu-central-1 | no | CloudFront (SPA + `/api/*`), Route 53 names, WebSocket custom domain |
| `voltaj-paysim` | eu-central-1 | no | VoltPay simulator at `pay.tdsynnexlab.link` |
| `voltaj-3pl` | eu-central-1 | no | 3PL VPC 172.16.0.0/16, EC2 customer gateway + WMS |

```bash
tools/deploy.sh all        # about 45 minutes from zero (MQ cluster, Aurora and OpenSearch take the longest)
tools/destroy.sh           # deletes the fixed-cost stacks; asks for "yes"
```

## How the live trace works

1. The SPA sends `X-Vid` (visitor) and `X-Cid` (correlation ID of the action) with every API call.
2. `voltaj.trace` registers botocore hooks, so every AWS SDK call of a function becomes one entry (service, operation, request text,
   parameters, duration, item count, DynamoDB capacity and cost, network path, auth). SQL, AMQP, Kafka and HTTPS calls are wrapped by hand.
3. Entries carry the diagram scenario and step (`sc = p3s1`, `st = 2`), so the panel badge links to the same step in the diagram.
4. Entries go to the DynamoDB table `voltaj-trace`. Its stream invokes `voltaj-tracepush`, which pushes each entry over the WebSocket
   to the connections of the same visitor. The saga writes its own entries with direct DynamoDB integrations; the bus tap function
   writes entries for steps without code (rule matches, Pipes, SNS fan-out); the simulators write theirs too.
5. The cid travels in every event: `detail.cid` on EventBridge, the event body through SNS/SQS, AMQP headers, Kafka headers, S3 object metadata.

## Cost guard

WAF rate rule (2,000 requests / 5 min / IP), API Gateway throttling, checkout 5/min per visitor (in the saga), admin uploads 20/h,
product saves 60/h, clickstream 120 batches/min per visitor, bursts 5/h (max 200 orders or 1,000 clicks), replays 2/h, duplicate-event
experiments 10/h. A blocked call shows as a red panel entry with the reason.
