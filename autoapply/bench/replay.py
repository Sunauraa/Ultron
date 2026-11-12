"""Real application pages, recorded once and replayed offline, so agents can be tested on them without
anything reaching the real site.

record: open the page in a fresh browser and save every response (HTML, scripts, styles, API data) to a HAR.
        It only loads the page: nothing is clicked, typed or sent.
replay: a browser whose every request is answered from the HAR. A request the HAR doesn't have is aborted,
        so nothing leaves this computer. Requests that would send data (POST, PUT, ...) are recorded as the
        page's submission and answered with a stub. The browser listens on a local CDP port, so Ultron and
        Playwright MCP drive it exactly as they drive the user's Chrome in real use.

Usage: python bench/replay.py record URL OUT_DIR
"""

from __future__ import annotations

import asyncio
import base64
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import parse_qs, urljoin, urlparse

from playwright.async_api import Route, async_playwright

SEND_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
LATENCY = 0.15  # seconds added to each data request, like a real network
# Invisible captchas (reCAPTCHA, hCaptcha incl. Recruitee's self-hosted copy, Cloudflare Turnstile) need their company's servers to issue a token, and pages wait for it before sending.
# Offline, they get this stand-in, which hands out a dummy token at once (the same for both arms).
CAPTCHA_SCRIPT = re.compile(r"(recaptcha(\.net|/)|google\.com/recaptcha).*/(api|enterprise)\.js|hcaptcha\.com/1/api\.js|js\.hcaptcha\.com|captcha-(base|assets)\.recruiteecdn\.com/1/(secure-)?api\.js|challenges\.cloudflare\.com/turnstile/.*api\.js")
CAPTCHA_STUB = """(() => {
  // An invisible widget rendered with a callback gets the token when executed (Lever: render(..., {callback}) then execute(id)).
  const callbacks = [];
  const token = 'replay-captcha-token';
  const api = { ready: (f) => setTimeout(f, 0), reset: () => {}, remove: () => {}, setData: () => {}, getResponse: () => token,
                getRespKey: () => 'replay-key',
                render: (el, opts) => { callbacks.push(opts && opts.callback); return callbacks.length - 1; },
                execute: (id, opts) => { const f = callbacks[typeof id === 'number' ? id : callbacks.length - 1];
                                   if (typeof f === 'function') setTimeout(() => f(token), 0);
                                   return Promise.resolve(opts && opts.async ? { response: token, key: 'replay-key' } : token); } };
  window.grecaptcha = Object.assign({ enterprise: api }, api);
  window.hcaptcha = api;
  window.turnstile = Object.assign({}, api, {
    render: (el, opts) => { if (opts && opts.callback) setTimeout(() => opts.callback('replay-captcha-token'), 0); return 'replay'; },
    remove: () => {}, isExpired: () => false });
  const src = (document.currentScript && document.currentScript.src) || '';
  const onload = new URL(src || location.href).searchParams.get('onload');
  if (onload && typeof window[onload] === 'function') setTimeout(window[onload], 0);
})();"""

