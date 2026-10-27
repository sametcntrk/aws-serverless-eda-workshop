#!/usr/bin/env python3
"""E-commerce on AWS (serverless core + event-driven backbone): 5-page draw.io file in aws-arch-diagram-sc style.

Source of truth: SHARED-UNDERSTANDING.md (§10 = layout v2). Layered bands: global edge, API, microservices,
orchestration & event backbone, data, VPC (3 AZs x public / private-app / private-data subnets).
Page 1: grey map of every connection + the main customer journey (14 numbered steps).
Pages 2-5: the same skeleton; components that the page flows do not use are grey (faded=1). Every flow is one
scenario (own color, steps restart at 1) with an event walk band under the cloud.

Usage: python3 gen_ecommerce_eda.py OUT.drawio
"""
import sys
from xml.sax.saxutils import escape

OUT = sys.argv[1]
F = "fontFamily=Helvetica;"
PTS = ("points=[[0,0,0],[0.25,0,0],[0.5,0,0],[0.75,0,0],[1,0,0],[0,1,0],[0.25,1,0],[0.5,1,0],[0.75,1,0],[1,1,0],"
       "[0,0.25,0],[0,0.5,0],[0,0.75,0],[1,0.25,0],[1,0.5,0],[1,0.75,0]];")
GPTS = ("points=[[0,0],[0.25,0],[0.5,0],[0.75,0],[1,0],[1,0.25],[1,0.5],[1,0.75],[1,1],[0.75,1],[0.5,1],[0.25,1],"
        "[0,1],[0,0.75],[0,0.5],[0,0.25]];")
SPAN = "color: light-dark(rgb(0,0,0), rgb(255,255,255));"

CAT = {  # tint, stroke, icon fill
    "net": ("#EDE7F6", "#8C4FFF", "#8C4FFF"),
    "compute": ("#FFF2E8", "#ED7100", "#ED7100"),
    "db": ("#F5E6F7", "#C925D1", "#C925D1"),
    "storage": ("#E8F5E9", "#3F8624", "#7AA116"),
    "sec": ("#FFEBEE", "#DD344C", "#DD344C"),
    "int": ("#FCE4EC", "#E7157B", "#E7157B"),
    "ana": ("#EDE7F6", "#8C4FFF", "#8C4FFF"),
    "biz": ("#FFEBEE", "#DD344C", "#DD344C"),
}
GREY_C = "faded=1;fillColor=light-dark(#F2F2F2,#2B2B2B);strokeColor=#C4C4C4;fontColor=#A6A6A6;"

cells = []


def a(s):
    return escape(s, {'"': "&quot;"})


def vertex(cid, value, style, x, y, w, h, parent="1", extra=""):
    cells.append(
        f'<mxCell id="{cid}" value="{a(value)}" style="{a(style)}" vertex="1" parent="{parent}"{extra}>'
        f'<mxGeometry x="{round(x)}" y="{round(y)}" width="{round(w)}" height="{round(h)}" as="geometry"/></mxCell>')



# ------------------------------------------------------------------ geometry (layout v2, SHARED-UNDERSTANDING.md §10)
LEFT_X, LP_W = 40, 660                       # left legend panel
ACT_X, ACT_W = 720, 180                      # left actors
CLOUD_X, CLOUD_Y = 960, 150
X0, PITCH = 1050, 220


def C(k):
    """x of a 120x120 service container in column k."""
    return X0 + PITCH * k


REGION_X = 990
Y_E, Y_A, Y_M, Y_B1, Y_B2, Y_D = 232, 490, 690, 890, 1060, 1260   # icon rows: edge, API, MS, backbone 1+2, data
EDGE_FRAME = (REGION_X + 20, 206, 900, 204)                       # x, y, w, h (global edge band, outside the Region)
REGION_Y = 420
AUX_X, AUX_Y, AUX_W, AUX_H = C(11) + 180, Y_A - 36, 300, (Y_M + 134) - (Y_A - 36)
REGION_R = AUX_X + AUX_W + 40
BAND_X = REGION_X + 20
BANDS = [  # id, title, y, h, color, right edge
    ("api", "API", Y_A - 36, 170, "#8C4FFF", AUX_X - 20),
    ("ms", "Microservices (Lambda outside the VPC)", Y_M - 36, 170, "#ED7100", AUX_X - 20),
    ("bb", "Orchestration & event backbone", Y_B1 - 36, (Y_B2 + 134) - (Y_B1 - 36), "#E7157B", REGION_R - 20),
    ("data", "Data", Y_D - 36, 170, "#C925D1", REGION_R - 20),
]
VPC_X, VPC_Y = 1060, 1430
VPC_R = REGION_R - 30
VPC_W = VPC_R - VPC_X
AZ_Y = 1530
PUB_Y, PUB_H = AZ_Y + 36, 160
APP_Y, APP_H = PUB_Y + PUB_H + 20, 170
DAT_Y, DAT_H = APP_Y + APP_H + 20, 190
AZ_H = DAT_Y + DAT_H + 20 - AZ_Y
VPC_H = AZ_Y + AZ_H + 30 - VPC_Y
AZ_W = (VPC_W - 80) // 3
AZ_X = [VPC_X + 20 + i * (AZ_W + 20) for i in range(3)]
VGW_Y = VPC_Y + VPC_H - 60
REGION_H = VGW_Y + 120 + 20 - REGION_Y
CLOUD_H = REGION_Y + REGION_H + 40 - CLOUD_Y
CLOUD_B = CLOUD_Y + CLOUD_H
CLOUD_R = REGION_R + 40
RACT_X = CLOUD_R + 40                        # right actor (customer inbox and phone)
RP_X, RP_W = RACT_X + ACT_W + 40, 660        # right legend panel
TOTAL_W = RP_X + RP_W - LEFT_X


def azp(i, slot):
    """x of a container in slot 0..4 of AZ i."""
    return AZ_X[i] + 25 + 150 * slot


GEO = {}   # component id -> absolute (x, y, w, h) of its container

# id: (x, y, cat, shape, name, sub, category, res, h)
COMP = {
    "cf": (C(1), Y_E, "net", "cloudfront", "Amazon CloudFront", "shop.tdsynnexlab.link<br>SPA, /images/*, /api/*", "CDN", True, 160),
    "waf": (C(2), Y_E, "sec", "waf", "AWS WAF", "web ACL, managed rules", "Firewall"),
    "r53": (C(3), Y_E, "net", "route_53", "Amazon Route 53", "zone tdsynnexlab.link", "DNS"),
    "wsapi": (C(0), Y_A, "net", "api_gateway", "API Gateway", "WebSocket API<br>ws.shop.tdsynnexlab.link", "Push channel"),
    "apigw": (C(1), Y_A, "net", "api_gateway", "API Gateway", "REST API (regional)<br>validation, usage plans", "REST API"),
    "cognito": (C(2), Y_A, "sec", "cognito", "Amazon Cognito", "user pool,<br>group admins (MFA)", "Identity"),
    "lws": (C(0), Y_M, "compute", "lambda", "Lambda ws", "connect, authorizer,<br>push", "Microservice"),
    "lprod": (C(1), Y_M, "compute", "lambda", "Lambda product", "search, catalog admin,<br>upload URL", "Microservice"),
    "lcart": (C(2), Y_M, "compute", "lambda", "Lambda cart", "cart API", "Microservice"),
    "lhook": (C(3), Y_M, "compute", "lambda", "Lambda webhook", "payment callback,<br>signature check", "Microservice"),
    "lresize": (C(5), Y_M, "compute", "lambda", "Lambda resize", "image sizes", "Microservice"),
    "lcount": (C(6), Y_M, "compute", "lambda", "Lambda counters", "MSK consumer group<br>counters", "Consumer"),
    "larch": (C(7), Y_M, "compute", "lambda", "Lambda archive", "MSK consumer group<br>archive", "Consumer"),
    "lsms": (C(8), Y_M, "compute", "lambda", "Lambda sms", "notification service", "Microservice"),
    "lmail": (C(10), Y_M, "compute", "lambda", "Lambda email", "notification service", "Microservice"),
    "sfn": (C(3), Y_B1, "int", "step_functions", "Step Functions", "checkout-saga<br>(Standard)", "Workflow"),
    "eb": (C(4), Y_B1, "int", "eventbridge", "EventBridge", "bus commerce: archive,<br>replay, schemas", "Event bus"),
    "sns": (C(7), Y_B1, "int", "sns", "Amazon SNS", "order-notifications", "Topic"),
    "sqssms": (C(8), Y_B1, "int", "sqs", "Amazon SQS", "SMS queue", "Queue"),
    "eum": (C(9), Y_B1, "biz", "end_user_messaging", "End User Messaging", "SMS", "SMS"),
    "sqsmail": (C(10), Y_B1, "int", "sqs", "Amazon SQS", "email queue", "Queue"),
    "ses": (C(11), Y_B1, "biz", "simple_email_service", "Amazon SES", "templates,<br>configuration set", "Email"),
    "pipes": (C(0), Y_B2, "int", "eventbridge_pipes", "EventBridge Pipes", "MQ source, filter", "Pipe", False),
    "sqsbuf": (C(3), Y_B2, "int", "sqs", "Amazon SQS", "order buffer", "Queue"),
    "busdef": (C(5), Y_B2, "int", "eventbridge_default_event_bus_resource", "Default event bus", "S3 and SES events", "Event bus", False),
    "dlq": (C(6), Y_B2, "int", "sqs", "Amazon SQS", "DLQs (one per<br>rule target)", "Dead-letter"),
    "sqsbo": (C(7), Y_B2, "int", "sqs", "Amazon SQS", "back-office queue", "Queue"),
    "osis": (C(0), Y_D, "ana", "opensearch_ingestion", "OpenSearch Ingestion", "zero-ETL pipeline", "Sync", False),
    "aoss": (C(1), Y_D, "ana", "elasticsearch_service", "OpenSearch Serverless", "search collection,<br>standby replicas", "Search"),
    "ddb": (C(2), Y_D, "db", "dynamodb", "Amazon DynamoDB", "catalog, cart, stock,<br>idempotency, counters,<br>ws-connections", "Key-value"),
    "s3web": (C(4), Y_D, "storage", "s3", "Amazon S3", "web bucket: SPA,<br>resized images (OAC)", "Static origin"),
    "s3up": (C(5), Y_D, "storage", "s3", "Amazon S3", "uploads bucket:<br>original images", "Uploads"),
    "s3lake": (C(6), Y_D, "storage", "s3", "Amazon S3", "data lake<br>(clickstream, events)", "Data lake"),
    # auxiliary column (no arrows)
    "secrets": (AUX_X + 30, AUX_Y + 40, "sec", "secrets_manager", "Secrets Manager", "MQ, Aurora,<br>provider key", "Auxiliary"),
    "kms": (AUX_X + 160, AUX_Y + 40, "sec", "key_management_service", "AWS KMS", "customer<br>managed keys", "Auxiliary"),
    "cw": (AUX_X + 30, AUX_Y + 200, "int", "cloudwatch_2", "CloudWatch", "alarms: DLQ, Pipes,<br>ESM errors", "Auxiliary"),
    "xray": (AUX_X + 160, AUX_Y + 200, "int", "xray", "AWS X-Ray", "tracing,<br>Powertools", "Auxiliary"),
    # VPC edges
    "igw": (VPC_X - 60, PUB_Y + 34, "net", "internet_gateway", "Internet gateway", "igw-shop", "Gateway", False),
    "vgw": (azp(0, 2), VGW_Y, "net", "vpn_gateway", "Virtual private gateway", "vgw-shop, Site-to-Site VPN", "Gateway", False),
    "vpcegw": (VPC_R - 300, VPC_Y - 30, "net", "endpoints", "Gateway endpoints", "S3, DynamoDB", "VPC endpoint", False),
}
_AURORA = ["Aurora writer", "Aurora reader", "Aurora reader 2"]
for i, az in enumerate("abc"):
    sfx = "" if az == "a" else az
    COMP[f"nat{az}"] = (azp(i, 1), PUB_Y + 34, "net", "nat_gateway", f"NAT gateway {az}", f"nat-{az}", "NAT", False)
    COMP[f"lorder{sfx}"] = (azp(i, 0), APP_Y + 34, "compute", "lambda", "Lambda order", "ENI", "Microservice")
    COMP[f"lpay{sfx}"] = (azp(i, 1), APP_Y + 34, "compute", "lambda", "Lambda payment", "ENI", "Microservice")
    COMP[f"lful{sfx}"] = (azp(i, 2), APP_Y + 34, "compute", "lambda", "Lambda fulfillment", "ENI", "Microservice")
    COMP[f"lprodc{sfx}"] = (azp(i, 3), APP_Y + 34, "compute", "lambda", "Lambda producer", "ENI", "Microservice")
    COMP[f"vpce{sfx}"] = (azp(i, 4), APP_Y + 34, "net", "endpoints", "Interface endpoints", "ENIs: EventBridge, SFN,<br>SNS, SQS, Secrets, STS, Logs", "VPC endpoint", False)
    COMP[f"proxy{sfx}"] = (azp(i, 0), DAT_Y + 34, "db", "rds_proxy", "RDS Proxy", "ENI, IAM auth", "Connection pool", False)
    COMP[f"aur{az}"] = (azp(i, 1), DAT_Y + 34, "db", "aurora_instance", _AURORA[i], "Serverless v2,<br>PostgreSQL", "Database", False)
    COMP[f"mq{az}"] = (azp(i, 2), DAT_Y + 34, "int", "mq_broker", f"MQ node {az}", "RabbitMQ cluster", "Broker", False)
    COMP[f"msk{sfx}"] = (azp(i, 3), DAT_Y + 34, "ana", "managed_streaming_for_kafka", "MSK Serverless", "ENI", "Streaming")

