# Learning app for the serverless EDA architecture - handoff and shared understanding

> Written: 2026-10-27, from the AWS database workshop session (~/Datatype).
> Read with: `SHARED-UNDERSTANDING.md` in this folder (the architecture, decided in two grill-me rounds).
> Status: **decided** (grilling 2026-10-27, rounds 1-3, see §11; §11 overrides §5-§9 where they differ).

## 0. How to use this document

1. Read `SHARED-UNDERSTANDING.md` (architecture, services, 7 flows, diagram plan).
2. Read this document. Then open the reference implementation (§1) and read the files named there.
3. Run a grilling round on the open decisions in §8, in Turkish, one numbered question with a recommended answer each.
4. Write the agreed result back into this file (change "proposal" to "decided" item by item).
5. Build in the phases of §9. Test with the checklist of §10 before you tell the user a phase is done.

The user writes Turkish; reply in Turkish. When the user names a skill, follow that skill exactly.

## 1. Reference implementation (read it, do not guess)

- Live: https://dbworkshop.tdsynnexlab.link/ (AWS account 179330777878, eu-central-1, stack `dbws-workshop`; do not
  delete it, the user wants to keep it).
- Repo: https://github.com/sametcntrk/aws-database-workshop (public, branch `main`). Local copy: `~/Datatype`.
- Domain: "Lale Market", a fictional Turkish shop. 10 AWS databases; each one powers one part of the shop and has
  exactly one EC2 "Engine App" (Flask) that talks only to its own database. The browser composes each page from
  several Engine Apps (ADR `docs/adr/0002-browser-composes-storefront.md`).

| File (under `app/engine_app/`) | What to take from it |
|---|---|
| `trace.py` | The trace contract: every backend call becomes one trace entry, returned with the API JSON |
| `engines/*.py` | How each call is wrapped (`with trace.call(op, request_text, params) as t: ... t.result(...)`); `learn_overview` / `learn_item` for the 101 big picture |
| `static/js/lm.js` | Behind-the-scenes panel (`api()`, `addCall`, `renderEntry`), Tutorial, Guided journey, 101 link hand-off (`keepForLesson`) |
| `templates/base.html` | Page shell: amber learning bar on top, header, panel on the right, mini Tutorial bar, persona dialog |
| `static/css/lm.css` | Design tokens (tulip red, navy, Iznik teal, amber learning layer, one colour per Engine), all components |
| `tutorials/*.yaml`, `tutorials/journey.yaml` | Tutorial steps per page (`title`, `text`, `target` CSS selector) and the guided journey stops |
| `lessons/*.yaml`, `templates/learn/lesson.html`, `static/js/learn.js`, `static/css/learn.css` | 101 lessons: content in YAML (Turkish), one generic template, the zoom and tree components |
| `templates/learn/opensearch/search.html` | The one hand-made lesson: the richest example of a lesson |
| `web.py` | Routing: `find_lesson()` picks a lesson from the clicked call (longest `[METHOD ]/api/path` match, then op name) |

## 2. The mentality (keep all of this)

1. **A real application on real AWS services, with a story.** Not a slide deck and not a mock. A visitor uses a shop;
   every click does real work on the real service.
2. **Every action shows what happened behind it.** A "Behind the scenes" panel on the right lists every backend call
   of the page as it happens: service, operation, the real request text, parameters, duration, result count, network
   path, authentication, capacity and cost when known, an explanation note, the error when it fails.
3. **The panel is a timeline.** Call 1 is at the top, new calls are added below. Each call has a numbered badge in the
   colour of its service; the same colour marks the service tag on the page part that made the call. Pointing to a
   call outlines the page element that made it.
4. **A separate learning layer, in amber, above the product.** Amber is never used by the product itself.
   - Guided journey: an ordered list of stops across pages with a progress bar and "Next stop".
   - Tutorial: steps per page; each step can spotlight a page element (`target`), Next/Back scroll to it and pulse it.
     A small fixed Back/Next/Close bar appears whenever the Tutorial buttons are not visible (see §4, pitfall 2).
     Close and Finish close the Tutorial for this page only; the header toggle turns it on or off everywhere.