# Resume uploads first ask the site for a storage address (none were recorded: recording uploads nothing). Offline these
# get a stand-in address of the shape the page's own code reads; the file itself is then "uploaded" there and answered
# by the stub for sends (the same for both arms). Greenhouse's address comes from a recorded GET; Lever sends the file
# with the form.
UPLOAD_STUBS = [
    # Ashby: the createFileUploadHandle mutation's fields (handle, url, fields), as its query asks for them.
    (re.compile(r"jobs\.ashbyhq\.com/api/non-user-graphql\?op=ApiCreateFileUploadHandle"),
     {"data": {"fileUploadHandle": {"handle": "replay-upload-handle",  # its upload bucket (the page's CSP allows only it); the send stub answers
                                    "url": "https://ashbyhq-infra-prd-main-app-uploaded-files-us-east-1.s3.us-east-1.amazonaws.com/", "fields": {},
                                    "__typename": "FileUploadHandle"}}}),
    # Workable: presign answers {uploadPostUrl: {url, fields}, downloadUrl} (read from its form code).
    (re.compile(r"apply\.workable\.com/api/v1/jobs/[^/]+/form/upload/"),
     {"uploadPostUrl": {"url": "https://uploads.replay.invalid/", "fields": {"key": "replay/resume.pdf"}},
      "downloadUrl": "https://uploads.replay.invalid/replay/resume.pdf"}),
    # Teamtailor: POST /uploads/presigned_data answers {url, fields} with a "${filename}" key; Dropzone then posts the
    # file there and reads the stored file's address from the answer's Location header (its upload code).
    (re.compile(r"\.teamtailor\.com/uploads/presigned_data$"),
     {"url": "https://uploads.replay.invalid/", "fields": {"key": "tmp/replay/${filename}"}}),
    # BambooHR: GET /files/post_upload_url answers {url, fileInfo, formInputs}; the file then goes to that url (its fabric.js;
    # a *.bamboohr.com url, as the page's CSP allows only those; the send stub answers, nothing leaves the machine).
    (re.compile(r"\.bamboohr\.com/files/post_upload_url$"),
     {"url": "https://replay-uploads.bamboohr.com/", "fileInfo": "replay-file-id", "formInputs": {"key": "replay/resume.pdf"}}),
]

# Stand-in for a site's thank-you page after a plain form post (the real page was not recorded: nothing was sent then).
SENT_PAGE = "<!doctype html><title>Application submitted</title><h1>Application submitted!</h1><p>Thank you for applying.</p>"


