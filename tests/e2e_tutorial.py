"""Tutorial on every page with real mouse clicks: Next to Finish, Close really hides the box, the mini bar appears when the buttons are covered."""
from playwright.sync_api import sync_playwright

BASE = "https://shop.tdsynnexlab.link"
PAGES = ["/", "/search?q=nova", "/p/VLT-1020", "/cart", "/orders", "/inbox", "/admin", "/reports", "/lessons"]
fails, errors = [], []


def click_center(page, sel):
    """Click like a person: at the centre of the visible button, and check that the button is really on top there."""
    el = page.locator(sel).first
    box = el.bounding_box()
    x, y = box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
    top = page.evaluate(f"(() => {{ const e = document.elementFromPoint({x}, {y}); return e && (e.closest('button') || e).outerHTML.slice(0, 80); }})()")
    page.mouse.click(x, y)
    return top


with sync_playwright() as p:
    b = p.chromium.launch()
    ctx = b.new_context(viewport={"width": 1366, "height": 768})
    page = ctx.new_page()
    page.on("pageerror", lambda e: errors.append(f"{page.url}: {e}"))
    page.goto(BASE + "/", wait_until="networkidle")
    page.click("#persona-list button[data-key=mert]")
    page.wait_for_timeout(2000)
    page.evaluate("Object.keys(localStorage).filter(k => k.startsWith('vt_tutor')).forEach(k => localStorage.removeItem(k))")
    for path in PAGES:
        page.goto(BASE + path, wait_until="networkidle")
        page.wait_for_timeout(1200)
        if page.is_hidden("#tutor"):
            fails.append(f"{path}: tutorial not shown"); continue
        n = 0
        while n < 12:
            mini = page.is_visible("#tutor-mini")
            sel = "#tutor-mini [data-tutor=next]" if mini else "#tutor [data-tutor=next]"
            label = page.text_content(sel)
            top = click_center(page, sel)
            if "data-tutor=\"next\"" not in (top or ""):
                fails.append(f"{path}: step {n + 1}: the click point is not the Next button ({top})")
            page.wait_for_timeout(500)
            n += 1
            if label.strip() == "Finish":
                break
        disp = page.evaluate("getComputedStyle(document.querySelector('#tutor')).display")
        mini_disp = page.evaluate("getComputedStyle(document.querySelector('#tutor-mini')).display")
        if disp != "none" or mini_disp != "none":
            fails.append(f"{path}: after Finish display={disp}, mini={mini_disp}")
        print(f"{path}: {n} step(s), finished, display={disp}")
    # Close on a fresh page, and the toggle turns it on again
    page.evaluate("Object.keys(localStorage).filter(k => k.startsWith('vt_tutor_done')).forEach(k => localStorage.removeItem(k))")
    page.goto(BASE + "/", wait_until="networkidle")
    page.wait_for_timeout(1000)
    click_center(page, "#tutor [data-tutor=close]")
    page.wait_for_timeout(300)
    print("close:", page.evaluate("getComputedStyle(document.querySelector('#tutor')).display"))
    click_center(page, "#tutor-toggle")
    page.wait_for_timeout(300)
    print("toggle on again:", page.evaluate("getComputedStyle(document.querySelector('#tutor')).display"))
    b.close()
print("FAILS:", fails)
print("errors:", errors)
