"""Seed Voltaj: catalog (DynamoDB), stock, product illustrations (S3 web bucket), personas (Cognito), order history (Aurora),
popular-product counters, and the SPA config (web/config.json).

Run: uv run --with boto3 --with pillow python tools/seed.py [--skip-images]
"""
import base64
import hashlib
import hmac
import io
import json
import math
import random
import struct
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import boto3
from PIL import Image, ImageDraw, ImageFilter

REGION = "eu-central-1"
ROOT = Path(__file__).resolve().parent.parent
cf = boto3.client("cloudformation", region_name=REGION)


def out(stack, key):
    o = cf.describe_stacks(StackName=stack)["Stacks"][0]["Outputs"]
    return next(x["OutputValue"] for x in o if x["OutputKey"] == key)


random.seed(7)
CATS = {
    "Phones": (["Nova", "Aster", "Pulse", "Orbit"], ["Lite", "", "Pro", "Ultra", "Mini", "Max"], (380, 1450), "#4F7CFF"),
    "Laptops": (["Kite", "Forge", "Atlas", "Quill", "Nimbus"], ["13", "14", "15 Pro", "16 Studio", "Air"], (650, 2600), "#7A5CFF"),
    "Headphones": (["Echo", "Hush", "Tidal", "Bass", "Aura"], ["Buds", "Buds Pro", "Over-Ear", "Studio", "Sport"], (39, 420), "#00A3A3"),
    "Watches": (["Tempo", "Stride", "Halo", "Pace", "Chrono"], ["Fit", "Active", "Classic", "Pro", "Kids"], (49, 650), "#FF7A45"),
    "Tablets": (["Slate", "Canvas", "Leaf", "Folio", "Pad"], ["8", "10", "11 Pro", "12.9 Pro", "Kids"], (180, 1300), "#2BB673"),
    "Speakers": (["Boom", "Sonic", "Ember", "Wave", "Cube"], ["Go", "Mini", "Home", "Max", "Party"], (29, 520), "#E2468C"),
    "Cameras": (["Lumo", "Frame", "Iris", "Prism", "Shutter"], ["Action", "Vlog", "Mirrorless", "Pro X", "Instant"], (99, 2400), "#D99A00"),
    "Accessories": (["Volt", "Link", "Grip", "Dock", "Juice"], ["Charger 65W", "Power Bank 20K", "USB-C Hub", "Cable 2m", "MagStand", "Case"], (9, 129), "#64748B"),
}
BRANDS = ["Voltaj Labs", "Northwind", "Kestrel", "Lumen", "Arcadia", "Tessera", "Zephyr"]
ADJ = {"Phones": "6.4-inch OLED, all-day battery", "Laptops": "light aluminium body, fast SSD", "Headphones": "active noise cancelling",
       "Watches": "heart-rate and GPS tracking", "Tablets": "bright display, pen support", "Speakers": "deep bass, water resistant",
       "Cameras": "4K video, image stabilisation", "Accessories": "fast charging, durable build"}


def catalog():
    items, n = [], 0
    for cat, (series, variants, (lo, hi), color) in CATS.items():
        combos = [(s, v) for s in series for v in variants]
        random.shuffle(combos)
        for s, v in combos[:25]:
            n += 1
            sku = f"VLT-{1000 + n}"
            price = round(random.uniform(lo, hi) / 5) * 5 - 0.01
            items.append({"sku": sku, "name": f"{s} {v}".strip(), "brand": random.choice(BRANDS), "category": cat, "price": round(price, 2),
                          "currency": "EUR", "rating": round(random.uniform(3.6, 4.9), 1), "rank": n, "color": color,
                          "short": f"{s} {v}: {ADJ[cat]}.".replace("  ", " "), "tags": [cat.lower(), s.lower()],
                          "stock": random.choice([0, 3, 8, 12, 25, 40, 60]) if n % 17 else 2})
    return items


