"""Smoke test on the live site: pages load without console errors, persona sign-in, search, panel entries."""
import json
import sys

from playwright.sync_api import sync_playwright

BASE = sys.argv[1] if len(sys.argv) > 1 else "https://shop.tdsynnexlab.link"
errors = []
with sync_playwright() as p:
    b = p.chromium.launch()
    ctx = b.new_context(viewport={"width": 1440, "height": 900})
    page = ctx.new_page()
    page.on("console", lambda m: m.type == "error" and errors.append(f"{page.url}: {m.text}"))
    page.on("pageerror", lambda e: errors.append(f"{page.url}: {e}"))
    page.goto(BASE + "/", wait_until="networkidle")
    page.wait_for_selector("#persona-dialog[open]", timeout=10000)
    page.click("#persona-list button[data-key=elif]")
    page.wait_for_function("document.querySelector('#persona-name').textContent.includes('Elif')", timeout=15000)
    page.wait_for_function("document.querySelector('#ws-state').dataset.state === 'open'", timeout=15000)
    page.wait_for_selector("#popular-grid .card", timeout=20000)
    n = page.eval_on_selector_all("#bts-list .entry", "els => els.length")
    print("home ok, panel entries:", n)
    page.screenshot(path="/tmp/vt-home.png")
    page.goto(BASE + "/search?q=hedphones", wait_until="networkidle")
    page.wait_for_selector("#results .card", timeout=20000)
    print("search results:", page.eval_on_selector_all("#results .card", "els => els.length"))
    page.screenshot(path="/tmp/vt-search.png")
    for path in ["/orders", "/inbox", "/reports", "/lessons", "/admin", "/diagram?page=3&sc=p3s1&st=2", "/learn/fanout"]:
        page.goto(BASE + path, wait_until="networkidle")
        page.wait_for_timeout(1500)
        print(path, "→", page.title())
    page.screenshot(path="/tmp/vt-lesson.png", full_page=False)
    b.close()
print("console errors:", json.dumps(errors, indent=1))
