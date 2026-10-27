"""Checkout end to end on the live site: persona → add to cart → checkout → VoltPay (pay|decline|none) → result → 3PL, email."""
import sys
import time

from playwright.sync_api import sync_playwright

BASE = "https://shop.tdsynnexlab.link"
DECISION = sys.argv[1] if len(sys.argv) > 1 else "pay"
errors = []
with sync_playwright() as p:
    b = p.chromium.launch()
    ctx = b.new_context(viewport={"width": 1440, "height": 900})
    page = ctx.new_page()
    page.on("console", lambda m: m.type == "error" and errors.append(f"{page.url}: {m.text}"))
    page.on("pageerror", lambda e: errors.append(f"{page.url}: {e}"))
    page.goto(BASE + "/", wait_until="networkidle")
    page.click("#persona-list button[data-key=can]")
    page.wait_for_function("document.querySelector('#ws-state').dataset.state === 'open'", timeout=20000)
    page.goto(BASE + "/search?q=Echo", wait_until="networkidle")
    page.wait_for_selector("#results .card .stock.ok", timeout=20000)
    page.locator("#results .card:has(.stock.ok)").first.click()
    page.wait_for_selector("#add:not([disabled])", timeout=20000)
    page.click("#add")
    page.wait_for_selector("#add-msg .stock.ok", timeout=20000)
    page.goto(BASE + "/cart", wait_until="networkidle")
    page.wait_for_selector("#checkout", timeout=20000)
    t0 = time.time()
    page.click("#checkout")
    page.wait_for_url("**/checkout?order=*", timeout=20000)
    order = page.url.split("order=")[1].split("&")[0]
    print("order", order)
    page.wait_for_selector("#pay-row a", timeout=60000)
    pay_url = page.get_attribute("#pay-row a", "href")
    print("pay page after", round(time.time() - t0, 1), "s:", pay_url)
    pay = ctx.new_page()
    pay.goto(pay_url, wait_until="networkidle")
    pay.click(f"button[data-d={DECISION}]")
    pay.wait_for_function("document.getElementById('done').textContent.length > 0", timeout=20000)
    print("voltpay:", pay.text_content("#done"))
    if DECISION == "pay":
        page.wait_for_selector("#banner.ok", timeout=60000)
        print("confirmed after", round(time.time() - t0, 1), "s")
        page.wait_for_function("document.querySelectorAll('#progress li.done').length >= 9", timeout=120000)
        print("progress done:", page.eval_on_selector_all("#progress li.done strong", "els => els.map(e => e.textContent)"))
    else:
        page.wait_for_selector("#banner.bad", timeout=200000)
        print("failed path after", round(time.time() - t0, 1), "s:", page.text_content("#banner"))
    page.wait_for_timeout(3000)
    page.screenshot(path=f"/tmp/vt-checkout-{DECISION}.png")
    n = page.eval_on_selector_all("#bts-list .entry", "els => els.length")
    bad = page.eval_on_selector_all("#bts-list .entry.failed .opname", "els => els.map(e => e.textContent)")
    print("panel entries:", n, "failed entries:", bad)
    if DECISION == "pay":
        page.goto(BASE + "/inbox", wait_until="networkidle")
        page.wait_for_selector("#msgs .mail, #msgs .sms", timeout=30000)
        print("inbox:", page.eval_on_selector_all("#msgs .mail header b", "els => els.map(e => e.textContent)")[:3])
    b.close()
print("console errors:", errors)