5. **Experiments on the page.** Small toggles that change one parameter of the real call (index on/off, fuzziness,
   consistent read, atomic vs naive counter, rollback) so the visitor sees the difference in the panel.
6. **101 lessons in a new tab, from the real call.** Each panel entry has a "101: What happened to the data? ↗" link.
   The lesson is Turkish, for beginners, and is filled with the clicked call's real data. Sections:
   1. Hero: the question, with the visitor's own value in it ("“kablosuz kulaklik” yazdın… nasıl?").
   2. **Big picture → selected record → nested structure**: every record (or a sample) of the service as small tiles
      in shelves; the records of the call marked; one tile selected; on the right the selected record as a nested tree
      with a type label per field. Tiles are clickable. This is the part the user liked most.
   3. "Kaynakta veri böyleydi, X'te böyle duruyor": the source form next to the stored form.
   4. "Senin çağrın adım adım": one step per real trace entry, with a Turkish explanation per operation.
   5. An everyday analogy.
   6. **"Neden X? Muadilleriyle kıyas"**: alternatives table with the same criteria for each option, ✓ / ~ / ✕, and a
      "Karar" box. Check every claim in the AWS documentation (AWS Knowledge MCP) and link the source.
   7. "Kendin dene" links, a glossary, and an index of all lessons.
7. **Personas.** A visitor picks a persona (a seeded customer with history) so that recommendations and history exist
   from the first page; the visitor's own writes stay separate (a visitor cookie).
8. **Report screens and a capped load simulation.** Admin pages show the analytic side. The load simulation is real
   but capped (requests per run, runs per hour) as a cost guard.
9. **Language.** Product UI text in English written to ASD-STE100 (lint: `~/.claude/skills/asd-ste100/scripts/ste-lint.py`).
   Lessons and guides in clear Turkish. Technical terms stay in English.
10. **Quality over cost, but guard the cost of anything a visitor can trigger in a loop.**

## 3. Contracts that make it work

### 3.1 Trace entry (one per backend call)
```json
{ "op": "UpdateItem", "engine": "Amazon DynamoDB", "request": "table.update_item(Key=..., ConditionExpression=...)",
  "params": {"qty": 1}, "ms": 7.4, "items": 1, "capacity": "1 WRU", "cost": "≈ $0.0000007625",
  "path": "EC2 10.20.10.13 → gateway endpoint → DynamoDB", "auth": "IAM role (SigV4)",
  "note": "ADD is atomic: ...", "explain": "...", "plan": "...", "error": null, "ok": true }
```
API responses are `{ "ok": true, "data": ..., "trace": [entries] }`. The browser `api()` helper adds one panel call per
API request and keeps the call in `localStorage["lm_learn"][<key>]` (last 25) so the 101 tab can read it.

### 3.2 101 link
`/<service>/learn?op=<op>&api=<path>&method=<METHOD>&k=<localStorage key>&i=<entry index>`; the server picks the
lesson; a lesson opened without `k` runs one safe sample GET or shows "do this in the shop first".

### 3.3 Big picture endpoints (per service)
`GET /api/learn/overview?lesson=&focus=a,b,c` → `{title, text, facts: [[value, label]], groups: [{label, items:
[{id, title, hit}]}], hit_label}` and `GET /api/learn/item?lesson=&id=` → `{title, sub, record, marks: {path: "kept"}}`.
`focus` comes from the call (`path`, `query:<name>`, `data:<key>`, `keys`); the server marks matching tiles.

## 4. Pitfalls we hit (do not repeat)

1. `[hidden]` lost against component CSS (`.tutor { display: grid }`), so a closed Tutorial stayed on screen as an
   empty box whose buttons did nothing. Put `[hidden] { display: none !important; }` in the base CSS on day one.
