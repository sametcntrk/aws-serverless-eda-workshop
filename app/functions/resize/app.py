"""Lambda resize: S3 Object Created (default bus) → three WebP sizes in the web bucket."""
import io
import os

from PIL import Image

from voltaj import trace

WEB = os.environ["WEB_BUCKET"]
MAX_BYTES = 2_000_000
SIZES = {"sm": 240, "md": 480, "lg": 960}
s3 = trace.client("s3")


def lambda_handler(event, context):
    d = event["detail"]
    bucket, key = d["bucket"]["name"], d["object"]["key"]
    sku = key.split("/")[0]
    meta = s3.head_object(Bucket=bucket, Key=key)
    trace.begin(meta["Metadata"].get("cid"), meta["Metadata"].get("vid"), fn="resize")
    trace.note("eb", "Rule image-uploaded", "S3 sent Object Created to the default bus. The rule matched the uploads bucket.",
               sc="p5s5", st="2", event={"source": event.get("source"), "detailType": event.get("detail-type"), "bus": "default",
                                          "keys": {"bucket": bucket, "key": key, "size": d["object"].get("size")}})
    if meta["ContentLength"] > MAX_BYTES:
        trace.note("guard", "Too large", f"The image has {meta['ContentLength']} bytes. The limit is {MAX_BYTES}. No resize.", ok=False)
        trace.flush()
        return {"skipped": True}
    trace.step("p5s5", "3")
    src = s3.get_object(Bucket=bucket, Key=key)["Body"].read()
    img = Image.open(io.BytesIO(src)).convert("RGB")
    trace.step("p5s5", "4")
    for name, px in SIZES.items():
        im = img.copy()
        im.thumbnail((px, px))
        canvas = Image.new("RGB", (px, px), (255, 255, 255))
        canvas.paste(im, ((px - im.width) // 2, (px - im.height) // 2))
        buf = io.BytesIO()
        canvas.save(buf, "WEBP", quality=82)
        s3.put_object(Bucket=WEB, Key=f"images/{sku}/{name}.webp", Body=buf.getvalue(), ContentType="image/webp",
                      CacheControl="public, max-age=60")
    trace.note("cf", "Served by CloudFront", f"The new sizes are at /images/{sku}/sm|md|lg.webp. CloudFront caches them for 60 s.",
               ui="image-ready", data={"sku": sku})
    trace.flush()
    return {"sku": sku}