ACTORS = {  # id: (x, y, w, h, title, icon, text)
    "users-customer": (ACT_X, 166, ACT_W, 664, "Customer", "users", "Web SPA in the browser<br>(shop.tdsynnexlab.link)"),
    "users-admin": (ACT_X, 860, ACT_W, 200, "Back-office admin", "users", "admin pages, MFA"),
    "ext-payment": (ACT_X, PUB_Y + 14, ACT_W, 160, "Payment provider", "internet_alt2", "HTTPS API + webhooks<br>198.51.100.40"),
    "users-inbox": (RACT_X, Y_B1 - 30, ACT_W, 230, "Customer inbox and phone", "users", "email and SMS<br>of the customer"),
}
P3PL = ("onprem-3pl", azp(0, 2) + 60 - 130, CLOUD_B + 40, 260, 170)

for k, v in COMP.items():
    h = v[8] if len(v) > 8 else 120
    GEO[k] = (v[0], v[1], 120, h)
for k, v in ACTORS.items():
    GEO[k] = v[:4]
GEO["onprem-3pl"] = P3PL[1:]


def node_id(k):
    return f"grp-{k}" if k in COMP else k


# ------------------------------------------------------------------ drawing primitives
def svc(k, faded):
    x, y, cat, shape, name, sub, category = COMP[k][:7]
    res = COMP[k][7] if len(COMP[k]) > 7 else True
    h = GEO[k][3]
    tint, stroke, fill = CAT[cat]
    if faded:
        cstyle = (GREY_C + "rounded=1;whiteSpace=wrap;html=1;verticalAlign=top;fontStyle=1;fontSize=11;" + F +
                  "container=1;collapsible=0;shadow=0;strokeWidth=1;spacingTop=-2;")
        fill, fcol = "#C4C4C4", "#A6A6A6"
        pre = "faded=1;"
    else:
        cstyle = (f"fillColor={tint};strokeColor={stroke};rounded=1;whiteSpace=wrap;html=1;verticalAlign=top;fontStyle=1;fontSize=11;"
                  f"fontColor={stroke};{F}container=1;collapsible=0;shadow=1;strokeWidth=1.5;spacingTop=-2;")
        fcol, pre = "#232F3E", ""
    vertex(f"grp-{k}", category, cstyle, x, y, 120, h)
    label = name + (f"<div><i>{sub}</i></div>" if sub else "")
    if res:
        st = (f"{pre}sketch=0;{PTS}outlineConnect=0;fontColor={fcol};fillColor={fill};strokeColor=#ffffff;dashed=0;"
              f"verticalLabelPosition=bottom;verticalAlign=top;align=center;html=1;fontSize=10;fontStyle=0;aspect=fixed;"
              f"shape=mxgraph.aws4.resourceIcon;resIcon=mxgraph.aws4.{shape};{F}" + ("" if faded else "shadow=1;"))
    else:
        st = (f"{pre}sketch=0;outlineConnect=0;fontColor={fcol};gradientColor=none;fillColor={fill};strokeColor=none;dashed=0;"
              f"verticalLabelPosition=bottom;verticalAlign=top;align=center;html=1;fontSize=10;fontStyle=0;aspect=fixed;"
              f"pointerEvents=1;shape=mxgraph.aws4.{shape};{F}")
    vertex(k, label, st, 36, 20 if h == 120 else 60, 48, 48, parent=f"grp-{k}")