2. Next scrolled to the step target, the Tutorial buttons went under the sticky header, and a click hit the header.
   Show the mini bar from the real overlap (button row top < header bottom while the header is stuck).
3. Tests that read `.hidden` or call `element.click()` passed while users saw broken buttons. Test with real mouse
   events at the button centre, check `document.elementFromPoint` is the button, and check computed `display`.
4. Ask the user before you run browser automation against the live site the first time.
5. Flask `jsonify` sorted keys and broke the field order of records in lessons: `app.json.sort_keys = False`.
6. Seed data generated "relative to seed time" went out of the default time range a day later (InfluxDB). Generate
   time series up to "now" or let the lesson widen the range and say so.
7. Empty states: an empty cart showed an empty big picture. Always render the visitor's own group, even when empty,
   with a sentence that says what to do.
8. `localStorage` (not `sessionStorage`) carries the call to the new tab: `target=_blank rel=noopener` does not copy
   session storage.
9. Deploys to the instances used SSM `send-command`; the auto-mode classifier blocked it until the user added allow
   rules in `.claude/settings.local.json`. In a new project, ask the user for the same rules up front.
10. Do not over-claim in the alternatives tables. One wrong ✓ costs more trust than a missing row.

## 5. Adaptation to the serverless EDA architecture (proposal)

### 5.1 The main difference: work continues after the HTTP response
In Lale Market every call finishes inside one request, so the trace returns with the response. In this architecture
most work happens later and elsewhere: the checkout saga waits for a payment callback, `OrderPlaced` fans out, the 3PL
answers over Amazon MQ, SES sends mail, MSK consumers write the data lake. The panel must therefore show **a live
event walk**, not only a request/response list.

Proposed design ("live trace"):
- Every entry point creates a **correlation id** (`cid`, for example the order id or a UUID) and returns it to the
  browser. Every event carries it (`detail.cid` on EventBridge, a message attribute on SNS/SQS/MQ, a Kafka header on
  MSK, the Step Functions execution input).
- Every Lambda (and the Step Functions states through a small Lambda or `$$.Execution` context) writes one trace
  entry per AWS call into a DynamoDB table `trace` (`pk = cid`, `sk = ts#seq`, TTL 24 h). Use botocore event hooks
  (`before-call` / `after-call`) or a Powertools middleware so the SDK calls are traced without hand-written wrappers.
- A DynamoDB Stream on `trace` → Lambda `ws-push` → the existing **WebSocket API** pushes each new entry to the
  connections that subscribed to that `cid`. The panel adds entries as they arrive, also minutes later (payment
  callback, shipment).
- Each entry gets the **diagram scenario and step number** (`scenario: 3, step: 7`) so that the panel, the 101
  lessons and the draw.io diagram use the same numbers and colours. The panel can link to the diagram page.
- The trace entry gains event fields: `event.source`, `event.detailType`, key fields, `bus`/`queue`/`topic`, retry
  count, DLQ flag. These are the "event walk" of the diagram plan (§8 of SHARED-UNDERSTANDING).
- X-Ray stays on for operations; it is not the panel's source (too slow and too coarse for a visitor view).

### 5.2 Mapping of the Lale Market parts

| Lale Market | Serverless EDA app |
|---|---|
| 10 Engine Apps on EC2, one per database | Microservice Lambdas behind REST API; the SPA is on S3 + CloudFront (`shop.tdsynnexlab.link`) |
| Engine colour | One colour per **service** (Lambda, Step Functions, EventBridge, SQS, SNS, MQ, MSK, DynamoDB, Aurora, OpenSearch, S3, SES, Cognito); scenario colours from the diagram for the step badges |
| Panel = list of request/response calls | Panel = live timeline grouped by `cid`: synchronous part first, then async entries streaming in; a "waiting for payment callback" placeholder; DLQ and retry entries in red |
| Experiments: index on/off, fuzziness, rollback | Fail the payment (compensation runs), send a duplicate event (idempotency key stops it), break a consumer (message goes to the DLQ, then redrive), replay from the EventBridge archive, change a Pipes filter, slow consumer (SQS backlog) |
| Load Simulation (capped) | Event burst (capped): N `OrderPlaced` or clickstream events; show fan-out counts, SQS depth, Lambda concurrency |
| Report screens | Saga executions list (Step Functions), event archive browser, DLQ viewer, MSK consumer lag, data-lake objects |
| 101 lessons per database | 101 lessons per **pattern** and per service (see 5.3) |