async def record(url: str, out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(record_har_path=str(out / "page.har"), record_har_content="embed",
                                            viewport={"width": 1280, "height": 900}, locale="en-US")
        page = await context.new_page()
        await page.goto(url, wait_until="domcontentloaded", timeout=60000)
        try:
            await page.wait_for_load_state("networkidle", timeout=20000)
        except Exception:
            pass
        await page.wait_for_timeout(3000)
        await page.screenshot(path=str(out / "page.png"), full_page=True)
        await context.close()  # writes the HAR
        await browser.close()
    (out / "meta.json").write_text(json.dumps({"url": url}, indent=1))


def clean_entries(entries: list[dict]) -> list[dict]:
    """Drop recorded responses with an empty body when the same URL was also recorded with its content.
    A script preloaded and then loaded is recorded twice, once empty, and replaying the empty copy breaks the app."""
    def size(e):
        return len(e["response"]["content"].get("text") or "")
    full = {e["request"]["url"] for e in entries if size(e) > 0}
    # A redirect to the same address (a bot check setting a cookie, then answering) would replay as an endless loop.
    answered = {e["request"]["url"] for e in entries if e["response"]["status"] not in (301, 302, 303, 307, 308)}
    def self_redirect(e):
        return e["response"]["status"] in (301, 302, 303, 307, 308) and e["request"]["url"] in answered \
            and urljoin(e["request"]["url"], e["response"].get("redirectURL") or "") == e["request"]["url"]
    return [e for e in entries if not self_redirect(e)
            and (size(e) > 0 or e["request"]["url"] not in full or e["response"]["status"] in (204, 301, 302, 303, 307, 308))]


class Replay:
    """One offline browser for one recorded page. Use as `async with Replay(folder, port) as r:`."""

    def __init__(self, folder: Path, port: int, profile: Path) -> None:
        self.folder, self.port, self.profile = folder, port, profile
        self.url = json.loads((folder / "meta.json").read_text())["url"]
        # POSTs made while the page loaded (GraphQL reads such as Ashby's, bot-check pings whose body changes
        # every time) are answered with their recorded response, matched by URL. Any other POST is a submission.
        har = json.loads((folder / "page.har").read_text())
        entries = har["log"]["entries"] = clean_entries(har["log"]["entries"])
        self.har = profile.parent / f"{profile.name}.har"
        self.har.parent.mkdir(parents=True, exist_ok=True)
        self.har.write_text(json.dumps(har))
        # Cookies the site set while recording (some apps stall without them, and redirects don't replay them).
        # A header can hold several cookies, one per line; nameless or malformed ones are left out.
        self.cookies = [{"name": name.strip(), "value": value, "domain": urlparse(e["request"]["url"]).hostname, "path": "/"}
                        for e in entries for h in e["response"]["headers"] if h["name"].lower() == "set-cookie"
                        for line in h["value"].split("\n")
                        for name, _, value in [line.split(";", 1)[0].partition("=")]
                        if re.fullmatch(r"[!#$%&'*+\-.^_`|~0-9A-Za-z]+", name.strip())]
        # Pages carry time-limited tokens and dates, so the page's clock starts at the recording's time.
        self.recorded_at = datetime.fromisoformat(entries[0]["startedDateTime"].replace("Z", "+00:00"))
        # Start at the address the recorded redirects led to: a replayed redirect aborts a navigation started over CDP.
        for entry in entries:
            location = entry["response"].get("redirectURL")
            if entry["request"]["url"] == self.url and entry["response"]["status"] in (301, 302, 303, 307, 308) and location:
                self.url = urljoin(self.url, location)
        # Several reads can share one address (a GraphQL endpoint), so each is kept with its body.
        self.recorded_posts: dict[tuple[str, str], list[tuple[str, dict]]] = {}
        for e in entries:
            if e["request"]["method"] in SEND_METHODS:
                self.recorded_posts.setdefault((e["request"]["method"], e["request"]["url"]), []).append(
                    ((e["request"].get("postData") or {}).get("text", ""), e["response"]))
        # Search-as-you-type lookups (a city, a school): the live answers to the persona's own queries, fetched by GET
        # when the page was recorded (lookups.json). A typed query gets the answer whose query it starts, or extends.
        path = folder / "lookups.json"
        self.lookups = json.loads(path.read_text()) if path.exists() else []
        # Ashby keeps the form on its server and answers each saved field with the whole form (FormRender), with the
        # saved value in it. The stand-in answers the same way, from the form as recorded; a bare "{}" made the page
        # show "There was a problem with the network connection", which the live site never does.
        self.ashby_form = next((json.loads(e["response"]["content"]["text"])["data"]["jobPosting"]["applicationForm"]
                                for e in entries if "op=ApiJobPosting" in e["request"]["url"] and e["response"]["content"].get("text")), None)
        self.sent: list[dict] = []    # requests that would have sent data
        self.missing: list[str] = []  # GETs the recording doesn't have (aborted)

    async def __aenter__(self) -> "Replay":
        self.playwright = await async_playwright().start()
        self.context = await self.playwright.chromium.launch_persistent_context(
            str(self.profile), headless=True, viewport={"width": 1280, "height": 900}, locale="en-US",
            args=[f"--remote-debugging-port={self.port}", "--remote-debugging-address=127.0.0.1"])
        await self.context.add_cookies(self.cookies)
        await self.context.clock.install(time=self.recorded_at)
        # Routes run newest first, each falling back to the one registered before it:
        # _outside (data-sending requests) -> the HAR -> _missing (abort; nothing reaches the network).
        await self.context.route("**/*", self._missing)
        await self.context.route_from_har(str(self.har), not_found="fallback")
        await self.context.route("**/*", self._outside)
        return self

    async def _outside(self, route: Route) -> None:
        request = route.request
        answer = self.lookup(request.method, request.url, (request.post_data_buffer or b"").decode("utf-8", "replace"))
        if answer is not None:
            await asyncio.sleep(LATENCY)
            await route.fulfill(status=answer["status"], content_type=answer["content_type"], body=base64.b64decode(answer["body_b64"]))
            return
        upload = next((answer for pattern, answer in UPLOAD_STUBS if pattern.search(request.url)), None)
        if upload is not None:
            await asyncio.sleep(LATENCY)
            await route.fulfill(status=200, content_type="application/json", body=json.dumps(upload))
            return
        bodies = self.recorded_posts.get((request.method, request.url))
        recorded = None
        if bodies:
            body = (request.post_data_buffer or b"").decode("utf-8", "replace")
            recorded = next((response for sent, response in bodies if sent == body), bodies[0][1])
        if recorded is not None:
            content = recorded["content"]
            body = base64.b64decode(content.get("text", "")) if content.get("encoding") == "base64" else content.get("text", "").encode()
            headers = {h["name"]: h["value"] for h in recorded["headers"] if h["name"].lower() not in ("content-encoding", "content-length", "transfer-encoding")}
            await route.fulfill(status=recorded["status"], headers=headers, body=body)
            return
        if request.method in SEND_METHODS:
            self.sent.append({"url": request.url, "method": request.method, "headers": await request.all_headers(),
                              "body": (request.post_data_buffer or b"").decode("utf-8", "replace")})
            ashby_op = re.search(r"op=(ApiSetFormValue|ApiSetFormValueToFile)$", request.url)
            if ashby_op and self.ashby_form is not None:
                await route.fulfill(status=200, content_type="application/json", body=json.dumps(self.ashby_saved(ashby_op.group(1), request)))
            elif request.resource_type == "document":  # a plain form post (Lever): sites answer with their thank-you page
                await route.fulfill(status=200, content_type="text/html", body=SENT_PAGE)
            elif urlparse(request.url).netloc == "uploads.replay.invalid":  # a stub upload bucket: answer as S3 does
                await route.fulfill(status=201, headers={"Location": "https://uploads.replay.invalid/tmp/replay/resume.pdf",
                                                         "Access-Control-Allow-Origin": "*", "Access-Control-Expose-Headers": "Location"}, body="")
            else:
                await route.fulfill(status=200, content_type="application/json", body="{}")
            return
        if CAPTCHA_SCRIPT.search(request.url):
            await route.fulfill(status=200, content_type="text/javascript", body=CAPTCHA_STUB)
            return
        if request.resource_type in ("xhr", "fetch"):
            await asyncio.sleep(LATENCY)  # some apps race when data arrives with no network delay
        await route.fallback()  # to the HAR; what it lacks goes on to _missing

    def ashby_saved(self, op: str, request) -> dict:
        """Ashby's answer to a saved field: the form with that field's value in it (shapes from its GraphQL documents)."""
        try:
            variables = json.loads(request.post_data or "{}").get("variables") or {}
        except ValueError:
            variables = {}
        for section in self.ashby_form["sections"]:
            for entry in section["fieldEntries"]:
                if entry["field"].get("path") == variables.get("path"):
                    entry["fieldValue"] = ({"id": "replay-file", "filename": "resume.pdf", "__typename": "File"} if op == "ApiSetFormValueToFile"
                                           else {"value": variables.get("value"), "__typename": "JSONBox"})
        return {"data": {"setFormValueToFile" if op == "ApiSetFormValueToFile" else "setFormValue": self.ashby_form}}

    def lookup(self, method: str, url: str, body: str) -> dict | None:
        """The recorded answer for a search request, or the endpoint's no-results answer; None if not a lookup."""
        for endpoint in self.lookups:
            if method != endpoint["method"] or url.split("?")[0] != endpoint["endpoint"].split("?")[0] \
                    or "?" in endpoint["endpoint"] and not url.startswith(endpoint["endpoint"]):
                continue
            if "json_path" in endpoint:
                typed = json.loads(body or "{}")
                for key in endpoint["json_path"]:
                    typed = typed.get(key, "") if isinstance(typed, dict) else ""
            else:
                typed = (parse_qs(urlparse(url).query).get(endpoint["param"]) or [""])[0] if endpoint["param"] else ""
            typed = str(typed).strip().casefold()
            answers = {query.casefold(): answer for query, answer in endpoint["answers"].items()}
            if typed in answers:
                return answers[typed]
            # Still typing: the shortest recorded query that continues what was typed. Typed past one: the longest it continues.
            longer = sorted((q for q in answers if typed and q.startswith(typed)), key=len)
            shorter = sorted((q for q in answers if q and typed.startswith(q)), key=len, reverse=True)
            return answers[(longer or shorter)[0]] if longer or shorter else endpoint["none"]
        return None

    async def _missing(self, route: Route) -> None:
        self.missing.append(route.request.url)
        await route.abort()

    async def __aexit__(self, *exc) -> None:
        await self.context.close()
        await self.playwright.stop()


if __name__ == "__main__":
    if sys.argv[1] == "record":
        asyncio.run(record(sys.argv[2], Path(sys.argv[3])))
