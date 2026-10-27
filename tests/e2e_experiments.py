"""Experiments on the live site: duplicate OrderPlaced (idempotency), broken email consumer → DLQ → redrive, burst, replay."""
import time

from playwright.sync_api import sync_playwright

BASE = "https://shop.tdsynnexlab.link"
errors = []


def checkout(page, ctx):
    page.goto(BASE + "/search?q=Boom", wait_until="networkidle")
    page.locator("#results .card:has(.stock.ok)").first.click()
    page.wait_for_selector("#add:not([disabled])")
    page.click("#add")
    page.wait_for_selector("#add-msg .stock.ok")
    page.goto(BASE + "/cart", wait_until="networkidle")
    page.click("#checkout")
    page.wait_for_url("**/checkout?order=*")
    page.wait_for_selector("#pay-row a", timeout=60000)
    pay = ctx.new_page()
    pay.goto(page.get_attribute("#pay-row a", "href"))
    pay.click("button[data-d=pay]")
    pay.wait_for_function("document.getElementById('done').textContent.length > 0")
    pay.close()
    page.wait_for_selector("#banner.ok", timeout=60000)
    return page.url.split("order=")[1].split("&")[0]


def count(page, text):
    return page.eval_on_selector_all("#bts-list .entry .opname", f"els => els.filter(e => e.textContent === {text!r}).length")


with sync_playwright() as p:
    b = p.chromium.launch()
    ctx = b.new_context(viewport={"width": 1440, "height": 900})
    page = ctx.new_page()
    page.on("console", lambda m: m.type == "error" and errors.append(f"{page.url}: {m.text}"))
    page.goto(BASE + "/", wait_until="networkidle")
    page.click("#persona-list button[data-key=elif]")
    page.wait_for_function("document.querySelector('#ws-state').dataset.state === 'open'", timeout=20000)
    oid = checkout(page, ctx)
    print("order", oid)
    page.wait_for_function("!document.querySelector('#dup').disabled", timeout=30000)
    page.wait_for_timeout(8000)
    page.click("#dup")
    page.wait_for_function("[...document.querySelectorAll('#bts-list .opname')].filter(e => e.textContent === 'Duplicate stopped').length >= 2", timeout=60000)
    page.wait_for_timeout(5000)
    print("duplicate stopped entries:", count(page, "Duplicate stopped"))
    page.screenshot(path="/tmp/vt-dup.png")
    # broken consumer
    page.goto(BASE + "/reports", wait_until="networkidle")
    page.click("#tabs [data-tab='2']")
    page.wait_for_selector("#break")
    page.click("#break")
    page.wait_for_timeout(2000)
    oid2 = checkout(page, ctx)
    print("order with broken email consumer", oid2)
    t0 = time.time()
    page.wait_for_function("[...document.querySelectorAll('#bts-list .opname')].filter(e => e.textContent === 'Consumer error').length >= 3", timeout=180000)
    print("consumer errors after", round(time.time() - t0), "s:", count(page, "Consumer error"))
    page.goto(BASE + "/reports", wait_until="networkidle")
    page.click("#tabs [data-tab='2']")
    for _ in range(12):
        page.wait_for_timeout(10000)
        page.click("#refresh")
        page.wait_for_timeout(3000)
        txt = page.text_content("#tab")
        if "email-dlq (0)" not in txt:
            break
    print("DLQ section:", [h for h in page.eval_on_selector_all("#tab h3", "e => e.map(x => x.textContent)") if "dlq" in h])
    page.click("#fix")
    page.wait_for_timeout(2000)
    page.click("#redrive")
    page.wait_for_timeout(45000)
    print("emails sent after redrive:", count(page, "Delivery"))
    page.click("#burst")
    page.wait_for_timeout(4000)
    page.click("#refresh")
    page.wait_for_timeout(3000)
    print("queues after burst:", page.eval_on_selector_all("#tab table tbody tr", "e => e.map(r => r.textContent.trim().replace(/\\s+/g,' '))")[:4])
    page.screenshot(path="/tmp/vt-reports.png")
    b.close()
print("console errors:", errors)