### 5.3 101 lessons (Turkish), proposed list
Patterns: pub/sub fan-out; queue vs topic vs bus vs stream; saga and compensation; callback with task token;
idempotency and at-least-once delivery; retry, DLQ and redrive; event archive and replay; schema registry; Pipes
filter and enrichment; WebSocket push; zero-ETL DynamoDB → OpenSearch; CloudFront + WAF + OAC; Cognito groups and
the authorizer; presigned upload → S3 event → resize; clickstream → MSK → data lake.

"Big picture → selected → nested" ideas:
- EventBridge: the archived events of the last hour as tiles grouped by detail-type; the call's events marked;
  selected event → the full event JSON (source, detail-type, detail with nested fields) and the rules that matched.
- Step Functions: the states of the checkout execution as tiles in order; selected state → its input and output.
- SQS / DLQ: messages as tiles per queue; selected → body, attributes, receive count.
- MSK: partitions as shelves, offsets as tiles; selected → record key, headers, value.
- SNS: subscriptions as shelves; selected delivery → the message each subscriber got.
- DynamoDB / Aurora / OpenSearch / S3: as in Lale Market.

"Muadilleriyle kıyas" is central here: for example SQS vs SNS vs EventBridge vs Amazon MQ vs MSK for the same message;
Step Functions Standard vs Express vs choreography only; WebSocket API vs polling vs AppSync subscriptions.
Verify every claim with the AWS Knowledge MCP.

### 5.4 What stays the same
Amber learning layer on top, Tutorial and Guided journey (the journey follows the 7 flows), personas, ASD-STE100 UI
English and Turkish lessons, design tokens and component look (copy `lm.css` and adapt), capped load, test discipline.

## 6. Frontend shape (proposal)
- Static SPA (plain ES modules, no framework needed; Lale Market uses none) on S3 behind CloudFront, as in the
  architecture. Lesson content as YAML/JSON in the SPA bundle; lesson data from `/api/learn/*` on the REST API.
- Port from Lale Market: `lm.js` (panel, tutorial, journey, persona), `learn.js` (zoom, tree, lesson renderer),
  `lm.css`, `learn.css`. Add a WebSocket client for the live trace.

## 7. Infrastructure notes (proposal)
- Domain: `shop.tdsynnexlab.link` and `ws.shop.tdsynnexlab.link` (still "to confirm" in SHARED-UNDERSTANDING §9).
- The `trace` table, the `ws-push` Lambda and the trace middleware are additions to the architecture. Add them to the
  diagram only if the user wants (proposal: an "observability for the learning app" note, not a main flow).
- Same account and Region as the database workshop; keep both apps independent (separate stacks).

## 8. Open decisions to grill (the user decides)

1. Is the goal the same as Lale Market: a learning app with a real shop on top of the real architecture (yes), or a
   pure visualiser of the diagram?
2. Live trace design: DynamoDB `trace` table + Stream + WebSocket push (recommended) vs X-Ray query vs CloudWatch Logs.
3. Do panel entries carry the diagram scenario/step numbers and colours, with a link to the diagram page? (recommended)
4. Which experiments first (recommended: failed payment → compensation; duplicate event → idempotency; broken
   consumer → DLQ → redrive)?
5. Lesson list and order; which lesson is the hand-made "sample" to approve first (recommended: pub/sub fan-out of
   `OrderPlaced`, or the checkout saga).
6. The external actors: a simulated payment provider (our own small HTTPS endpoint with webhooks) and a simulated 3PL
   (an AMQP client that answers `FulfillOrder` with `ShipmentDispatched`)? Where do they run?