# ------------------------------------------------------------------ illustrations
def hexrgb(h):
    return tuple(int(h[i:i + 2], 16) for i in (1, 3, 5))


def mix(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def illustrate(p, size=960):
    base = hexrgb(p["color"])
    rnd = random.Random(p["sku"])
    hue_shift = rnd.uniform(-0.15, 0.15)
    tint = mix(base, (255, 255, 255), 0.82 + hue_shift / 3)
    img = Image.new("RGB", (size, size), tint)
    d = ImageDraw.Draw(img)
    for r in range(size, 0, -8):  # soft radial glow
        t = r / size
        d.ellipse([size / 2 - r * .75, size * .48 - r * .75, size / 2 + r * .75, size * .48 + r * .75], fill=mix(mix(base, (255, 255, 255), .55), tint, t))
    shadow = Image.new("L", (size, size), 0)
    sd = ImageDraw.Draw(shadow)
    sd.ellipse([size * .25, size * .80, size * .75, size * .88], fill=110)
    img.paste((0, 0, 0), mask=shadow.filter(ImageFilter.GaussianBlur(24)).point(lambda v: v * 0.5))
    d = ImageDraw.Draw(img)
    dark, body = (28, 30, 38), mix(base, (20, 20, 30), rnd.uniform(0.15, 0.55))
    accent = mix(base, (255, 255, 255), 0.25)
    c, s = size / 2, size
    cat = p["category"]
    if cat == "Phones":
        d.rounded_rectangle([c - s * .17, s * .14, c + s * .17, s * .82], radius=s * .06, fill=body)
        d.rounded_rectangle([c - s * .155, s * .16, c + s * .155, s * .80], radius=s * .05, fill=dark)
        for i in range(5):
            d.rounded_rectangle([c - s * .12, s * (.24 + i * .1), c + s * .12, s * (.30 + i * .1)], radius=s * .02, fill=mix(accent, dark, i * .15))
        d.ellipse([c - s * .015, s * .175, c + s * .015, s * .205], fill=(60, 60, 70))
    elif cat == "Laptops":
        d.rounded_rectangle([c - s * .32, s * .22, c + s * .32, s * .64], radius=s * .03, fill=body)
        d.rectangle([c - s * .29, s * .25, c + s * .29, s * .61], fill=dark)
        d.polygon([(c - s * .4, s * .66), (c + s * .4, s * .66), (c + s * .36, s * .74), (c - s * .36, s * .74)], fill=mix(body, (255, 255, 255), .25))
        for i in range(4):
            d.rectangle([c - s * .25, s * (.31 + i * .07), c + s * (.05 + .05 * i), s * (.35 + i * .07)], fill=mix(accent, dark, i * .2))
    elif cat == "Headphones":
        d.arc([c - s * .28, s * .16, c + s * .28, s * .72], 190, 350, fill=body, width=int(s * .05))
        for x in (-1, 1):
            d.rounded_rectangle([c + x * s * .27 - s * .09, s * .42, c + x * s * .27 + s * .09, s * .72], radius=s * .07, fill=body)
            d.rounded_rectangle([c + x * s * .27 - s * .06, s * .46, c + x * s * .27 + s * .06, s * .68], radius=s * .05, fill=accent)
    elif cat == "Watches":
        d.rounded_rectangle([c - s * .09, s * .08, c + s * .09, s * .9], radius=s * .05, fill=mix(body, (255, 255, 255), .2))
        d.rounded_rectangle([c - s * .17, s * .3, c + s * .17, s * .7], radius=s * .07, fill=body)
        d.rounded_rectangle([c - s * .145, s * .325, c + s * .145, s * .675], radius=s * .06, fill=dark)
        d.arc([c - s * .1, s * .4, c + s * .1, s * .6], -90, 200, fill=accent, width=int(s * .025))
    elif cat == "Tablets":
        d.rounded_rectangle([c - s * .27, s * .16, c + s * .27, s * .80], radius=s * .05, fill=body)
        d.rounded_rectangle([c - s * .245, s * .19, c + s * .245, s * .77], radius=s * .035, fill=dark)
        for i in range(3):
            for j in range(3):
                d.rounded_rectangle([c - s * .2 + j * s * .14, s * .26 + i * s * .15, c - s * .1 + j * s * .14, s * .36 + i * s * .15], radius=s * .02,
                                    fill=mix(accent, dark, (i + j) * .12))
    elif cat == "Speakers":
        d.rounded_rectangle([c - s * .2, s * .16, c + s * .2, s * .80], radius=s * .1, fill=body)
        for cy, r in ((s * .36, s * .1), (s * .62, s * .13)):
            d.ellipse([c - r, cy - r, c + r, cy + r], fill=dark)
            d.ellipse([c - r * .45, cy - r * .45, c + r * .45, cy + r * .45], fill=accent)
    elif cat == "Cameras":
        d.rounded_rectangle([c - s * .3, s * .3, c + s * .3, s * .72], radius=s * .05, fill=body)
        d.rounded_rectangle([c - s * .22, s * .24, c - s * .06, s * .32], radius=s * .02, fill=body)
        for r, col in ((s * .16, dark), (s * .12, (60, 64, 80)), (s * .07, accent)):
            d.ellipse([c - r, s * .51 - r, c + r, s * .51 + r], fill=col)
        d.ellipse([c + s * .19, s * .35, c + s * .25, s * .41], fill=accent)
    else:
        d.rounded_rectangle([c - s * .16, s * .26, c + s * .16, s * .62], radius=s * .05, fill=body)
        d.rectangle([c - s * .06, s * .17, c - s * .03, s * .27], fill=(190, 190, 200))
        d.rectangle([c + s * .03, s * .17, c + s * .06, s * .27], fill=(190, 190, 200))
        d.line([(c, s * .62), (c, s * .72), (c + s * .2, s * .78), (c + s * .3, s * .7)], fill=body, width=int(s * .03), joint="curve")
        d.polygon([(c - s * .03, s * .33), (c + s * .04, s * .33), (c - s * .005, s * .44), (c + s * .05, s * .44),
                   (c - s * .04, s * .56), (c - s * .01, s * .46), (c - s * .06, s * .46)], fill=accent)
    return img


def webp(img, px):
    im = img.resize((px, px), Image.LANCZOS)
    buf = io.BytesIO()
    im.save(buf, "WEBP", quality=84)
    return buf.getvalue()


# ------------------------------------------------------------------ personas
PERSONAS = [
    {"key": "elif", "name": "Elif Yılmaz", "email": "elif@voltaj.shop", "city": "İstanbul", "smsOptIn": True, "likes": ["Phones", "Watches"],
     "story": "Product designer. Changes phones every two years and wants SMS updates."},
    {"key": "mert", "name": "Mert Kaya", "email": "mert@voltaj.shop", "city": "Ankara", "smsOptIn": False, "likes": ["Laptops", "Accessories"],
     "story": "Software student. Builds a gaming setup on a budget."},
    {"key": "zeynep", "name": "Zeynep Demir", "email": "zeynep@voltaj.shop", "city": "İzmir", "smsOptIn": False, "likes": ["Cameras", "Tablets"],
     "story": "Travel photographer. Buys lenses, cameras and tablets for editing."},
    {"key": "can", "name": "Can Öztürk", "email": "can@voltaj.shop", "city": "Bursa", "smsOptIn": True, "likes": ["Headphones", "Speakers"],
     "story": "Music producer. Cares about sound and fast delivery."},
    {"key": "ayse", "name": "Ayşe Şahin", "email": "ayse@voltaj.shop", "city": "Antalya", "smsOptIn": False, "likes": ["Speakers", "Watches"],
     "story": "Runs a small hotel. Buys smart speakers and watches for the team."},
]
ADMIN = {"key": "deniz", "name": "Deniz Arslan", "email": "demo-admin@voltaj.shop", "city": "İstanbul", "smsOptIn": False, "admin": True,
         "story": "Back-office demo admin. Can change only products whose SKU starts with demo-."}


def pw(key):
    return "Voltaj-" + hashlib.sha256(f"voltaj-demo-{key}".encode()).hexdigest()[:8] + "A1"


def totp(secret_b32, t=None):
    key = base64.b32decode(secret_b32 + "=" * (-len(secret_b32) % 8))
    counter = int((t or time.time()) // 30)
    h = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    o = h[-1] & 15
    return f"{(struct.unpack('>I', h[o:o + 4])[0] & 0x7FFFFFFF) % 1000000:06d}"


def ensure_user(idp, pool, client, p):
    try:
        idp.admin_create_user(UserPoolId=pool, Username=p["email"], MessageAction="SUPPRESS", UserAttributes=[
            {"Name": "email", "Value": p["email"]}, {"Name": "email_verified", "Value": "true"}, {"Name": "name", "Value": p["name"]}])
    except idp.exceptions.UsernameExistsException:
        pass
    idp.admin_set_user_password(UserPoolId=pool, Username=p["email"], Password=pw(p["key"]), Permanent=True)
    u = idp.admin_get_user(UserPoolId=pool, Username=p["email"])
    return next(a["Value"] for a in u["UserAttributes"] if a["Name"] == "sub")


def setup_admin_totp(idp, pool, client):
    idp.admin_add_user_to_group(UserPoolId=pool, Username=ADMIN["email"], GroupName="admins")
    cache = ROOT / "build" / "admin-totp.txt"
    u = idp.admin_get_user(UserPoolId=pool, Username=ADMIN["email"])
    if cache.exists() and u.get("PreferredMfaSetting") == "SOFTWARE_TOKEN_MFA":
        return cache.read_text().strip()
    idp.admin_set_user_mfa_preference(UserPoolId=pool, Username=ADMIN["email"], SoftwareTokenMfaSettings={"Enabled": False, "PreferredMfa": False})
    auth = idp.initiate_auth(ClientId=client, AuthFlow="USER_PASSWORD_AUTH", AuthParameters={"USERNAME": ADMIN["email"], "PASSWORD": pw("deniz")})
    token = auth["AuthenticationResult"]["AccessToken"]
    secret = idp.associate_software_token(AccessToken=token)["SecretCode"]
    idp.verify_software_token(AccessToken=token, UserCode=totp(secret), FriendlyDeviceName="voltaj-demo")
    idp.admin_set_user_mfa_preference(UserPoolId=pool, Username=ADMIN["email"], SoftwareTokenMfaSettings={"Enabled": True, "PreferredMfa": True})
    cache.write_text(secret)
    return secret


def main():
    skip_images = "--skip-images" in sys.argv
    ddb = boto3.client("dynamodb", region_name=REGION)
    s3 = boto3.client("s3", region_name=REGION)
    idp = boto3.client("cognito-idp", region_name=REGION)
    lam = boto3.client("lambda", region_name=REGION)
    web = out("voltaj-data", "WebBucket")
    pool, client = out("voltaj-app", "UserPoolId"), out("voltaj-app", "UserPoolClientId")
    (ROOT / "build").mkdir(exist_ok=True)

    items = catalog()
    print(f"catalog: {len(items)} products")
    reqs_c, reqs_s = [], []
    for p in items:
        reqs_c.append({"PutRequest": {"Item": {
            "pk": {"S": f"SKU#{p['sku']}"}, "sku": {"S": p["sku"]}, "name": {"S": p["name"]}, "brand": {"S": p["brand"]},
            "category": {"S": p["category"]}, "price": {"N": str(p["price"])}, "currency": {"S": "EUR"}, "rating": {"N": str(p["rating"])},
            "rank": {"N": str(p["rank"])}, "short": {"S": p["short"]}, "tags": {"L": [{"S": t} for t in p["tags"]]},
            "image": {"S": f"images/{p['sku']}/md.webp"}, "updatedAt": {"N": str(int(time.time()))}}}})
        reqs_s.append({"PutRequest": {"Item": {"pk": {"S": f"SKU#{p['sku']}"}, "available": {"N": str(p["stock"])}, "reserved": {"N": "0"}}}})
    for table, reqs in (("voltaj-catalog", reqs_c), ("voltaj-stock", reqs_s)):
        for i in range(0, len(reqs), 25):
            batch = {table: reqs[i:i + 25]}
            while batch:
                batch = ddb.batch_write_item(RequestItems=batch).get("UnprocessedItems") or None
    if not skip_images:
        for n, p in enumerate(items):
            img = illustrate(p)
            for name, px in (("sm", 240), ("md", 480), ("lg", 960)):
                s3.put_object(Bucket=web, Key=f"images/{p['sku']}/{name}.webp", Body=webp(img, px), ContentType="image/webp",
                              CacheControl="public, max-age=86400")
            if n % 40 == 0:
                print(f"  images {n}/{len(items)}")
    # popular counters (a start value, the clickstream adds to it)
    for p in random.sample(items, 30):
        ddb.put_item(TableName="voltaj-counters", Item={"pk": {"S": f"POP#SKU#{p['sku']}"}, "views": {"N": str(random.randint(20, 400))}})

    # personas
    people = []
    for p in PERSONAS + [ADMIN]:
        sub = ensure_user(idp, pool, client, p)
        people.append({**p, "sub": sub, "password": pw(p["key"])})
    secret = setup_admin_totp(idp, pool, client)
    print("personas ready")

    # order history in Aurora
    by_cat = {}
    for p in items:
        by_cat.setdefault(p["category"], []).append(p)
    orders = []
    now = datetime.now(timezone.utc)
    for person in people[:-1]:
        for k in range(random.randint(3, 6)):
            lines = []
            for _ in range(random.randint(1, 3)):
                prod = random.choice(by_cat[random.choice(person["likes"])])
                if prod["sku"] not in [x["sku"] for x in lines]:
                    lines.append({"sku": prod["sku"], "name": prod["name"], "qty": random.choice([1, 1, 1, 2]), "price": prod["price"]})
            orders.append({"id": f"o-hist-{person['key']}-{k + 1}", "customerId": person["sub"], "status": "DELIVERED",
                           "total": round(sum(x["qty"] * x["price"] for x in lines), 2), "lines": lines,
                           "date": (now - timedelta(days=random.randint(5, 400))).isoformat()})
    r = lam.invoke(FunctionName="voltaj-order", Payload=json.dumps({"action": "migrate", "customers": [
        {"id": p["sub"], "name": p["name"], "email": p["email"], "city": p["city"], "smsOptIn": p["smsOptIn"]} for p in people],
        "orders": orders}).encode())
    print("aurora:", r["Payload"].read().decode()[:200])

    # SPA config and the persona guard parameter
    cfg = {"region": REGION, "userPoolId": pool, "clientId": client, "wsUrl": "wss://ws.shop.tdsynnexlab.link",
           "payUrl": "https://pay.tdsynnexlab.link", "diagram": "/diagram/",
           "personas": [{k: p[k] for k in ("key", "name", "email", "password", "city", "smsOptIn", "story", "likes", "sub") if k in p}
                        for p in people[:-1]],
           "demoAdmin": {"key": ADMIN["key"], "name": ADMIN["name"], "email": ADMIN["email"], "password": pw("deniz"), "totpSecret": secret,
                         "story": ADMIN["story"]},
           "categories": list(CATS)}
    (ROOT / "web" / "config.json").write_text(json.dumps(cfg, ensure_ascii=False, indent=1))
    (ROOT / "build" / "personas.json").write_text(json.dumps([{"username": p["email"], "password": p["password"]} for p in people]))
    print("wrote web/config.json and build/personas.json")


if __name__ == "__main__":
    main()