def actor(k, faded):
    x, y, w, h, title, icon, text = ACTORS[k]
    pre = "faded=1;" if faded else ""
    fcol = "#A6A6A6" if faded else "#333333"
    vertex(k, title, f"{pre}fillColor=#f5f5f5;strokeColor=light-dark(#666666,#D4D4D4);rounded=1;whiteSpace=wrap;html=1;verticalAlign=top;"
           f"fontStyle=1;fontSize=12;fontColor={fcol};{F}container=1;collapsible=0;shadow=1;strokeWidth=1;", x, y, w, h)
    vertex(f"{k}-icon", "", f"{pre}sketch=0;{PTS}outlineConnect=0;fontColor=#232F3E;fillColor={'#C4C4C4' if faded else '#232F3D'};"
           "strokeColor=#ffffff;dashed=0;verticalLabelPosition=bottom;verticalAlign=top;align=center;html=1;fontSize=12;fontStyle=0;"
           f"aspect=fixed;shape=mxgraph.aws4.resourceIcon;resIcon=mxgraph.aws4.{icon};{F}", (w - 48) // 2, 30, 48, 48, parent=k)
    vertex(f"{k}-text", text, f"{pre}text;html=1;align=center;verticalAlign=top;fontSize=10;whiteSpace=wrap;fontColor={fcol};{F}",
           6, 82, w - 12, 40, parent=k)


def onprem(faded):
    cid, x, y, w, h = P3PL
    pre = "faded=1;" if faded else ""
    vertex(cid, "3PL warehouse network<br>172.16.0.0/16",
           f"{pre}{GPTS}outlineConnect=0;gradientColor=none;html=1;whiteSpace=wrap;fontSize=12;fontStyle=1;shape=mxgraph.aws4.group;"
           "grIcon=mxgraph.aws4.group_corporate_data_center;strokeColor=light-dark(#7D8998,#D4D4D4);fillColor=none;verticalAlign=top;"
           f"align=left;spacingLeft=30;fontColor={'#A6A6A6' if faded else 'light-dark(#5A6C86,#D4D4D4)'};dashed=0;container=1;"
           f"pointerEvents=0;collapsible=0;recursiveResize=0;{F}", x, y, w, h)
    vertex("onprem-wms", "Legacy WMS<div><i>AMQP client, 172.16.10.5<br>customer gateway</i></div>",
           f"{pre}sketch=0;outlineConnect=0;fontColor={'#A6A6A6' if faded else '#232F3E'};gradientColor=none;"
           f"fillColor={'#C4C4C4' if faded else '#232F3D'};strokeColor=none;dashed=0;verticalLabelPosition=bottom;verticalAlign=top;"
           f"align=center;html=1;fontSize=10;aspect=fixed;pointerEvents=1;shape=mxgraph.aws4.traditional_server;{F}",
           (w - 30) // 2, 50, 30, 48, parent=cid)


def group(cid, label, kind, x, y, w, h):
    styles = {
        "cloud": "grIcon=mxgraph.aws4.group_aws_cloud;strokeColor=#232F3E;fillColor=light-dark(#232F3E0D,#232F3E0D);fontColor=#232F3E;dashed=0;container=1;fontSize=14;fontStyle=1;",
        "region": "grIcon=mxgraph.aws4.group_region;strokeColor=#00A4A6;fillColor=light-dark(#0C7B7D0D,#0C7B7D0D);fontColor=#00A4A6;dashed=1;container=0;fontSize=14;fontStyle=1;",
        "vpc": "grIcon=mxgraph.aws4.group_vpc2;strokeColor=#8C4FFF;fillColor=light-dark(#8C4FFF0D,#8C4FFF0D);fontColor=#8C4FFF;dashed=0;container=1;fontSize=13;fontStyle=1;",
        "pub": "grIcon=mxgraph.aws4.group_public_subnet;strokeColor=#248814;fillColor=light-dark(#2488140D,#2488140D);fontColor=#248814;dashed=0;container=1;fontSize=11;fontStyle=0;",
        "priv": "grIcon=mxgraph.aws4.group_private_subnet;strokeColor=#147EBA;fillColor=light-dark(#147EBA0D,#147EBA0D);fontColor=#147EBA;dashed=0;container=1;fontSize=11;fontStyle=0;",
    }
    if kind == "az":
        st = ("fillColor=none;strokeColor=#147EBA;dashed=1;verticalAlign=top;align=left;spacingLeft=10;fontStyle=1;fontSize=12;"
              "fontColor=#147EBA;whiteSpace=wrap;html=1;container=1;pointerEvents=0;collapsible=0;recursiveResize=0;" + F)
    elif kind == "aux":
        st = ("rounded=0;fillColor=none;dashed=1;verticalAlign=top;align=left;spacingLeft=10;html=1;fontSize=12;fontStyle=1;"
              "strokeColor=#666666;fontColor=#666666;whiteSpace=wrap;container=1;pointerEvents=0;collapsible=0;" + F)
    else:
        st = (f"{GPTS}outlineConnect=0;gradientColor=none;html=1;whiteSpace=wrap;shape=mxgraph.aws4.group;fillStyle=auto;"
              f"verticalAlign=top;align=left;spacingLeft=30;pointerEvents=0;collapsible=0;recursiveResize=0;{styles[kind]}{F}")
    vertex(cid, label, st, x, y, w, h)


def rt_box(cid, name, rows, x, y, w):
    trs = "".join(f'<tr><td style="padding:1px 4px">{d}</td><td style="padding:1px 4px">{t}</td></tr>' for d, t in rows)
    html = (f'<b style="color:#8C4FFF">Route table: {name}</b>'
            f'<table style="width:{w - 12}px;font-size:10px;border-collapse:collapse;margin-top:2px">'
            f'<tr style="background:#E6E6E6;color:#333333"><td style="padding:1px 4px"><b>Destination</b></td>'
            f'<td style="padding:1px 4px"><b>Target</b></td></tr>{trs}</table>')
    h = 22 + 15 * (len(rows) + 1) + 6 + (14 if w < 200 else 0)
    vertex(cid, html, "text;html=1;whiteSpace=wrap;align=left;verticalAlign=top;strokeColor=#8C4FFF;rounded=0;"
           "fillColor=light-dark(#FFFFFF,#1E1E1E);spacing=4;fontSize=10;" + F, x, y, w, h)
    return h


# ------------------------------------------------------------------ edges and badges
def point(k, side, coord=None):
    x, y, w, h = GEO[k]
    if side == "R":
        c = y + h / 2 if coord is None else coord
        return (x + w, c), (1, (c - y) / h)
    if side == "L":
        c = y + h / 2 if coord is None else coord
        return (x, c), (0, (c - y) / h)
    if side == "T":
        c = x + w / 2 if coord is None else coord
        return (c, y), ((c - x) / w, 0)
    c = x + w / 2 if coord is None else coord
    return (c, y + h), ((c - x) / w, 1)


def fr(v):
    return f"{v:.4f}".rstrip("0").rstrip(".")


def badge(cid, label, x, y, fill, size=None):
    w = size or (28 if len(label) == 1 else 36)
    vertex(cid, label, f"rounded=1;whiteSpace=wrap;html=1;fillColor={fill};strokeColor=default;fontColor=#FFFFFF;fontStyle=1;"
           f"fontSize=15;{F}shadow=1;glass=0;strokeWidth=2;align=center;verticalAlign=middle;labelBackgroundColor=none;",
           x, y, w, 28)


def edge(cid, src, tgt, color, ex, en, pts=(), dashed=False, dotted=False, width=2, arrow=True):
    (sx, sy), (efx, efy) = point(src, *ex)
    _, (nfx, nfy) = point(tgt, *en)
    st = (f"edgeStyle=orthogonalEdgeStyle;html=1;endArrow={'block' if arrow else 'none'};startArrow=none;endFill=1;"
          f"strokeColor={color};rounded=0;strokeWidth={width};jumpStyle=arc;jumpSize=10;{F}"
          f"exitX={fr(efx)};exitY={fr(efy)};exitDx=0;exitDy=0;entryX={fr(nfx)};entryY={fr(nfy)};entryDx=0;entryDy=0;")
    if dashed:
        st += "dashed=1;dashPattern=8 4;"
    if dotted:
        st += "dashed=1;dashPattern=2 3;"
    p = "".join(f'<mxPoint x="{round(px)}" y="{round(py)}"/>' for px, py in pts)
    arr = f'<Array as="points">{p}</Array>' if pts else ""
    cells.append(f'<mxCell id="{cid}" style="{a(st)}" edge="1" parent="1" source="{node_id(src)}" target="{node_id(tgt)}">'
                 f'<mxGeometry relative="1" as="geometry">{arr}</mxGeometry></mxCell>')
    return (sx, sy), ex[0]


def step_badge(cid, label, start, side, fill):
    (px, py) = start
    w = 28 if len(label) == 1 else 36
    pos = {"R": (px + 17, py - 33), "L": (px - 17 - w, py - 33), "B": (px + 7, py + 17), "T": (px + 7, py - 45)}[side]
    badge(cid, label, *pos, fill)


# ------------------------------------------------------------------ text height estimate
def est_lines(text, width, px=12):
    import re
    plain = re.sub(r"<br\s*/?>|</div>|</p>|</tr>", "\n", text)
    plain = re.sub(r"<[^>]+>", "", plain)
    per = max(10, int(width / (px * 0.53)))
    n = 0
    for para in plain.split("\n"):
        n += max(1, -(-len(para) // per)) if para.strip() else 0
    return max(n, 1)


# ------------------------------------------------------------------ legend panels
def legend_panel(sfx, x, y, w, h, blocks):
    """blocks: ("scen", scenario dict) or ("box", id, html, stroke)."""
    vertex(f"legend-bg-{sfx}", "", "verticalLabelPosition=bottom;verticalAlign=top;html=1;shape=mxgraph.basic.rect;fillColor2=none;"
           "strokeWidth=1;size=20;indent=5;fillColor=light-dark(#EDF3FF,#305363);strokeColor=#6c8ebf;", x, y, w, h)
    cw = w - 40
    cont = f"legend-container-{sfx}"
    vertex(cont, "", "group", x + 20, y + 20, cw, h - 40, extra=' connectable="0"')
    yy = 0
    for b in blocks:
        if b[0] == "box":
            _, bid, html, stroke = b
            bh = est_lines(html, cw - 16) * 16 + 20 + (40 if "<table" in html else 0)
            vertex(f"legend-{bid}-{sfx}", f'<div style="{SPAN}">{html}</div>',
                   f"text;html=1;align=left;verticalAlign=top;fontSize=12;labelBackgroundColor=none;whiteSpace=wrap;rounded=1;"
                   f"strokeColor={stroke};dashed=1;spacing=8;fillColor=none;{F}", 0, yy, cw, bh, parent=cont)
            yy += bh + 14
            continue
        s = b[1]
        head = (f'<div style="font-size:16px;color:{s["color"]}"><b>{s["title"]}</b></div>'
                f'<div style="{SPAN}">{s["who"]}</div>')
        if s.get("needs"):
            head += f'<div style="{SPAN}"><i>{s["needs"]}</i></div>'
        hh = est_lines(head, cw, 12) * 16 + 14
        vertex(f"legend-head-{s['key']}-{sfx}", head, "text;html=1;align=left;verticalAlign=top;spacingTop=-4;fontSize=12;"
               "labelBackgroundColor=none;whiteSpace=wrap;" + F, 0, yy, cw, hh, parent=cont)
        yy += hh + 4
        for st in s["steps"]:
            lab, title, text = st["label"], st["title"], st["text"]
            body = f'<div><b>{title}</b></div><div><span style="{SPAN}">{text}</span></div>'
            sh = max(40, est_lines(body, cw - 52, 12) * 16 + 6)
            g = f"step-{s['key']}-{lab}-legend"
            vertex(g, "", "group;" + F, 0, yy, cw, sh, parent=cont, extra=' connectable="0"')
            vertex(f"step-{s['key']}-{lab}-badge-legend", lab,
                   f"rounded=1;whiteSpace=wrap;html=1;fillColor={s['color']};strokeColor=default;fontColor=#FFFFFF;fontStyle=1;"
                   "fontSize=15;labelBackgroundColor=none;" + F + "shadow=1;glass=0;strokeWidth=2;", 0, 0, 40, 30, parent=g)
            vertex(f"step-{s['key']}-{lab}-desc-legend", body,
                   "text;html=1;align=left;verticalAlign=top;spacingTop=-4;fontSize=12;labelBackgroundColor=none;whiteSpace=wrap;" + F,
                   52, 0, cw - 52, sh, parent=g)
            yy += sh + 6
        yy += 14
    return yy + 40


# ------------------------------------------------------------------ event walk
def event_walk(s, x, y, w):
    n = len(s["steps"])
    gap = 34
    cw = min(420, (w - 40 - (n - 1) * gap) / n)
    lines = [st["card"] for st in s["steps"]]
    card_h = max(est_lines("<br>".join(c), cw - 12, 11) * 15 + 34 for c in lines)
    H = 89 + card_h + 16
    col = s["color"]
    vertex(f"frame-walk-{s['key']}", "", f"rounded=1;whiteSpace=wrap;html=1;fillColor=none;strokeColor={col};dashed=1;" + F, x, y, w, H)
    vertex(f"walk-{s['key']}-title", f'<b style="color:{col}">{s["title"]} - event walk</b>'
           f'<span style="{SPAN}"> (one card per step: the request or event at that point)</span>',
           "text;html=1;align=left;verticalAlign=top;fontSize=13;labelBackgroundColor=none;whiteSpace=wrap;" + F, x + 14, y + 6, w - 28, 22)
    prev = None
    for i, st in enumerate(s["steps"]):
        cx = x + 20 + i * (cw + gap)
        cid = f"walk-{s['key']}-hdr{i}"
        src_lab = NAMES.get(st["src"], st["src"])
        tgt_lab = NAMES.get(st["tgt"], st["tgt"])
        body = f"<b>{src_lab} → {tgt_lab}</b><br>" + "<br>".join(st["card"])
        vertex(cid, body, "text;html=1;align=left;verticalAlign=top;fontSize=11;whiteSpace=wrap;rounded=1;strokeColor=#545B64;"
               "fillColor=light-dark(#FFFFFF,#1E1E1E);spacing=6;" + F, cx, y + 89, cw, card_h)
        badge(f"walk-{s['key']}-b{i}", st["label"], cx, y + 44, col)
        if prev:
            cells.append(f'<mxCell id="walk-{s["key"]}-e{i}" style="{a("edgeStyle=orthogonalEdgeStyle;html=1;endArrow=block;endFill=1;strokeColor=" + col + ";strokeWidth=2;" + F + "exitX=1;exitY=0.5;entryX=0;entryY=0.5;")}" '
                         f'edge="1" parent="1" source="{prev}" target="{cid}"><mxGeometry relative="1" as="geometry"/></mxCell>')
        prev = cid
    return H


NAMES = {
    "users-customer": "Customer", "users-admin": "Admin", "ext-payment": "Payment provider", "users-inbox": "Customer inbox/phone",
    "onprem-3pl": "3PL WMS", "r53": "Route 53", "cf": "CloudFront", "waf": "WAF", "wsapi": "WebSocket API", "s3web": "S3 web bucket",
    "cognito": "Cognito", "s3up": "S3 uploads bucket", "lws": "Lambda ws", "apigw": "REST API", "busdef": "Default bus",
    "aoss": "OpenSearch", "lprod": "Lambda product", "lcart": "Lambda cart", "lhook": "Lambda webhook", "lresize": "Lambda resize",
    "osis": "OpenSearch Ingestion", "ddb": "DynamoDB", "sfn": "Step Functions", "sns": "SNS topic", "eb": "Bus commerce",
    "pipes": "Pipe", "sqsmail": "SQS email", "sqssms": "SQS sms", "sqsbo": "SQS back office", "sqsbuf": "SQS order buffer",
    "lmail": "Lambda email", "lsms": "Lambda sms", "dlq": "SQS DLQ", "lcount": "Lambda counters", "ses": "SES",
    "eum": "End User Messaging", "larch": "Lambda archive", "s3lake": "S3 data lake", "lpay": "Lambda payment",
    "proxy": "RDS Proxy", "lorder": "Lambda order", "lful": "Lambda fulfillment", "lprodc": "Lambda producer", "msk": "MSK",
    "igw": "Internet gateway", "vgw": "Virtual private gateway", "nata": "NAT gateway a", "mqa": "MQ node a", "aura": "Aurora writer",
}


# ------------------------------------------------------------------ handy coordinates
def cx(k):
    return GEO[k][0] + GEO[k][2] / 2


def cy(k):
    return GEO[k][1] + GEO[k][3] / 2


def top(k):
    return GEO[k][1]


def bot(k):
    return GEO[k][1] + GEO[k][3]


def lft(k):
    return GEO[k][0]


def rgt(k):
    return GEO[k][0] + GEO[k][2]


L_R0R1, L_R1R2, L_R2R3, L_R3R4 = 455, 785, 1015, 1265


def S(label, src, tgt, ex, en, title, text, card, pts=(), dashed=False, b=None):
    return dict(label=label, src=src, tgt=tgt, ex=ex, en=en, title=title, text=text, card=card, pts=pts, dashed=dashed, b=b)


COLORS = ["#007CBD", "#ED7100", "#7AA116", "#C925D1", "#3F8624", "#E7157B", "#00A4A6", "#545B64"]

# ================================================================== PAGE CONTENT
CUS, ADM = "users-customer", "users-admin"

P2 = [
    dict(title="Scenario 1 - The browser loads the SPA",
         who="The customer browser starts this flow. It needs the static files of the single-page application (SPA).",
         steps=[
             S("1", CUS, "r53", ("R", 310), ("L", 310), "DNS lookup",
               "The browser asks for shop.tdsynnexlab.link. Route 53 answers with an alias record that points to the CloudFront distribution.",
               ["DNS query: shop.tdsynnexlab.link (A, AAAA)", "Answer: alias to dxxxx.cloudfront.net"]),
             S("2", CUS, "cf", ("R", 545), ("L", 545), "HTTPS request",
               "The browser sends GET / over HTTPS. AWS WAF checks the request at CloudFront. CloudFront sends a cached copy when it has one.",
               ["HTTPS GET /", "Host: shop.tdsynnexlab.link", "TLS certificate: ACM in us-east-1"]),
             S("3", "cf", "s3web", ("B", 1240), ("L", 890), "Origin request on a cache miss",
               "CloudFront signs the request with origin access control (OAC). Only CloudFront can read the bucket. "
               "Return path: S3 → CloudFront → browser.",
               ["S3 GetObject /index.html", "Authorization: SigV4 (OAC)", "Response: 200 with Cache-Control"], pts=[(1240, 890)]),
         ]),
    dict(title="Scenario 2 - The customer signs in",
         who="The customer browser starts this flow. It needs tokens for the protected APIs.",
         steps=[
             S("1", CUS, "cognito", ("R", 1140), ("L", 1140), "Sign-in",
               "The SPA sends the email and the password to the Cognito user pool with SRP. Cognito asks for MFA when the customer "
               "turned it on. Return path: Cognito sends the ID, access and refresh tokens (JWT) to the browser.",
               ["InitiateAuth USER_SRP_AUTH", "USERNAME = email, SRP_A", "Result: IdToken, AccessToken, RefreshToken"]),
         ]),
    dict(title="Scenario 3 - The customer searches for products",
         who="The customer browser starts this flow. Search is public and needs no token.",
         needs="Needs: Scenario 1 (the SPA runs in the browser).",
         steps=[
             S("1", CUS, "cf", ("R", 590), ("L", 590), "Search request",
               "The SPA sends GET /api/products?q=laptop. WAF checks the request. The /api/* cache behavior sends it to the REST API origin.",
               ["HTTPS GET /api/products?q=laptop&page=1", "Host: shop.tdsynnexlab.link"]),
             S("2", "cf", "apigw", ("R", 590), ("L", 590), "Origin request",
               "CloudFront sends the request to the regional REST API. The request validator checks the query parameters.",
               ["HTTPS GET /prod/products?q=laptop", "X-Forwarded-For: client IP"]),
             S("3", "apigw", "lprod", ("R", 590), ("L", 590), "Lambda proxy integration",
               "API Gateway invokes the product function. The event contains the full request.",
               ["Lambda event (proxy)", "httpMethod GET, path /products", "queryStringParameters.q = laptop"]),
             S("4", "lprod", "aoss", ("T", cx("lprod")), ("B", cx("aoss")), "Full-text search",
               "The function sends a search query to the products index. The index returns the matching SKUs.",
               ["POST /products/_search", "match name: laptop, size 20", "SigV4 (service aoss)"]),
             S("5", "lprod", "ddb", ("R", 580), ("L", 580), "Current price and stock",
               "The function reads price and stock for the SKUs with BatchGetItem. Return path: Lambda → API Gateway → CloudFront → browser.",
               ["BatchGetItem table catalog", "Keys: PK = SKU#123, ...", "ProjectionExpression price, stock"]),
         ]),
    dict(title="Scenario 4 - The customer adds an item to the cart",
         who="The signed-in customer starts this flow.",
         needs="Needs: Scenario 2 (the ID token).",
         steps=[
             S("1", CUS, "cf", ("R", 635), ("L", 635), "Cart request",
               "The SPA sends POST /api/cart/items. The Authorization header carries the ID token.",
               ["HTTPS POST /api/cart/items", "Authorization: Bearer &lt;ID token&gt;", "body {sku: SKU#123, qty: 1}"]),
             S("2", "cf", "apigw", ("R", 635), ("L", 635), "Token check",
               "The Cognito authorizer checks the signature and the expiry of the JWT. The request validator checks the JSON body.",
               ["Origin request /prod/cart/items", "authorizer: claims.sub = c-42"]),
             S("3", "apigw", "lcart", ("R", 635), ("L", 870), "Invoke",
               "API Gateway invokes the cart function. The event carries the token claims (sub is the customer ID).",
               ["Lambda event", "requestContext.authorizer.claims.sub = c-42", "body {sku, qty}"], pts=[(1880, 635), (1880, 870)]),
             S("4", "lcart", "ddb", ("R", 870), ("B", 2270), "Cart write",
               "The function updates the cart item and sets expiresAt. DynamoDB TTL deletes old carts. "
               "Return path: Lambda → API Gateway → CloudFront → browser.",
               ["UpdateItem table cart", "PK CART#c-42, SK SKU#123", "SET qty, expiresAt (TTL)"], pts=[(2270, 870)]),
         ]),
    dict(title="Scenario 5 - The browser opens the WebSocket",
         who="The browser opens this connection before the checkout. Page 3 uses it to push the checkout result.",
         needs="Needs: Scenario 2 (the ID token).",
         steps=[
             S("1", CUS, "r53", ("R", 355), ("L", 355), "DNS lookup",
               "The browser asks for ws.shop.tdsynnexlab.link. Route 53 answers with an alias to the custom domain of the WebSocket API.",
               ["DNS query: ws.shop.tdsynnexlab.link", "Answer: alias to the regional API domain (eu-central-1)"]),
             S("2", CUS, "wsapi", ("R", 440), ("B", 1440), "WebSocket upgrade",
               "The browser opens wss://ws.shop.tdsynnexlab.link with the token. A Lambda authorizer checks the Cognito token on the $connect route.",
               ["GET wss://ws.shop.tdsynnexlab.link/?token=&lt;JWT&gt;", "Upgrade: websocket", "TLS certificate: ACM in eu-central-1"],
               pts=[(1440, 440)]),
             S("3", "wsapi", "lws", ("R", 330), ("L", 330), "$connect route",
               "API Gateway invokes the ws function with the connection ID.",
               ["Lambda event, routeKey $connect", "connectionId = Ab12=", "authorizer.principalId = c-42"]),
             S("4", "lws", "ddb", ("B", 1740), ("T", 2300), "Store the connection",
               "The function writes the connection ID with the customer ID and a TTL. Return path: API Gateway sends "
               "101 Switching Protocols. The connection stays open.",
               ["PutItem table ws-connections", "PK CUST#c-42, connectionId Ab12=", "expiresAt (TTL)"],
               pts=[(1740, L_R0R1), (2300, L_R0R1)]),
         ]),
    dict(title="Scenario 6 - The customer starts the checkout",
         who="The signed-in customer starts this flow from the cart page.",
         needs="Needs: Scenario 4 (the cart) and Scenario 5 (the open WebSocket).",
         steps=[
             S("1", CUS, "cf", ("R", 680), ("L", 680), "Checkout request",
               "The SPA sends POST /api/checkout with the ID token and an Idempotency-Key header.",
               ["HTTPS POST /api/checkout", "Authorization: Bearer &lt;ID token&gt;", "Idempotency-Key: o-1001"]),
             S("2", "cf", "apigw", ("R", 680), ("L", 680), "Token check",
               "The Cognito authorizer checks the token. The request validator checks the body.",
               ["Origin request /prod/checkout", "authorizer: claims.sub = c-42"]),
             S("3", "apigw", "sfn", ("B", 1740), ("T", 2300), "Direct integration",
               "API Gateway calls StartExecution. The execution name is the Idempotency-Key, so a retry does not start a second saga. "
               "Return path: API Gateway sends 202 to the browser. Page 3 continues the saga.",
               ["StartExecution checkout-saga (Standard)", "name = o-1001", "input {orderId: o-1001, customerId: c-42, cartId}",
                "Response: 202 {executionArn}"], pts=[(1740, L_R2R3), (2300, L_R2R3)]),
         ]),
]

# Page 3 -------------------------------------------------------------------
SFN_T = top("sfn")
P3 = [
    dict(title="Scenario 1 - The saga reserves stock and asks for payment",
         who="The Step Functions Standard workflow checkout-saga starts this flow.",
         needs="Needs: page 2, Scenario 6 (the execution started).",
         steps=[
             S("1", "sfn", "ddb", ("T", 2300), ("B", 2300), "Reserve stock",
               "The workflow calls UpdateItem directly with the condition available >= qty. If the condition fails, the saga stops with OutOfStock.",
               ["UpdateItem table stock, PK SKU#123", "ConditionExpression available >= :qty", "SET available = available - :qty"], b=(2262, 880)),
             S("2", "sfn", "lpay", ("B", 2270), ("R", 1660), "Payment task with a task token",
               "The workflow invokes the payment function with .waitForTaskToken. Then the workflow waits for the callback. The wait has a 15-minute timeout.",
               ["Invoke payment-svc (.waitForTaskToken)", "Payload {orderId: o-1001, amount: 1299.00 EUR,", "taskToken: AQB...}"],
               pts=[(2270, 1490), (1700, 1490), (1700, 1660)], b=(2236, 1230)),
             S("3", "lpay", "ddb", ("T", 1620), ("B", 2264), "Store the task token",
               "The function writes the task token under the order ID. AWS delivers the request privately on the AWS backbone "
               "through the DynamoDB gateway endpoint.",
               ["PutItem table idempotency", "PK PAY#o-1001, taskToken AQB...", "expiresAt (TTL)"],
               pts=[(1620, L_R1R2), (2264, L_R1R2)], b=(1627, 1380)),
             S("4", "lpay", "nata", ("B", 1590), ("T", 1590), "Internet call from the VPC",
               "The function ENI sends the HTTPS request. Route table rtb-private-a sends 0.0.0.0/0 to nat-a.",
               ["HTTPS POST api.payments.example/v1/payments", "src 10.0.16.25 (Lambda ENI a private IP)",
                "dst 198.51.100.40 (provider public IP)"]),
             S("5", "nata", "igw", ("L", 1900), ("R", 1900), "SNAT by the NAT gateway",
               "The NAT gateway replaces the source with its private IP 10.0.0.10. Route table rtb-public-a sends 0.0.0.0/0 to igw-shop.",
               ["src 10.0.0.10 (NAT GW a private IP)", "dst 198.51.100.40 (provider public IP)", "SNAT by NAT GW a"]),
             S("6", "igw", "ext-payment", ("L", 1900), ("R", 1900), "Create the payment",
               "The internet gateway maps 10.0.0.10 to the Elastic IP 203.0.113.11. The provider uses the order ID as idempotency key. "
               "Return path: provider → IGW → NAT GW → Lambda. The workflow keeps waiting.",
               ["src 203.0.113.11 (NAT GW a Elastic IP)", "Idempotency-Key: o-1001", "metadata {orderId: o-1001}"]),
         ]),
    dict(title="Scenario 2 - The payment provider sends the webhook",
         who="The payment provider starts this flow when the payment succeeds or fails.",
         needs="Needs: Scenario 1 (the payment exists).",
         steps=[
             S("1", "ext-payment", "cf", ("R", 1850), ("B", 1220), "Webhook",
               "The provider sends POST /api/webhooks/payment to shop.tdsynnexlab.link. WAF checks the request.",
               ["HTTPS POST /api/webhooks/payment", "Payment-Signature: t=..., v1=...", "body {type: payment.succeeded, orderId: o-1001}"],
               pts=[(980, 1850), (980, 790), (1220, 790)]),
             S("2", "cf", "apigw", ("R", 600), ("L", 600), "Origin request",
               "This route has no Cognito authorizer. The webhook function checks the signature instead.",
               ["Origin request /prod/webhooks/payment", "no Authorization header"]),
             S("3", "apigw", "lhook", ("B", 1760), ("L", 1140), "Invoke",
               "API Gateway invokes the webhook function with the raw body and the signature header.",
               ["Lambda event", "headers.Payment-Signature", "body (raw, for the HMAC check)"], pts=[(1760, 1140)]),
             S("4", "lhook", "ddb", ("R", 1100), ("L", 610), "Find the task token",
               "The function checks the signature with the key from Secrets Manager. It reads the task token for the order ID. "
               "It ignores an event ID that it processed before.",
               ["GetItem PK PAY#o-1001 → taskToken", "PutItem EVT#evt_9", "(condition attribute_not_exists)"],
               pts=[(2190, 1100), (2190, 610)]),
             S("5", "lhook", "sfn", ("R", 1170), ("L", 1170), "Callback",
               "The function calls SendTaskSuccess for a paid order or SendTaskFailure for a failed payment. "
               "Return path: Lambda → API Gateway → CloudFront → provider (200).",
               ["SendTaskSuccess", "taskToken AQB...", "output {paymentId: pay_77, status: PAID}"]),
         ]),
    dict(title="Scenario 3 - The saga writes the order and tells the customer",
         who="The workflow continues after SendTaskSuccess.",
         needs="Needs: Scenario 2 (the callback).",
         steps=[
             S("1", "sfn", "lorder", ("B", 2300), ("T", 2300), "Write the order",
               "The workflow invokes the order function with the order data and the payment ID.",
               ["Invoke order-svc", "{orderId: o-1001, customerId: c-42,", "lines[], paymentId: pay_77}"], b=(2307, 1260)),
             S("2", "lorder", "proxy", ("L", 1660), ("R", 1660), "Pooled connection",
               "The function connects to RDS Proxy with IAM authentication. The proxy keeps a pool of database connections.",
               ["PostgreSQL 5432 over TLS", "user order_svc, IAM auth token"]),
             S("3", "proxy", "aura", ("B", cx("proxy")), ("T", cx("aura")), "One transaction",
               "The proxy sends the statements to the writer in AZ-a. One transaction writes the order and its lines.",
               ["BEGIN", "INSERT INTO orders ...; INSERT INTO order_lines ...", "COMMIT"]),
             S("4", "sfn", "eb", ("R", 1100), ("L", 1100), "Publish OrderPlaced",
               "The workflow calls PutEvents directly on the commerce bus. Scenario 5 shows the targets.",
               ["PutEvents, EventBusName commerce", "source com.shop.checkout", "detail-type OrderPlaced",
                "detail {orderId: o-1001, customerId: c-42, total: 1299.00}"]),
             S("5", "sfn", "lws", ("T", 2276), ("B", 1770), "Push request",
               "The workflow invokes the ws function with the order ID and the status CONFIRMED.",
               ["Invoke ws-push", "{customerId: c-42, orderId: o-1001,", "status: CONFIRMED}"],
               pts=[(2276, L_R2R3), (1880, L_R2R3), (1880, 470), (1770, 470)], b=(1887, 860)),
             S("6", "lws", "ddb", ("R", 300), ("T", 2290), "Find the connection",
               "The function reads the connection ID of the customer from the ws-connections table.",
               ["Query table ws-connections", "PK CUST#c-42 → connectionId Ab12="],
               pts=[(1900, 300), (1900, 240), (2160, 240), (2160, 470), (2290, 470)]),
             S("7", "lws", "wsapi", ("L", 300), ("R", 300), "Post to the connection",
               "The function calls the @connections API with the message.",
               ["POST /prod/@connections/Ab12=", "SigV4, execute-api:ManageConnections"]),
             S("8", "wsapi", CUS, ("B", 1430), ("R", 470), "Push",
               "API Gateway sends the message on the open WebSocket. The SPA shows the order confirmation. "
               "Return path: none. The push goes one way.",
               ["WebSocket frame", "{type: checkout.result, orderId: o-1001,", "status: CONFIRMED}"], pts=[(1430, 470)], b=(1100, 437)),
         ]),
    dict(title="Scenario 4 - The saga undoes the reservation",
         who="Compensation: the workflow catches the payment error.",
         needs="Branch of Scenario 1, step 2: SendTaskFailure arrives, or the 15-minute timeout ends the wait.",
         steps=[
             S("1", "sfn", "ddb", ("T", 2330), ("B", 2330), "Release the stock",
               "The Catch block calls UpdateItem. It adds the reserved quantity back to available.",
               ["UpdateItem table stock, PK SKU#123", "SET available = available + :qty"], b=(2338, 960)),
             S("2", "sfn", "eb", ("R", 1150), ("L", 1150), "Publish PaymentFailed",
               "The workflow publishes PaymentFailed on the commerce bus.",
               ["PutEvents, EventBusName commerce", "source com.shop.checkout", "detail-type PaymentFailed",
                "detail {orderId: o-1001, reason: declined | timeout}"]),
             S("3", "sfn", "lws", ("T", 2258), ("B", 1755), "Push request",
               "The workflow invokes the ws function with the status PAYMENT_FAILED.",
               ["Invoke ws-push", "{customerId: c-42, orderId: o-1001,", "status: PAYMENT_FAILED}"],
               pts=[(2258, 1040), (1860, 1040), (1860, 490), (1755, 490)], b=(1822, 880)),
             S("4", "lws", "wsapi", ("L", 350), ("R", 350), "Post to the connection",
               "The function reads the connection ID first, as in Scenario 3, step 6. Then it calls the @connections API.",
               ["POST /prod/@connections/Ab12=", "SigV4, execute-api:ManageConnections"]),
             S("5", "wsapi", CUS, ("B", 1460), ("R", 490), "Push",
               "The SPA shows that the payment failed. Return path: none. If the Aurora write fails after the payment, "
               "the saga also refunds through Lambda payment (not drawn).",
               ["WebSocket frame", "{type: checkout.result, orderId: o-1001,", "status: PAYMENT_FAILED}"], pts=[(1460, 490)], b=(1100, 496)),
         ]),
    dict(title="Scenario 5 - EventBridge delivers OrderPlaced",
         who="The commerce bus starts this flow. Three rules match the same event. Steps 1a, 1b and 1c run in parallel.",
         needs="Needs: Scenario 3, step 4 (OrderPlaced on the bus).",
         steps=[
             S("1a", "eb", "sns", ("T", 2580), ("B", 2580), "Rule order-placed-notify",
               "The rule sends the event to the notification topic. Page 4 shows the email and the SMS.",
               ["SNS Publish, topic order-notifications", "MessageAttributes eventType = OrderPlaced"]),
             S("1b", "eb", "sqsbuf", ("R", 1110), ("L", 1110), "Rule order-placed-fulfil",
               "The rule sends the event to the order buffer queue. The queue protects the 3PL link from peaks. Page 4 shows the fulfillment.",
               ["SQS SendMessage, queue order-buffer", "body = the event JSON"], b=(2700, 1077)),
             S("1c", "eb", "lprodc", ("R", 1176), ("T", 3080), "Rule commerce-log",
               "The rule invokes the producer function in the VPC.",
               ["Lambda event = the EventBridge event", "detail-type OrderPlaced"], pts=[(2700, 1176), (2700, 1510), (3080, 1510)], b=(2707, 1300)),
             S("2", "lprodc", "msk", ("R", 1660), ("L", 1660), "Event log",
               "The function writes the event to the Kafka topic commerce-events with IAM authentication.",
               ["Kafka produce, topic commerce-events", "key o-1001, value = the event JSON", "SASL/IAM on port 9098"]),
             S("3", "eb", "dlq", ("R", 1152), ("B", 3140), "Failed delivery",
               "If a target still fails after all retries, EventBridge sends the event to the DLQ of that rule. "
               "Return path: none. The bus archive keeps every event for replay.",
               ["SQS message in the rule DLQ", "attributes ERROR_CODE, RULE_ARN"],
               pts=[(2730, 1152), (2730, L_R3R4), (3140, L_R3R4)], dashed=True, b=(2738, 1200)),
         ]),
]

# Page 4 -------------------------------------------------------------------
P4 = [
    dict(title="Scenario 1 - The fulfillment command goes to the 3PL",
         who="The order buffer queue starts this flow.",
         needs="Needs: page 3, Scenario 5, step 1b (OrderPlaced in the buffer).",
         steps=[
             S("1", "sqsbuf", "lful", ("B", 2860), ("T", 2860), "Poll",
               "The event source mapping polls the queue and invokes the function with a batch. The function reports only the failed items.",
               ["SQS ReceiveMessage (event source mapping)", "Records[].body = OrderPlaced event", "ReportBatchItemFailures"]),
             S("2", "lful", "mqa", ("B", 2860), ("T", 1740), "Publish FulfillOrder",
               "The function publishes a persistent FulfillOrder message to the fulfillment exchange over AMQPS. The broker confirms each message.",
               ["AMQP basic.publish, exchange fulfillment", "routing key 3pl.orders, delivery_mode 2", "type FulfillOrder, message_id o-1001"],
               pts=[(2860, 1745), (1740, 1745)]),
             S("3", "mqa", "vgw", ("L", 2060), ("R", 2060), "To the VPN",
               "The broker sends the message on the AMQPS connection that the WMS opened. Route table rtb-private-a sends 172.16.0.0/16 to vgw-shop.",
               ["AMQPS 5671", "src 10.0.16.40 (MQ node a private IP)", "dst 172.16.10.5 (3PL WMS private IP)"]),
             S("4", "vgw", "onprem-3pl", ("L", 2060), ("R", 2060), "Delivery",
               "The Site-to-Site VPN carries the message to the customer gateway of the 3PL. The WMS reads the message and sends an ack. "
               "Return path: the ack goes back the same way to the broker.",
               ["IPsec tunnel to the 3PL customer gateway", "WMS sends basic.ack"]),
         ]),
    dict(title="Scenario 2 - The 3PL reports the shipment",
         who="The 3PL WMS starts this flow when a parcel leaves the warehouse.",
         steps=[
             S("1", "onprem-3pl", "vgw", ("R", 2100), ("L", 2100), "Publish ShipmentDispatched",
               "The WMS publishes the message to the shipments exchange over the VPN.",
               ["AMQP basic.publish, exchange shipments", "src 172.16.10.5 (3PL WMS private IP)", "dst 10.0.16.40 (MQ node a private IP)"]),
             S("2", "vgw", "mqa", ("R", 2100), ("L", 2100), "Into the VPC",
               "The virtual private gateway delivers the packets to the broker. The broker stores the message in the queue shipments.events.",
               ["queue shipments.events", "body {orderId: o-1001, carrier, trackingNo}"]),
             S("3", "mqa", "pipes", ("T", 1680), ("B", 2580), "Poll",
               "The pipe reads batches from the queue. Its filter passes only ShipmentDispatched messages. An MQ source runs 5 pollers. "
               "A quota increase gives more.",
               ["Pipe source: Amazon MQ queue shipments.events", "filter: data.type = ShipmentDispatched"],
               pts=[(1680, 1500), (2580, 1500)]),
             S("4", "pipes", "eb", ("T", 2580), ("B", 2580), "Publish to the bus",
               "The pipe sends the event to the commerce bus with detail-type ShipmentDispatched.",
               ["PutEvents, EventBusName commerce", "source com.shop.3pl", "detail-type ShipmentDispatched",
                "detail {orderId: o-1001, trackingNo}"]),
             S("5", "eb", "sns", ("T", 2580), ("B", 2580), "Rule shipment-notify",
               "The rule sends the event to the notification topic. Scenarios 3 and 4 continue. "
               "Return path: none. The pipe acknowledges the messages after the delivery.",
               ["SNS Publish, topic order-notifications", "MessageAttributes eventType = ShipmentDispatched"]),
         ]),
    dict(title="Scenario 3 - The customer gets an email",
         who="The notification topic starts this flow.",
         needs="Needs: page 3, Scenario 5, step 1a, or Scenario 2, step 5.",
         steps=[
             S("1", "sns", "sqsmail", ("T", 2610), ("L", 330), "Fan-out",
               "The topic sends a copy to the email queue with raw message delivery.",
               ["SQS message, body = the event JSON (raw)"], pts=[(2610, 330)], b=(2617, 440)),
             S("2", "sqsmail", "lmail", ("R", 330), ("L", 330), "Poll",
               "The event source mapping invokes the email function with a batch.",
               ["Records[], eventType OrderPlaced"]),
             S("3", "lmail", "ses", ("R", 330), ("L", 330), "Send the email",
               "The function selects the template from the event type. It calls SendEmail with the configuration set.",
               ["SESv2 SendEmail", "Template OrderConfirmed | ShipmentDispatched", "ConfigurationSetName shop-mail"]),
             S("4", "ses", "users-inbox", ("R", 330), ("L", 330), "Delivery",
               "SES delivers the email to the mailbox of the customer. Return path: the configuration set sends bounce "
               "and complaint events to the EventBridge default bus.",
               ["SMTP to the mail server of the customer", "From: orders@shop.tdsynnexlab.link"]),
         ]),
    dict(title="Scenario 4 - The customer gets an SMS",
         who="The notification topic starts this flow.",
         needs="Needs: the same event as Scenario 3.",
         steps=[
             S("1", "sns", "sqssms", ("R", 580), ("L", 580), "Fan-out",
               "The topic sends a copy to the SMS queue. A filter policy passes only customers who accept SMS.",
               ["Subscription filter policy {smsOptIn: [true]}"]),
             S("2", "sqssms", "lsms", ("R", 580), ("L", 580), "Poll",
               "The event source mapping invokes the SMS function.",
               ["Records[], eventType OrderPlaced"]),
             S("3", "lsms", "eum", ("R", 580), ("L", 580), "Send the SMS",
               "The function calls SendTextMessage of AWS End User Messaging SMS.",
               ["SendTextMessage", "DestinationPhoneNumber +49...", "MessageBody: Order o-1001 confirmed"]),
             S("4", "eum", "users-inbox", ("R", 580), ("L", 580), "Delivery",
               "The SMS goes to the phone of the customer. Return path: none.",
               ["SMS to +49..."]),
         ]),
    dict(title="Scenario 5 - The back office gets a copy",
         who="The notification topic starts this flow.",
         needs="Needs: the same event as Scenario 3.",
         steps=[
             S("1", "sns", "sqsbo", ("B", 2625), ("L", 890), "Fan-out",
               "The topic sends a copy to the back-office queue. The back-office application reads it. "
               "That application is outside this design. Return path: none.",
               ["SQS message", "eventType OrderPlaced | ShipmentDispatched"], pts=[(2625, 890)], b=(2632, 760)),
         ]),
]

# Page 5 -------------------------------------------------------------------
P5 = [
    dict(title="Scenario 1 - The admin saves a product",
         who="A back-office admin starts this flow from the admin pages of the SPA.",
         needs="Needs: the admin signed in with MFA (as on page 2, Scenario 2).",
         steps=[
             S("1", ADM, "cf", ("R", 1340), ("B", 1215), "Admin request",
               "The admin pages send PUT /api/admin/products/SKU#123 with the ID token.",
               ["HTTPS PUT /api/admin/products/SKU%23123", "Authorization: Bearer &lt;ID token&gt;", "body {name, price, attributes}"],
               pts=[(980, 1340), (980, 790), (1215, 790)]),
             S("2", "cf", "apigw", ("R", 600), ("L", 600), "Token and group check",
               "The authorizer accepts only tokens with the admins group claim. The request validator checks the product body.",
               ["Origin request /prod/admin/products/SKU%23123", "claims cognito:groups = [admins]"]),
             S("3", "apigw", "lprod", ("R", 580), ("L", 580), "Invoke",
               "API Gateway invokes the product function on the admin route.",
               ["Lambda event, resource /admin/products/{sku}"]),
             S("4", "lprod", "ddb", ("R", 580), ("L", 580), "Write the product",
               "The function writes the product item. DynamoDB Streams records the change. "
               "Return path: Lambda → API Gateway → CloudFront → admin.",
               ["PutItem table catalog, PK SKU#123", "stream record with the new image"]),
         ]),
    dict(title="Scenario 2 - Zero-ETL copies the change to OpenSearch",
         who="The DynamoDB stream starts this flow.",
         needs="Needs: Scenario 1 (the stream record).",
         steps=[
             S("1", "ddb", "osis", ("T", cx("ddb")), ("B", cx("osis")), "Read the stream",
               "The OpenSearch Ingestion pipeline of the zero-ETL integration reads the DynamoDB stream. "
               "The first full copy came from a point-in-time recovery (PITR) export.",
               ["Stream record, eventName MODIFY", "NewImage {SKU#123, name, price}"]),
             S("2", "osis", "aoss", ("L", 330), ("R", 330), "Index the document",
               "The pipeline writes the document to the products index. Search shows the change after a short delay. Return path: none.",
               ["Bulk index, index products", "_id SKU#123"]),
         ]),
    dict(title="Scenario 3 - The admin gets a presigned upload URL",
         who="A back-office admin starts this flow before an image upload.",
         needs="Needs: the admin signed in with MFA.",
         steps=[
             S("1", ADM, "cf", ("R", 1370), ("B", 1245), "Request",
               "The admin pages send POST /api/admin/images/upload-url with the ID token.",
               ["HTTPS POST /api/admin/images/upload-url", "body {sku: SKU#123, contentType: image/jpeg}"],
               pts=[(1020, 1370), (1020, 810), (1245, 810)], b=(1027, 1100)),
             S("2", "cf", "apigw", ("R", 645), ("L", 645), "Token and group check",
               "The authorizer accepts only tokens with the admins group claim.",
               ["Origin request /prod/admin/images/upload-url", "claims cognito:groups = [admins]"]),
             S("3", "apigw", "lprod", ("R", 620), ("L", 620), "Sign the URL",
               "The function signs a PUT URL for the uploads bucket. It does not call S3. Return path: the URL goes back to the admin. "
               "The URL expires after a short time (for example 5 minutes).",
               ["Response {url: https://&lt;uploads bucket&gt;.s3.eu-central-1", ".amazonaws.com/SKU%23123/orig.jpg?X-Amz-Signature=...}"]),
         ]),
    dict(title="Scenario 4 - The admin browser uploads the image",
         who="The admin browser starts this flow.",
         needs="Needs: Scenario 3 (the presigned URL).",
         steps=[
             S("1", ADM, "s3up", ("R", 1420), ("L", 1420), "Upload",
               "The browser sends the file with HTTPS PUT to the presigned URL. The upload does not use CloudFront or API Gateway. "
               "Return path: S3 sends 200 to the browser.",
               ["HTTPS PUT /SKU%23123/orig.jpg", "Host: &lt;uploads bucket&gt;.s3.eu-central-1.amazonaws.com", "Content-Type: image/jpeg"]),
         ]),
    dict(title="Scenario 5 - S3 starts the image resize",
         who="The uploads bucket starts this flow.",
         needs="Needs: Scenario 4 (the new object).",
         steps=[
             S("1", "s3up", "busdef", ("R", 1390), ("L", 1390), "Object Created event",
               "The bucket sends an Object Created event to the EventBridge default bus. S3 sends its events only to the default bus.",
               ["source aws.s3, detail-type Object Created", "detail.bucket.name = uploads bucket", "detail.object.key = SKU#123/orig.jpg"]),
             S("2", "busdef", "lresize", ("R", 1390), ("L", 1390), "Rule image-uploaded",
               "The rule matches the uploads bucket and invokes the resize function. A DLQ keeps failed deliveries.",
               ["Lambda event = the EventBridge event"]),
             S("3", "lresize", "s3up", ("B", 2020), ("B", 1460), "Read the original",
               "The function reads the original image with GetObject.",
               ["GetObject uploads bucket, SKU#123/orig.jpg"], pts=[(2020, 1480), (1460, 1480)]),
             S("4", "lresize", "s3web", ("T", 1990), ("R", 890), "Write the sizes",
               "The function writes three sizes to the web bucket. CloudFront serves them under /images/*. Return path: none. "
               "The separate bucket prevents a resize loop.",
               ["PutObject web bucket", "images/SKU#123/sm.webp, md.webp, lg.webp"],
               pts=[(1990, L_R3R4), (1600, L_R3R4), (1600, 890)]),
         ]),
    dict(title="Scenario 6 - The browser sends clickstream events",
         who="The customer browser starts this flow while the customer uses the shop.",
         needs="Needs: page 2, Scenario 1 (the SPA runs).",
         steps=[
             S("1", CUS, "cf", ("R", 690), ("L", 690), "Event batch",
               "The SPA sends POST /api/events with a batch of page views and clicks.",
               ["HTTPS POST /api/events", "[{type: page_view, sku, ts}, ...]"]),
             S("2", "cf", "apigw", ("R", 690), ("L", 690), "Origin request",
               "CloudFront sends the batch to the REST API. Throttling on the /events route limits the request rate.",
               ["Origin request /prod/events"]),
             S("3", "apigw", "lprodc", ("R", 700), ("T", 3050), "Invoke",
               "API Gateway invokes the producer function. The function runs in the VPC because the browser cannot speak Kafka.",
               ["Lambda event, body = the event batch"], pts=[(1880, 700), (1880, 1510), (3050, 1510)]),
             S("4", "lprodc", "msk", ("R", 1660), ("L", 1660), "Produce",
               "The function writes the events to the topic clickstream. The key is the session ID. "
               "Return path: Lambda → API Gateway → CloudFront → browser (202).",
               ["Kafka produce, topic clickstream", "key = session s-9", "SASL/IAM on port 9098"]),
         ]),
    dict(title="Scenario 7 - A consumer writes the data lake",
         who="MSK Serverless starts this flow through an event source mapping.",
         needs="Needs: Scenario 6 (or page 3, Scenario 5, step 2 for commerce events).",
         steps=[
             S("1", "msk", "larch", ("T", 3348), ("B", 3420), "Poll",
               "The event source mapping in provisioned mode reads batches. Its consumer group is archive.",
               ["Records from clickstream-0, offsets 1200-1499", "consumer group archive"], pts=[(3348, 1500), (3420, 1500)]),
             S("2", "larch", "s3lake", ("R", 1390), ("L", 1390), "Write a batch file",
               "The function writes one file for each batch. The object key has date and hour partitions. "
               "The marketing team queries this data. Return path: none.",
               ["PutObject data lake bucket", "clickstream/dt=2026-10-26/hour=14/part-0001.json.gz"]),
         ]),
    dict(title="Scenario 8 - A consumer counts popular products",
         who="MSK Serverless starts this flow through a second event source mapping.",
         needs="Needs: Scenario 6.",
         steps=[
             S("1", "msk", "lcount", ("T", 3252), ("B", 3140), "Poll",
               "A second event source mapping reads the same topic. Its consumer group is counters.",
               ["consumer group counters", "Records[], type page_view"], pts=[(3252, 1500), (3140, 1500)]),
             S("2", "lcount", "ddb", ("L", 1390), ("B", 2330), "Update the counters",
               "The function adds the view counts for each SKU with an atomic ADD. The product function reads these counters. Return path: none.",
               ["UpdateItem table counters, PK POP#SKU#123", "ADD views :n"], pts=[(3000, 1390), (3000, L_R1R2), (2330, L_R1R2)]),
         ]),
]

ASSOC = {  # extra association lines per page (no traffic): (src, tgt, ex, en, pts, label)
    "waf": ("waf", "cf", ("B", 1240), ("T", 1240), (), "web ACL"),
    "cognito": ("apigw", "cognito", ("B", 1700), ("R", 1140), [(1700, 1140)], "JWT authorizer"),
}


# ================================================================== ROUTES (layout v2)
# (page, scenario index, step label): (exit, entry, waypoints, badge position or None)
ROUTES = {
    # page 2 - customer (synchronous)
    (2, 0, "1"): (("R", 176), ("R", 270), [(1870, 176), (1870, 270)], (1877, 200)),
    (2, 0, "2"): (("R", 254), ("L", 254), [], (917, 240)),
    (2, 0, "3"): (("R", 385), ("L", 1320), [(1880, 385), (1880, 1320)], (1420, 351)),
    (2, 1, "1"): (("R", 447), ("T", 1550), [(1550, 447)], (917, 414)),
    (2, 2, "1"): (("R", 286), ("L", 286), [], (980, 272)),
    (2, 2, "2"): (("B", 1290), ("T", 1290), [], (1276, 410)),
    (2, 2, "3"): (("B", 1310), ("T", 1310), [], (1317, 627)),
    (2, 2, "4"): (("B", 1330), ("T", 1330), [], (1337, 827)),
    (2, 2, "5"): (("R", 780), ("L", 1300), [(1440, 780), (1440, 1300)], None),
    (2, 3, "1"): (("R", 318), ("L", 318), [], (1043, 304)),
    (2, 3, "2"): (("B", 1335), ("T", 1335), [], (1321, 410)),
    (2, 3, "3"): (("B", 1360), ("T", 1520), [(1360, 650), (1520, 650)], (1450, 636)),
    (2, 3, "4"): (("B", 1550), ("T", 1550), [], None),
    (2, 4, "1"): (("R", 196), ("T", 1790), [(1790, 196)], (1745, 182)),
    (2, 4, "2"): (("R", 530), ("L", 530), [], (917, 497)),
    (2, 4, "3"): (("B", 1110), ("T", 1110), [], None),
    (2, 4, "4"): (("R", 760), ("T", 1520), [(1240, 760), (1240, 1230), (1520, 1230)], None),
    (2, 5, "1"): (("R", 350), ("L", 350), [], (1106, 336)),
    (2, 5, "2"): (("B", 1380), ("T", 1380), [], (1366, 410)),
    (2, 5, "3"): (("B", 1380), ("L", 875), [(1380, 632), (1660, 632), (1660, 875)], (1667, 740)),
    # page 3 - checkout saga
    (3, 0, "1"): (("L", 900), ("T", 1580), [(1580, 900)], (1587, 1200)),
    (3, 0, "2"): (("L", 950), ("R", 1840), [(1670, 950), (1670, 1475), (1390, 1475), (1390, 1840)], (1677, 1300)),
    (3, 0, "3"): (("L", 1820), ("B", 1550), [(1240, 1820), (1240, 1412), (1550, 1412)], (1180, 1478)),
    (3, 0, "4"): (("T", 1315), ("B", 1315), [], None),
    (3, 0, "5"): (("L", 1660), ("R", 1660), [], None),
    (3, 0, "6"): (("L", 1660), ("R", 1660), [], (925, 1627)),
    (3, 1, "1"): (("R", 1600), ("L", 370), [(935, 1600), (935, 370)], (942, 1200)),
    (3, 1, "2"): (("B", 1335), ("T", 1335), [], (1321, 410)),
    (3, 1, "3"): (("B", 1380), ("T", 1740), [(1380, 632), (1740, 632)], None),
    (3, 1, "4"): (("L", 760), ("R", 1290), [(1625, 760), (1625, 1290)], None),
    (3, 1, "5"): (("B", 1770), ("T", 1770), [], None),
    (3, 2, "1"): (("L", 925), ("T", 1165), [(1650, 925), (1650, 1460), (1165, 1460)], (1612, 1080)),
    (3, 2, "2"): (("B", 1165), ("T", 1165), [], None),
    (3, 2, "3"): (("R", 2030), ("L", 2030), [], (1226, 1926)),
    (3, 2, "4"): (("R", 910), ("L", 910), [], None),
    (3, 2, "5"): (("T", 1730), ("B", 1140), [(1730, 855), (1140, 855)], (1450, 841)),
    (3, 2, "6"): (("R", 760), ("T", 1520), [(1240, 760), (1240, 1230), (1520, 1230)], None),
    (3, 2, "7"): (("T", 1110), ("B", 1110), [], (1070, 630)),
    (3, 2, "8"): (("L", 560), ("R", 560), [], (1010, 527)),
    (3, 3, "1"): (("L", 888), ("T", 1565), [(1565, 888)], (1500, 1200)),
    (3, 3, "2"): (("R", 960), ("L", 960), [], None),
    (3, 3, "3"): (("T", 1720), ("B", 1125), [(1720, 870), (1125, 870)], (1530, 856)),
    (3, 3, "4"): (("T", 1140), ("B", 1140), [], (1147, 630)),
    (3, 3, "5"): (("L", 590), ("R", 590), [], (970, 576)),
    (3, 4, "1a"): (("R", 910), ("L", 910), [], None),
    (3, 4, "1b"): (("B", 1965), ("T", 1770), [(1965, 1035), (1770, 1035)], (1860, 992)),
    (3, 4, "1c"): (("R", 975), ("T", 1630), [(2100, 975), (2100, 1490), (1630, 1490)], (2058, 1110)),
    (3, 4, "2"): (("B", 1615), ("T", 1615), [], None),
    (3, 4, "3"): (("B", 2010), ("T", 2430), [(2010, 1045), (2430, 1045)], (2300, 1004)),
    # page 4 - fulfillment and notifications
    (4, 0, "1"): (("B", 1770), ("T", 1465), [(1770, 1505), (1465, 1505)], (1777, 1300)),
    (4, 0, "2"): (("B", 1465), ("T", 1465), [], None),
    (4, 0, "3"): (("B", 1450), ("T", 1450), [], (1360, 2150)),
    (4, 0, "4"): (("B", 1450), ("T", 1450), [], (1415, 2253)),
    (4, 1, "1"): (("T", 1490), ("B", 1490), [], None),
    (4, 1, "2"): (("T", 1490), ("B", 1490), [], (1545, 2150)),
    (4, 1, "3"): (("R", 2000), ("R", 1120), [(1540, 2000), (1540, 1394), (1220, 1394), (1220, 1120)], (1227, 1300)),
    (4, 1, "4"): (("T", 1110), ("L", 990), [(1110, 1022), (1900, 1022), (1900, 990)], (1500, 988)),
    (4, 1, "5"): (("R", 910), ("L", 910), [], None),
    (4, 2, "1"): (("B", 2690), ("B", 3280), [(2690, 1025), (3280, 1025)], (2955, 1031)),
    (4, 2, "2"): (("T", 3310), ("B", 3310), [], None),
    (4, 2, "3"): (("B", 3350), ("T", 3530), [(3350, 855), (3530, 855)], (3420, 841)),
    (4, 2, "4"): (("R", 950), ("L", 950), [], None),
    (4, 3, "1"): (("R", 950), ("L", 950), [], None),
    (4, 3, "2"): (("T", 2870), ("B", 2870), [], None),
    (4, 3, "3"): (("B", 2910), ("T", 3090), [(2910, 860), (3090, 860)], (2960, 846)),
    (4, 3, "4"): (("B", 3110), ("L", 1045), [(3110, 1045)], (3200, 1050)),
    (4, 4, "1"): (("B", 2650), ("T", 2650), [], None),
    # page 5 - admin and analytics
    (5, 0, "1"): (("R", 880), ("L", 340), [(935, 880), (935, 340)], (942, 700)),
    (5, 0, "2"): (("B", 1290), ("T", 1290), [], (1276, 410)),
    (5, 0, "3"): (("B", 1300), ("T", 1300), [], None),
    (5, 0, "4"): (("R", 780), ("L", 1300), [(1440, 780), (1440, 1300)], None),
    (5, 1, "1"): (("B", 1520), ("B", 1110), [(1520, 1405), (1110, 1405)], None),
    (5, 1, "2"): (("R", 1320), ("L", 1320), [], None),
    (5, 2, "1"): (("R", 910), ("L", 370), [(950, 910), (950, 370)], (957, 560)),
    (5, 2, "2"): (("B", 1335), ("T", 1335), [], (1321, 410)),
    (5, 2, "3"): (("B", 1350), ("T", 1350), [], (1357, 627)),
    (5, 3, "1"): (("R", 1000), ("B", 2210), [(945, 1000), (945, 1424), (2210, 1424)], (952, 1100)),
    (5, 4, "1"): (("T", 2210), ("B", 2210), [], None),
    (5, 4, "2"): (("T", 2210), ("B", 2210), [], None),
    (5, 4, "3"): (("R", 770), ("R", 1330), [(2300, 770), (2300, 1330)], None),
    (5, 4, "4"): (("L", 730), ("R", 1290), [(2100, 730), (2100, 1290)], None),
    (5, 5, "1"): (("R", 286), ("L", 286), [], (980, 272)),
    (5, 5, "2"): (("B", 1380), ("T", 1380), [], (1366, 410)),
    (5, 5, "3"): (("B", 1380), ("T", 1600), [(1380, 632), (1665, 632), (1665, 1482), (1600, 1482)], (1672, 740)),
    (5, 5, "4"): (("B", 1615), ("T", 1615), [], None),
    (5, 6, "1"): (("R", 2050), ("R", 760), [(1697, 2050), (1697, 1505), (2760, 1505), (2760, 760)], (2767, 1100)),
    (5, 6, "2"): (("L", 780), ("R", 1320), [(2540, 780), (2540, 1320)], None),
    (5, 7, "1"): (("R", 2010), ("L", 760), [(1683, 2010), (1683, 1490), (2320, 1490), (2320, 760)], (2327, 1220)),
    (5, 7, "2"): (("T", 2430), ("R", 1320), [(2430, 640), (1680, 640), (1680, 1320)], None),
}

PAGE_SCEN = {2: P2, 3: P3, 4: P4, 5: P5}
for (pg_n, si, lab), (ex, en, pts, bpos) in ROUTES.items():
    st = next(s for s in PAGE_SCEN[pg_n][si]["steps"] if s["label"] == lab)
    st.update(ex=ex, en=en, pts=pts, b=bpos)
for pg_n, sc in PAGE_SCEN.items():
    for si, s in enumerate(sc):
        for st in s["steps"]:
            assert (pg_n, si, st["label"]) in ROUTES, (pg_n, si, st["label"])


def ref(pg_n, si, lab):
    return next(s for s in PAGE_SCEN[pg_n][si]["steps"] if s["label"] == lab)


# ================================================================== PAGE 1: main customer journey (14 steps)
JOURNEY = [
    ("Customer → CloudFront", "The browser loads the SPA and calls /api/* through CloudFront. AWS WAF checks every request.",
     [(2, 0, "2")]),
    ("CloudFront → REST API", "CloudFront sends /api/* to the regional REST API. The Cognito authorizer checks the token on protected routes.",
     [(2, 2, "2")]),
    ("Search", "The product function searches the OpenSearch Serverless index. Page 2 shows the price and stock read from DynamoDB.",
     [(2, 2, "3"), (2, 2, "4")]),
    ("Cart", "The cart function writes the cart item to DynamoDB. DynamoDB TTL deletes old carts.",
     [(2, 3, "3"), (2, 3, "4")]),
    ("Checkout start", "The REST API starts the checkout-saga execution directly. The execution name is the Idempotency-Key.",
     [(2, 5, "3")]),
    ("Stock reservation", "The saga reserves the stock with a conditional UpdateItem in DynamoDB.",
     [(3, 0, "1")]),
    ("Payment request", "The saga invokes the payment function with a task token. The function calls the payment provider "
     "through the NAT gateway and the internet gateway.",
     [(3, 0, "2"), (3, 0, "4"), (3, 0, "5"), (3, 0, "6")]),
    ("Payment callback", "The provider sends the webhook through CloudFront and the REST API. The webhook function checks "
     "the signature and calls SendTaskSuccess.",
     [(3, 1, "1"), (3, 1, "2"), (3, 1, "3"), (3, 1, "5")]),
    ("Order write", "The order function writes the order to the Aurora writer through RDS Proxy.",
     [(3, 2, "1"), (3, 2, "2"), (3, 2, "3")]),
    ("OrderPlaced", "The saga publishes OrderPlaced on the commerce bus.",
     [(3, 2, "4")]),
    ("Fulfillment", "A rule sends OrderPlaced to the order buffer queue. The fulfillment function publishes FulfillOrder to "
     "Amazon MQ. The 3PL WMS reads the message over the Site-to-Site VPN.",
     [(3, 4, "1b"), (4, 0, "1"), (4, 0, "2"), (4, 0, "3"), (4, 0, "4")]),
    ("Shipment", "The WMS publishes ShipmentDispatched to Amazon MQ. EventBridge Pipes sends it to the commerce bus.",
     [(4, 1, "1"), (4, 1, "2"), (4, 1, "3"), (4, 1, "4")]),
    ("Email", "A rule sends the event to SNS. SNS sends a copy to the email queue. The email function sends the email with SES.",
     [(3, 4, "1a"), (4, 2, "1"), (4, 2, "2"), (4, 2, "3"), (4, 2, "4")]),
    ("Result push", "The saga invokes the ws function. The function posts the checkout result to the open WebSocket. "
     "Return path: none. The push goes one way.",
     [(3, 2, "5"), (3, 2, "7"), (3, 2, "8")]),
]
J_COLOR = "#007CBD"
J_BADGE = {11: (1777, 1300)}   # badge on another arrow of the step where the first arrow has no room
GREY_LINE = "#A7B1BC"

ASSOC = {  # association lines (no traffic): (src, tgt, exit, entry, waypoints, label)
    "waf": ("cf", "waf", ("R", 300), ("L", 300), (), "web ACL"),
    "cognito": ("apigw", "cognito", ("R", 550), ("L", 550), (), "JWT authorizer"),
}

LINE_STYLES = ("<b>Line styles</b><br>Solid colored arrow: one step of a scenario (the color is the scenario).<br>"
               "Dashed colored arrow: failure path.<br>Dotted grey line: association. No traffic flows on it.<br>"
               "Arc on a line: two lines cross. They do not connect.")
LINE_STYLES_P1 = ("<b>Line styles</b><br>Blue numbered arrow: one step of the main customer journey. "
                  "One number can cover several arrows.<br>Grey arrow: another connection. Pages 2 to 5 show it as a step.<br>"
                  "Dashed arrow: failure path.<br>Dotted grey line: association. No traffic flows on it.<br>"
                  "Arc on a line: two lines cross. They do not connect.")

SG_TABLE = ("<b>Security groups</b><table style=\"width:560px;font-size:11px;border-collapse:collapse;margin-top:4px\">"
            "<tr style=\"background:#E6E6E6;color:#333333\"><td><b>Source</b></td><td><b>Destination</b></td><td><b>Port</b></td></tr>"
            "<tr><td>sg-lambda-vpc</td><td>sg-proxy</td><td>TCP 5432</td></tr>"
            "<tr><td>sg-proxy</td><td>sg-aurora</td><td>TCP 5432</td></tr>"
            "<tr><td>sg-lambda-vpc</td><td>sg-mq</td><td>TCP 5671 (AMQPS)</td></tr>"
            "<tr><td>Pipes ENIs (broker VPC settings)</td><td>sg-mq</td><td>TCP 5671</td></tr>"
            "<tr><td>172.16.0.0/16 (3PL over VPN)</td><td>sg-mq</td><td>TCP 5671</td></tr>"
            "<tr><td>sg-lambda-vpc</td><td>sg-msk</td><td>TCP 9098 (IAM)</td></tr>"
            "<tr><td>MSK event source mappings</td><td>sg-msk</td><td>TCP 9098</td></tr>"
            "<tr><td>sg-lambda-vpc</td><td>sg-vpce</td><td>TCP 443</td></tr>"
            "<tr><td>sg-lambda-vpc (payment)</td><td>0.0.0.0/0 through NAT</td><td>TCP 443</td></tr></table>")

P1_RIGHT = [
    ("box", "dec", "<b>Key decisions</b><br>"
     "One account, one Region (eu-central-1), three AZs. Production models everywhere: Multi-AZ, clusters, standby replicas.<br>"
     "MQ, MSK, SQS and DynamoDB Streams deliver at least once. Every consumer is idempotent (DynamoDB idempotency keys). "
     "Every asynchronous target has a DLQ.<br>"
     "Private-app subnets reach the internet only through the NAT gateway of their AZ. Only the payment calls use it. "
     "Private-data subnets have no route to the internet.<br>"
     "Gateway endpoints carry S3 and DynamoDB traffic. Interface endpoints carry EventBridge, Step Functions, SNS, SQS, "
     "Secrets Manager, STS and CloudWatch Logs traffic. AWS delivers that traffic privately on the AWS backbone.<br>"
     "The VGW route to 172.16.0.0/16 is propagated from the Site-to-Site VPN.", "#6c8ebf"),
    ("box", "sg", SG_TABLE, "#DD344C"),
    ("box", "aux", "<b>Security and observability (no arrows)</b><br>Secrets Manager keeps the MQ, Aurora and payment "
     "provider credentials. AWS KMS customer managed keys encrypt the data. Lambda Powertools, X-Ray and CloudWatch alarms "
     "(DLQ depth, Pipes and ESM errors) give observability.", "#666666"),
    ("box", "cert", "<b>Certificates and names</b><br>ACM in us-east-1 for CloudFront (shop.tdsynnexlab.link). "
     "ACM in eu-central-1 for the WebSocket API (ws.shop.tdsynnexlab.link).<br>"
     "<i>Open item: the user confirms the two domain names. The zone has no such records today.</i>", "#DD344C"),
    ("box", "az", "<b>Availability Zones</b><br>Each AZ has the same components. Arrows go only to AZ-a. The Lambda, "
     "RDS Proxy, MSK and endpoint icons in the subnets are the ENIs of regional services.", "#147EBA"),
    ("box", "lines", LINE_STYLES_P1, "#666666"),
]

PAGES = [
    dict(name="1 Overview", title="E-commerce on AWS - serverless core and event-driven backbone (overview)",
         sub="One account (179330777878), Frankfurt (eu-central-1), three AZs. Layers top to bottom: global edge, API, microservices, "
             "orchestration and events, data, VPC. Blue numbers show the main customer journey. Grey arrows show all other connections.",
         scen=[], assoc=["waf", "cognito"]),
    dict(name="2 Customer (synchronous)", title="Page 2 - Customer flows (synchronous): SPA, sign-in, search, cart, WebSocket, checkout start",
         sub="The customer browser starts every flow on this page. Grey components are not part of these flows.",
         scen=P2, assoc=["waf", "cognito"]),
    dict(name="3 Checkout saga", title="Page 3 - Checkout saga (Step Functions Standard) and OrderPlaced fan-out",
         sub="Payment with a task token callback, compensation on failure, result push over the WebSocket, OrderPlaced on the commerce bus.",
         scen=P3, assoc=["waf"]),
    dict(name="4 Fulfillment + notifications", title="Page 4 - Fulfillment over Amazon MQ and customer notifications",
         sub="FulfillOrder goes to the 3PL over the VPN. ShipmentDispatched comes back through EventBridge Pipes. SNS fans out to email, SMS and back office.",
         scen=P4, assoc=[]),
    dict(name="5 Admin + analytics", title="Page 5 - Catalog administration, image processing and clickstream analytics",
         sub="Catalog writes reach OpenSearch through the DynamoDB zero-ETL integration. Images resize on upload. Clickstream goes through MSK to the data lake and the counters.",
         scen=P5, assoc=["waf", "cognito"]),
]


# ================================================================== BUILD
def used_components(scen, assoc):
    u = set()
    for s in scen:
        for st in s["steps"]:
            u.add(st["src"])
            u.add(st["tgt"])
    for k in assoc:
        u.add(ASSOC[k][0])
        u.add(ASSOC[k][1])
    return u


def band(cid, title, y, h, color, right):
    vertex(f"frame-band-{cid}", f"<b>{title}</b>",
           f"rounded=1;arcSize=2;whiteSpace=wrap;html=1;fillColor=light-dark({color}0A,{color}14);fillStyle=auto;strokeColor={color};"
           f"strokeWidth=1;dashed=0;verticalAlign=top;align=left;spacingLeft=10;spacingTop=2;fontSize=13;fontColor={color};{F}",
           BAND_X, y, right - BAND_X, h)


def draw_architecture(used):
    fade = (lambda k: False) if used is None else (lambda k: k not in used)
    group("aws-cloud", "AWS Cloud - account 179330777878", "cloud", CLOUD_X, CLOUD_Y, CLOUD_R - CLOUD_X, CLOUD_H)
    ex_, ey_, ew_, eh_ = EDGE_FRAME
    vertex("frame-band-edge", "<b>Global edge (outside the Region)</b>",
           f"rounded=1;arcSize=2;whiteSpace=wrap;html=1;fillColor=light-dark(#8C4FFF0A,#8C4FFF14);fillStyle=auto;strokeColor=#8C4FFF;"
           f"dashed=1;verticalAlign=top;align=left;spacingLeft=10;spacingTop=2;fontSize=13;fontColor=#8C4FFF;{F}", ex_, ey_, ew_, eh_)
    group("region", "Europe (Frankfurt) eu-central-1", "region", REGION_X, REGION_Y, REGION_R - REGION_X, REGION_H)
    for b in BANDS:
        band(*b)
    group("aux", "Security & observability (no arrows)", "aux", AUX_X, AUX_Y, AUX_W, AUX_H)
    group("vpc", "VPC shop-vpc 10.0.0.0/16", "vpc", VPC_X, VPC_Y, VPC_W, VPC_H)
    pub = ["10.0.0.0/24", "10.0.1.0/24", "10.0.2.0/24"]
    app = ["10.0.16.0/20", "10.0.32.0/20", "10.0.48.0/20"]
    dat = ["10.0.64.0/22", "10.0.68.0/22", "10.0.72.0/22"]
    for i, az in enumerate("abc"):
        lab = f"Availability Zone {az} (eu-central-1{az})" + ("" if i == 0 else " - same components as AZ-a (flows not drawn)")
        group(f"az-{az}", lab, "az", AZ_X[i], AZ_Y, AZ_W, AZ_H)
        group(f"pub-{az}", f"Public subnet {az} {pub[i]}", "pub", AZ_X[i] + 15, PUB_Y, AZ_W - 30, PUB_H)
        group(f"app-{az}", f"Private-app subnet {az} {app[i]}", "priv", AZ_X[i] + 15, APP_Y, AZ_W - 30, APP_H)
        group(f"dat-{az}", f"Private-data subnet {az} {dat[i]}", "priv", AZ_X[i] + 15, DAT_Y, AZ_W - 30, DAT_H)
        rx, rw = AZ_X[i] + 755, AZ_W - 30 - 755 + 15 - 10
        rt_box(f"rt-pub-{az}", f"rtb-public-{az}", [("10.0.0.0/16", "local"), ("0.0.0.0/0", "igw-shop")], rx, PUB_Y + 34, rw)
        rt_box(f"rt-app-{az}", f"rtb-app-{az}", [("10.0.0.0/16", "local"), ("0.0.0.0/0", f"nat-{az}"),
                                                   ("pl-s3", "vpce-s3"), ("pl-ddb", "vpce-ddb")], rx, APP_Y + 34, rw)
        rt_box(f"rt-dat-{az}", f"rtb-data-{az}", [("10.0.0.0/16", "local"), ("172.16.0.0/16", "vgw-shop"),
                                                   ("pl-s3", "vpce-s3"), ("pl-ddb", "vpce-ddb")], rx, DAT_Y + 34, rw)
    for k in COMP:
        svc(k, fade(k))
    for k in ACTORS:
        actor(k, fade(k))
    onprem(fade("onprem-3pl"))


def draw_step_edge(cid, st, color, width=2, with_badge=True, label=None, fill=None):
    start, side = edge(cid, st["src"], st["tgt"], color, st["ex"], st["en"], pts=st["pts"], dashed=st["dashed"], width=width)
    if with_badge:
        lab = label or st["label"]
        if st["b"]:
            badge(f"step-{cid[2:]}", lab, *st["b"], fill or color)
        else:
            step_badge(f"step-{cid[2:]}", lab, start, side, fill or color)


def title_block(pg):
    vertex("title-group", "", "group;" + F, LEFT_X, 30, TOTAL_W, 90, extra=' connectable="0"')
    vertex("title-text", pg["title"], "text;html=1;resizable=1;points=[];autosize=1;align=left;verticalAlign=top;spacingTop=-4;"
           "fontSize=30;fontStyle=1;" + F, 0, 0, TOTAL_W, 42, parent="title-group")
    vertex("subtitle-text", pg["sub"], "text;html=1;resizable=0;points=[];align=left;verticalAlign=top;spacingTop=-4;fontSize=16;"
           + F, 5, 42, TOTAL_W - 10, 25, parent="title-group")
    vertex("title-separator", "", "line;strokeWidth=2;html=1;fontSize=14;strokeColor=#FF9900;" + F, 5, 72, TOTAL_W - 10, 10,
           parent="title-group")


def draw_assoc(keys):
    for k in keys:
        src, tgt, ex, en, pts, label = ASSOC[k]
        edge(f"assoc-{k}", src, tgt, "#879196", ex, en, pts=pts, dotted=True, width=1.5, arrow=False)
        cells.append(f'<mxCell id="assoc-{k}-label" value="{a(label)}" style="{a("edgeLabel;html=1;align=center;verticalAlign=middle;resizable=0;points=[];labelBackgroundColor=none;fontSize=10;fontColor=#545B64;fontStyle=2;" + F)}" '
                     f'connectable="0" vertex="1" parent="assoc-{k}"><mxGeometry x="0" y="-10" relative="1" as="geometry"><mxPoint as="offset"/></mxGeometry></mxCell>')


def build_overview(pg):
    cells.clear()
    title_block(pg)
    draw_architecture(None)
    draw_assoc(pg["assoc"])
    jrefs = {r for _, _, refs in JOURNEY for r in refs}
    jpairs = {(ref(*r)["src"], ref(*r)["tgt"]) for r in jrefs}
    seen = set()
    for pg_n, sc in PAGE_SCEN.items():
        for si, s in enumerate(sc):
            for st in s["steps"]:
                pair = (st["src"], st["tgt"])
                if (pg_n, si, st["label"]) in jrefs or pair in jpairs or pair in seen:
                    continue
                seen.add(pair)
                draw_step_edge(f"e-g{pg_n}{si}{st['label']}", st, GREY_LINE, width=1.25, with_badge=False)
    jsteps = []
    for n, (title, text, refs) in enumerate(JOURNEY, start=1):
        for j, r in enumerate(refs):
            draw_step_edge(f"e-j{n}-{j}", ref(*r), J_COLOR, width=2.5, with_badge=(j == 0 and n not in J_BADGE),
                           label=str(n), fill=J_COLOR)
        if n in J_BADGE:
            badge(f"step-j{n}", str(n), *J_BADGE[n], J_COLOR)
        jsteps.append(dict(label=str(n), title=title, text=text))
    journey = dict(key="j", color=J_COLOR, title="Main customer journey (14 steps)",
                   who="The customer starts the journey in the browser. One number can cover several arrows. "
                       "Pages 2 to 5 show every step in detail, with an event walk.",
                   steps=jsteps)
    hl = legend_panel("L", LEFT_X, CLOUD_Y, LP_W, CLOUD_H, [("scen", journey)])
    hr = legend_panel("R", RP_X, CLOUD_Y, RP_W, CLOUD_H, P1_RIGHT)
    if max(hl, hr) > CLOUD_H:
        print(f"WARNING {pg['name']}: legend content {max(hl, hr)} > panel {CLOUD_H}", file=sys.stderr)
    return "".join(cells)


def build_page(pg):
    if not pg["scen"]:
        return build_overview(pg)
    cells.clear()
    scen = pg["scen"]
    for i, s in enumerate(scen):
        s["color"] = COLORS[i]
        s["key"] = f"s{i + 1}"
    used = used_components(scen, pg["assoc"])
    title_block(pg)
    draw_architecture(used)
    draw_assoc(pg["assoc"])
    for s in scen:
        for st in s["steps"]:
            draw_step_edge(f"e-{s['key']}-{st['label']}", st, s["color"])
    sizes = [sum(2 + len(st["text"]) / 70 for st in s["steps"]) + 3 for s in scen]
    tot, acc, half = sum(sizes), 0, 1
    for i in range(len(scen)):
        acc += sizes[i]
        if acc >= tot / 2:
            half = i + 1
            break
    left = [("scen", s) for s in scen[:half]]
    right = [("scen", s) for s in scen[half:]] + [("box", "lines", LINE_STYLES, "#666666")]
    if pg["name"].startswith(("3", "4")):
        right.append(("box", "ips", "<b>Addresses</b><br>Private IPs come from the VPC plan (10.0.0.0/16) and the 3PL network "
                      "(172.16.0.0/16). Internet addresses use the RFC 5737 documentation ranges.", "#666666"))
    hl = legend_panel("L", LEFT_X, CLOUD_Y, LP_W, CLOUD_H, left)
    hr = legend_panel("R", RP_X, CLOUD_Y, RP_W, CLOUD_H, right)
    if max(hl, hr) > CLOUD_H:
        print(f"WARNING {pg['name']}: legend content {max(hl, hr)} > panel {CLOUD_H}", file=sys.stderr)
    wy = max(CLOUD_B, P3PL[2] + P3PL[4]) + 50
    for s in scen:
        wy += event_walk(s, ACT_X, wy, RACT_X + ACT_W - ACT_X) + 24
    return "".join(cells)


def suffix_ids(body, sfx):
    """Unique cell ids per page: the icon color fixer looks up parents across the whole file."""
    import re
    keep = {"0", "1"}
    return re.sub(r'\b(id|parent|source|target)="([^"]+)"',
                  lambda m: m.group(0) if m.group(2) in keep else f'{m.group(1)}="{m.group(2)}-{sfx}"', body)


pages_xml = []
for n, pg in enumerate(PAGES):
    body = suffix_ids(build_page(pg), f"p{n + 1}")
    pages_xml.append(
        f'<diagram name="{a(pg["name"])}" id="page-{n + 1}"><mxGraphModel dx="2400" dy="1600" grid="0" gridSize="10" guides="1" '
        f'tooltips="1" connect="1" arrows="1" fold="1" page="0" pageScale="1" pageWidth="5000" pageHeight="3600" math="0" shadow="0">'
        f'<root><mxCell id="0"/><mxCell id="1" parent="0"/>{body}</root></mxGraphModel></diagram>')

with open(OUT, "w", encoding="utf-8") as f:
    f.write('<mxfile host="Electron" version="29.6.1">' + "".join(pages_xml) + "</mxfile>\n")
print("wrote", OUT)
