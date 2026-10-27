"""Back office (MFA, product save, zero-ETL, image upload + resize) and the lab experiments, on the live site."""
import time

from playwright.sync_api import sync_playwright

BASE = "https://shop.tdsynnexlab.link"
errors = []


def png(path):
    from PIL import Image, ImageDraw
    im = Image.new("RGB", (600, 600), (255, 212, 0))
    ImageDraw.Draw(im).ellipse([150, 150, 450, 450], fill=(17, 19, 26))
    im.save(path)


png("/tmp/vt-upload.png")
with sync_playwright() as p:
    b = p.chromium.launch()
    ctx = b.new_context(viewport={"width": 1440, "height": 900})
    page = ctx.new_page()
    page.on("console", lambda m: m.type == "error" and errors.append(f"{page.url}: {m.text}"))
    page.on("pageerror", lambda e: errors.append(f"{page.url}: {e}"))
    page.goto(BASE + "/admin", wait_until="networkidle")
    page.keyboard.press("Escape")
    page.click("#as-admin")
    page.wait_for_selector("#product-form", timeout=30000)
    ops = page.eval_on_selector_all("#bts-list .entry .opname", "els => els.map(e => e.textContent)")
    print("admin sign-in ops:", ops)
    name = f"Voltaj Demo Speaker {int(time.time()) % 10000}"
    page.fill("#f-name", name)
    page.click("#save")
    page.wait_for_selector("#save-msg .stock.ok", timeout=20000)
    print("saved", name)
    page.set_input_files("#file", "/tmp/vt-upload.png")
    page.click("#upload")
    page.wait_for_selector("#preview:not([hidden])", timeout=60000)
    print("resize done:", page.text_content("#up-msg"))
    page.screenshot(path="/tmp/vt-admin.png")
    time.sleep(12)
    page.goto(BASE + "/search?q=" + name.replace(" ", "+"), wait_until="networkidle")
    page.wait_for_selector("#results .card", timeout=20000)
    print("zero-etl search finds:", page.eval_on_selector_all("#results .card .name", "els => els.map(e => e.textContent)")[:3])
    # lab: reports tabs
    page.goto(BASE + "/reports", wait_until="networkidle")
    for i in range(5):
        page.click(f"#tabs [data-tab='{i}']")
        page.wait_for_timeout(2500)
        print("report tab", i, "ok" if not page.query_selector("#tab .notice.bad") else page.text_content("#tab .notice.bad"))
    # lesson opened from a real panel entry
    page.goto(BASE + "/search?q=hedphones", wait_until="networkidle")
    page.wait_for_selector("#bts-list .learn-link")
    with ctx.expect_page() as lp:
        page.locator("#bts-list .entry:has-text('Search') .learn-link").first.click()
    lesson = lp.value
    lesson.wait_for_load_state("networkidle")
    lesson.wait_for_selector(".tile", timeout=20000)
    lesson.wait_for_timeout(2500)
    print("lesson:", lesson.title(), "| tiles:", lesson.eval_on_selector_all(".tile", "e => e.length"), "| hits:",
          lesson.eval_on_selector_all(".tile.hit", "e => e.length"), "| tree:", bool(lesson.query_selector(".bp-item .tree")))
    lesson.screenshot(path="/tmp/vt-lesson-zero-etl.png", full_page=True)
    b.close()
print("console errors:", errors)