7. Delivery: CloudFormation (one template, like the workshop) vs CDK; one stack or several.
8. Cost guard limits for the event burst and for MSK/MQ (both have a high fixed cost: confirm the user accepts it).
9. Domain names (§7).
10. Does the participant guide (Turkish, console-based, like `~/Datatype/guide/`) belong to this project too?

## 9. Suggested phases
1. Grill (§8) → update this file.
2. Skeleton: SPA shell with the learning bar, panel and persona; REST API + one Lambda with the trace middleware.
3. Synchronous flows (search, cart) with the panel; Tutorial for these pages.
4. Live trace (cid, `trace` table, Stream, WebSocket push); checkout saga with the payment simulator; compensation
   experiment.
5. `OrderPlaced` fan-out, MQ/3PL round trip, SNS → SQS → SES; DLQ/redrive experiment.
6. One hand-made 101 lesson → user approval → the rest from YAML.
7. Report screens, capped event burst, clickstream/MSK.
8. Polish with `frontend-design:frontend-design`; full test pass.

## 10. Definition of done (per phase)
- Every page loads with no console error; every API call shows in the panel with its entries.
- Async entries arrive in the panel for the same `cid`, in order, within seconds of the real event.
- Tutorial: on every page, real mouse clicks on Next go from step 1 to Finish; Close and Finish really remove the
  box (computed `display: none`); the mini bar appears when the buttons are covered.
- Every 101 link opens the right lesson; big picture and item endpoints return data for every lesson; no "okunamadı".
- Alternatives tables: every claim checked against AWS docs; sources linked.
- Commit with the attribution trailer; deploy; re-test on the live domain; report results with the real output.

## 11. Decisions (grilling 2026-10-27)

Round 1:
1. **Goal - decided**: a learning app with a real shop on the real architecture (Lale Market model), not a visualiser.
   The story is the fictional electronics shop; each of the 7 flows is one user action in the shop.
2. **Run mode - decided**: the production model stays. Fixed-cost parts (MQ cluster, MSK, OpenSearch Serverless,
   Aurora, NAT, VPN, interface endpoints) live in separate stacks that are deployed and deleted with one script
   (on for workshop/demo days). Seed data loads again at every deploy. A precise monthly estimate comes later.
3. **IaC - decided**: plain CloudFormation (YAML), several independent stacks joined by export/import: network,
   data, integration (MQ, MSK), app, edge (CloudFront, WAF, ACM us-east-1, Route 53), learning (trace, ws-push).
4. **Domains - decided**: `shop.tdsynnexlab.link` and `ws.shop.tdsynnexlab.link`.
5. **Repo - decided**: new public repo `sametcntrk/aws-serverless-eda-workshop`, local `~/Pubsub`, layout like the
   workshop (`app/`, `cloudformation/`, `docs/`, `guide/`, `tools/`); docs and diagram move to `docs/`. Ask before
   creating the repo and before the first push.

User clarification (2026-10-27, before round 2): the app turns the existing e-commerce diagram into a web shop
with its own story. It has **no relation to Lale Market** (own name, story, look; no links between the two). Lale
Market is only the model for the learning mechanics: what happens behind the current page, 101-style guides in other
tabs, room to explore and play with the services. Round 1 decisions still hold.

Round 2 (all recommendations accepted):
6. **Story - decided**: fictional Turkish electronics shop **"Voltaj"**; short story (fast-growing shop, warehouse
   work with a 3PL on a legacy WMS, marketing wants clickstream) explains why each service exists. UI English
   (ASD-STE100), lessons Turkish.
7. **Look - decided**: new identity with `frontend-design:frontend-design` (electronics / energy theme); show the
   user 2-3 options before choosing. The learning layer uses one colour that the product never uses (not
   necessarily amber).
