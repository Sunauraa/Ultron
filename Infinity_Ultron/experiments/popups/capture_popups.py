"""Open public pages with scripts on and record any pop-up, without ever interacting with it.

Usage: capture_popups.py URL_FILE OUT_DIR

Safeguards: Chromium's sandbox stays on, each site gets a fresh profile, downloads and permissions
are off, and every request other than GET or HEAD is blocked, so nothing can be submitted. The only
input is scrolling. Native alert() boxes are dismissed because the page hangs otherwise. Everything
captured is untrusted page content.
"""

import asyncio
import hashlib
import json
import sys
from pathlib import Path
from urllib.parse import urlparse

from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parents[2]
CHROME = ROOT / ".cache/pw/chromium-1248/chrome-linux64/chrome"
WORKERS = 12
SETTLE_MS = 7000

# Records notification requests and always refuses them.
INIT = """
window.__notify = 0;
if (window.Notification) {
  Notification.requestPermission = function () { window.__notify++; return Promise.resolve('denied'); };
}
"""

# Finds the outermost visible modal-like elements, going through open shadow roots.
FIND = """
() => {
  const W = innerWidth, H = innerHeight;
  const CLICK = 'button,a[href],[role=button],[role=link],input[type=button],input[type=submit]';
  function walk(root, out) {
    for (const el of root.querySelectorAll('*')) {
      out.push(el);
      if (el.shadowRoot) walk(el.shadowRoot, out);
    }
    return out;
  }
  function visible(el) {
    const s = getComputedStyle(el), r = el.getBoundingClientRect();
    return s.display !== 'none' && s.visibility !== 'hidden' && +s.opacity > 0.05 &&
      r.width > 8 && r.height > 8 && r.bottom > 0 && r.right > 0 && r.top < H && r.left < W;
  }
  function signal(el) {
    const role = el.getAttribute('role');
    if (role === 'dialog' || role === 'alertdialog') return role;
    if (el.getAttribute('aria-modal') === 'true') return 'aria-modal';
    if (el.tagName === 'DIALOG' && el.open) return 'dialog';
    const s = getComputedStyle(el);
    if (s.position !== 'fixed') return null;
    if (el.closest('header,nav,footer,[role=navigation],[role=banner]')) return null;
    const r = el.getBoundingClientRect();
    if (r.height > 1.2 * H || r.height < 60) return null;  // page wrappers and thin menu bars
    return r.width * r.height >= 0.02 * W * H ? 'fixed' : null;
  }
  function clickables(el) {
    const found = [...el.querySelectorAll(CLICK)];
    for (const inner of walk(el, [])) if (inner.shadowRoot) found.push(...inner.shadowRoot.querySelectorAll(CLICK));
    return found.filter(visible);
  }
  function describe(b) {
    const s = getComputedStyle(b), q = b.getBoundingClientRect();
    return {
      text: (b.innerText || b.value || '').trim().slice(0, 120),
      aria: b.getAttribute('aria-label') || b.getAttribute('title') || '',
      tag: b.tagName.toLowerCase(),
      href: b.href ? b.href.slice(0, 200) : '',
      rect: [q.x, q.y, q.width, q.height].map(Math.round),
      color: s.color, background: s.backgroundColor, font_px: parseFloat(s.fontSize),
    };
  }
  const hits = [], chosen = [];
  for (const el of walk(document, [])) {
    if (!visible(el) || chosen.some(c => c.contains(el))) continue;
    const why = signal(el);
    if (!why) continue;
    const text = (el.innerText || '').trim();
    const buttons = clickables(el);
    if (text.length < 10 || !buttons.length || buttons.length > 15) continue;
    chosen.push(el);
    const r = el.getBoundingClientRect();
    hits.push({
      signal: why,
      text: text.slice(0, 2000),
      rect: [r.x, r.y, r.width, r.height].map(Math.round),
      buttons: buttons.map(describe),
    });
  }
  // A consent box in an iframe is often not fixed inside its own document, so a subframe
  // that the page overlays is recorded whole.
  if (window !== top && !hits.length && document.body && visible(document.body)) {
    const text = (document.body.innerText || '').trim();
    const buttons = clickables(document.body);
    if (text.length >= 10 && buttons.length && buttons.length <= 15) {
      hits.push({ signal: 'subframe', text: text.slice(0, 2000), rect: [0, 0, W, H], buttons: buttons.map(describe) });
    }
  }
  return { hits, notify: window.__notify || 0, lang: document.documentElement.lang || '' };
}
"""


# True if an iframe is large enough to be a dialog and sits in a fixed-position container.
OVERLAID = """
el => {
  const r = el.getBoundingClientRect();
  if (r.width < 200 || r.height < 80) return false;
  for (let n = el; n && n.nodeType === 1; n = n.parentElement || (n.getRootNode() && n.getRootNode().host)) {
    if (getComputedStyle(n).position === 'fixed') return true;
  }
  return false;
}
"""


async def block_writes(route):
    if route.request.method in ("GET", "HEAD"):
        await route.continue_()
    else:
        await route.abort()


async def capture(browser, url, shots):
    record = {"url": url, "native": [], "popups": [], "notify": 0, "lang": "", "error": None}

    async def on_dialog(dialog):
        record["native"].append({"type": dialog.type, "text": dialog.message[:500]})
        await dialog.dismiss()

    context = await browser.new_context(
        viewport={"width": 1280, "height": 800}, accept_downloads=False, permissions=[],
    )
    try:
        await context.add_init_script(INIT)
        await context.route("**/*", block_writes)
        page = await context.new_page()
        page.on("dialog", on_dialog)
        await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(SETTLE_MS)
        await page.mouse.wheel(0, 800)  # some pop-ups only appear on scroll
        await page.wait_for_timeout(2000)
        record["final_url"] = page.url
        name = hashlib.sha256(url.encode()).hexdigest()[:12]
        for i, frame in enumerate(page.frames):
            try:
                found = await asyncio.wait_for(frame.evaluate(FIND), 10)
            except Exception:
                continue  # frames may detach or block scripts
            if i == 0:
                record["notify"], record["lang"] = found["notify"], found["lang"]
            if i and found["hits"] and found["hits"][0]["signal"] == "subframe":
                overlaid = await (await frame.frame_element()).evaluate(OVERLAID)
                if not overlaid:
                    continue
            for hit in found["hits"]:
                hit["frame"] = urlparse(frame.url).netloc
                record["popups"].append(hit)
        if record["popups"] or record["native"]:
            shot = shots / f"{name}.png"
            await page.screenshot(path=shot, timeout=10000)
            record["screenshot"] = shot.name
    except Exception as e:
        record["error"] = f"{type(e).__name__}: {str(e)[:200]}"
    finally:
        await context.close()
    return record


async def main():
    urls = [u.strip() for u in Path(sys.argv[1]).read_text().splitlines() if u.strip() and not u.startswith("#")]
    out = Path(sys.argv[2])
    shots = out / "screenshots"
    shots.mkdir(parents=True, exist_ok=True)
    limit = asyncio.Semaphore(WORKERS)
    log = (out / "captured.jsonl").open("a")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, executable_path=str(CHROME), chromium_sandbox=True)

        async def one(url):
            async with limit:
                try:
                    record = await asyncio.wait_for(capture(browser, url, shots), 90)
                except asyncio.TimeoutError:
                    record = {"url": url, "error": "timeout", "popups": [], "native": []}
            log.write(json.dumps(record, ensure_ascii=False) + "\n")
            log.flush()
            print(f"{url[:50]:50} popups={len(record['popups'])} native={len(record['native'])} {record['error'] or ''}"[:140], flush=True)

        await asyncio.gather(*(one(u) for u in urls))
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