8. **Code - decided**: do not copy Lale Market code. Read its trace contract, panel behaviour and the
   big picture → selected → nested component as reference; write clean new code. Apply §4 pitfalls from day one.
   No link or name of Lale Market anywhere.
9. **Live trace - decided**: §5.1 design (cid everywhere, DynamoDB `trace` table with TTL 24 h, Stream → `ws-push`
   → WebSocket). X-Ray for operations only. Lives in the `learning` stack.
10. **Diagram link - decided**: every trace entry carries scenario, step and colour; "See in diagram" link to a
    diagram page in the app; single source `scenarios.json`.
11. **Identity - decided**: personas are seeded Cognito users with history; the SPA signs in for real (real JWT);
    visitor writes are kept under a separate visitor id; real sign-up optional; persona password change and delete
    blocked.
12. **Admin - decided**: "demo admin" persona in `admins` with a fixed TOTP secret (SPA makes the code, MFA step is
    real in the panel); writes limited to `demo-` products, images <= 2 MB, hourly cap.
13. **Payment simulator - decided**: `paysim` stack, Lambda + CloudFront at `pay.tdsynnexlab.link`; hosted checkout
    page with Pay / Decline / No answer; HMAC-signed webhook; demo timeout 2 min (parameter).
14. **3PL simulator - decided**: `3pl` VPC 172.16.0.0/16 with a small EC2: strongSwan customer gateway + Python
    AMQP client (`FulfillOrder` in, `ShipmentDispatched` out after a few seconds); deployed and deleted with the
    fixed-cost layer.
15. **First experiments - decided**: payment decline → compensation; duplicate event → idempotency; broken consumer
    → DLQ → redrive. Later: replay, Pipes filter, SQS backlog.
16. **Sample lesson - decided**: `OrderPlaced` pub/sub fan-out first; checkout saga second.
17. **Participant guide - decided**: yes, after the app is complete; reserve `guide/` now.

Round 3 (all recommendations accepted):
18. **Seed - decided**: ~200 products in 8 categories, fictional brand names, generated category-style
    illustrations (no real photos); 6 personas (5 customers with orders, carts, click history + 1 demo admin); one
    seed script, reloaded at every deploy.
19. **Email/SMS - decided**: real API calls to the SES mailbox simulator and the End User Messaging SMS simulator
    numbers (real delivery/bounce/complaint events); an in-app "Inbox" page shows the persona's rendered email and
    SMS from the trace by `cid`. Real email only to an optional real sign-up, and only with SES production access.
    To do: verify simulator support in the AWS docs.
20. **Cost guard - decided** (all parameters): burst max 200 `OrderPlaced` or 1,000 clickstream events per run,
    max 5 runs per hour; checkout max 5 per minute per visitor; admin uploads max 20 per hour; WAF rate rule 2,000
    requests per 5 min per IP; API GW usage plan throttle; AWS Budgets alarm. A blocked request shows as a red panel
    entry with the reason.
21. **Lesson order - decided**: CloudFront+WAF+OAC; Cognito groups + authorizer; zero-ETL DynamoDB → OpenSearch;
    DynamoDB conditional update; saga + compensation; task token callback; WebSocket push; pub/sub fan-out (sample);
    queue vs topic vs bus vs stream; idempotency + at-least-once; retry/DLQ/redrive; archive + replay; schema
    registry; Pipes filter + enrichment; SNS → SQS → SES; presigned upload → S3 event → resize; clickstream → MSK →
    data lake. Plus one short lesson per service. A panel entry opens the pattern lesson first, else the service one.
22. **Journey and reports - decided**: journey follows the 7 flows (search → cart → checkout/payment → fan-out →
    shipping/3PL → Inbox → admin/analytics). Reports: saga executions, EventBridge archive browser, DLQ viewer with
    redrive, MSK consumer lag, data lake objects, popular-product counters.
23. **Phases - decided** (replaces §9): 0 identity options → user choice; 1 repo + skeleton stacks (network, edge,
    app, learning); 2 SPA shell, panel, personas, sync flows (search, cart), Tutorial; 3 live trace, checkout saga,
    paysim, compensation experiment; 4 fan-out, 3PL VPC + VPN, notifications, DLQ/redrive experiment; 5 sample
    lesson → approval → other lessons; 6 admin + analytics, MSK, reports, burst; 7 polish + full test pass;
    8 participant guide. Test each phase with §10 before reporting it done.
24. **Permissions - decided**: add allow rules to `.claude/settings.local.json` for deploy/verify commands
    (`aws cloudformation deploy/describe-*`, `aws s3 sync`, `aws cloudfront create-invalidation`, `aws logs`,
    `aws stepfunctions describe-*`); show the full list to the user first. No delete commands in the allow list.
    Browser automation against the live site is approved.

Defaults (not grilled, change if the user objects): Lambda in Python with Powertools; SPA in plain ES modules (no
framework); Playwright for browser tests with real mouse events.

After round 3 (user, 2026-10-27): shared understanding confirmed. No identity options needed; Claude picks the look.
**Continue without asking until v1 is out** (overrides "show 2-3 options", "ask before repo/push" and "show the
allow list first").

## 12. Build status - v1 (2026-10-27)

Repo: https://github.com/sametcntrk/aws-serverless-eda-workshop (public, `main`), local `~/Pubsub`. Live: https://shop.tdsynnexlab.link.
All 10 stacks deployed in 179330777878 (eu-central-1; `voltaj-global` in us-east-1). Read `README.md` first.

Verified on the live site with Playwright (`tests/`), real mouse clicks, 0 console errors:
- `e2e_smoke.py`: all pages load; persona sign-in; WebSocket open; search.
- `e2e_checkout.py pay`: order confirmed in ~9 s; NAT → VoltPay → webhook → SendTaskSuccess → Aurora → OrderPlaced → WebSocket;
  fulfillment over MQ → VPN → 3PL; ShipmentDispatched back through Pipes; email and SMS (simulators); 59 panel entries.
- `e2e_checkout.py decline` (compensation in ~3 s) and `none` (timeout 120 s → compensation).
- `e2e_admin_lab.py`: demo admin password + TOTP; product save → zero-ETL search finds it in ~12 s; presigned upload → resize;
  report tabs; lesson opened from a panel entry (big picture 200 documents, hits marked, nested tree, DynamoDB source next to it).
- `e2e_experiments.py`: duplicate OrderPlaced stopped by 3 consumers; broken email consumer → DLQ (2) → fix → redrive → emails sent;
  burst of 50.
- `e2e_tutorial.py`: Next to Finish on 9 pages, click point checked with elementFromPoint, Close/Finish give display none.

Cost while deployed (AWS Price List, eu-central-1, idle): MQ cluster m7g.large $0.98/h, MSK Serverless $0.90/h + partitions,
OpenSearch Serverless with standby ≥ 2 OCU × $0.339/h, OpenSearch Ingestion ≥ 1 OCU × $0.31/h, Aurora 3 × 0.5 ACU × $0.14/h,
RDS Proxy, 3 NAT, 27 interface endpoint ENIs, VPN, EC2 t4g.small. About $3.7-4.4 per hour (~$90-105 per day). `tools/destroy.sh`
deletes these stacks; `tools/deploy.sh all` brings them back (~45 min, seed runs again).

Known gaps / next steps (after v1):
- Phase 5 says "sample lesson → user approval → the rest": all 18 lessons exist in `web/data/lessons/lessons.json`; the user has not
  reviewed the sample lesson (`fanout`) yet. Alternatives tables were checked against AWS docs for the main claims; review each table again.
- Lessons per service (decision 21) are covered by the pattern lessons; no separate short service lessons yet.
- Schema registry tab is empty until discovery creates `discovered-schemas`.
- The back-office queue has no consumer by design (it collects copies; 4-day retention).
- Participant guide (`guide/`) not started (decision 17).
- Visual polish pass with `frontend-design` not done beyond the base design (decision 7 left the look to Claude).
