"""Have the local LLM write varied pop-ups. Usage: gen_dialogs_llm.py OUT.jsonl REQUESTS [SEED] [KIND,KIND]"""

import json
import random
import re
import sys
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from threading import Lock

URL = "http://127.0.0.1:8007/v1/chat/completions"
LANGS = ["English"] * 8 + ["Vietnamese"] * 8 + ["German", "French", "Italian", "Spanish", "Dutch"]
AREAS = ["online banking", "code hosting", "web hosting", "an HR portal", "a hospital portal", "a university portal", "a food delivery app", "ride hailing",
         "an airline", "a hotel site", "a clothing shop", "an electronics shop", "a cloud storage app", "an email client", "a CRM", "accounting software",
         "a government service", "a news site", "a video streaming site", "a game store", "a telecom provider", "an insurance company", "a real estate site",
         "a recruiting site", "a learning platform", "a crypto exchange", "a photo editor", "a project tracker", "a smart-home app", "a car rental site"]
# kind: (what to write, "safe" button meaning, "other" button meaning)
KINDS = {
    "cookie": ("a cookie or privacy consent banner, some short and some with long legal wording", "the button refusing optional cookies", "the button accepting all"),
    "promo": ("a marketing pop-up: discount, newsletter, app download, survey or membership", "the button declining or closing", "the button taking the offer"),
    "notify": ("a request to turn on notifications, location or another permission", "the button declining or postponing", "the button allowing it"),
    "locale": ("a suggestion to switch region, language or to a different site", "the button staying where you are", "the button switching"),
    "session": ("a warning that the session will time out", "the button staying signed in", "the button signing out"),
    "wall": ("a captcha, sign-in requirement, age check or a required choice", "", "the button that proceeds"),
    "danger": ("a confirmation of an action that destroys, overwrites, shares, sends or revokes something, or that spends money, signs a contract or starts a charge. "
               "Vary the verbs widely, and include cases where the risk is only implied", "the button backing out", "the button that carries out the action"),
    "trap_close": ("a scam or deceptive pop-up with a real way out: fake prize, fake virus alert, fake update, fake urgency, a free trial needing a card, guilt-tripping wording",
                   "the button declining or closing, sometimes worded to shame the user", "the button that falls for it"),
    "trap_closed": ("a scam pop-up with no real way out, which asks for card or bank details, a fee, remote access or a download", "", "a button that falls for it"),
}
CHOSEN = sys.argv[4].split(",") if len(sys.argv) > 4 else list(KINDS)
lock = Lock()


def ask(prompt, seed):
    body = {"model": "local", "messages": [{"role": "user", "content": prompt}], "temperature": 0.95, "max_tokens": 1800, "seed": seed}
    request = urllib.request.Request(URL, json.dumps(body).encode(), {"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=600) as response:
        return json.load(response)["choices"][0]["message"]["content"]


def job(args):
    i, seed, out = args
    rng = random.Random(seed)
    kind = rng.choice(CHOSEN)
    lang, area = rng.choice(LANGS), rng.choice(AREAS)
    what, safe, other = KINDS[kind]
    fields = '"text": the pop-up wording, "other": ' + other
    if safe:
        fields += ', "safe": ' + safe
    prompt = (f"Write 12 different realistic website pop-ups in {lang}, as they would appear on {area}. Each one is {what}. "
              f"Make wording, length and tone very different from each other, and use invented brand names. Button labels are 1 to 6 words.\n"
              f"Return only a JSON list of objects with these fields: {fields}.")
    try:
        raw = ask(prompt, seed)
        rows = json.loads(raw[raw.index("["):raw.rindex("]") + 1])
    except Exception as e:
        print(i, "failed", type(e).__name__, flush=True)
        return
    kept = 0
    with lock:
        for row in rows:
            if isinstance(row, dict) and isinstance(row.get("text"), str) and isinstance(row.get("other"), str) and (not safe or isinstance(row.get("safe"), str)):
                out.write(json.dumps({"kind": kind, "lang": lang, "text": re.sub(r"\s+", " ", row["text"]).strip(), "other": row["other"].strip(), "safe": str(row.get("safe") or "").strip()}, ensure_ascii=False) + "\n")
                kept += 1
        out.flush()
    print(i, kind, lang, kept, flush=True)


def main():
    path, requests = sys.argv[1], int(sys.argv[2])
    seed = int(sys.argv[3]) if len(sys.argv) > 3 else 7
    with open(path, "a") as out, ThreadPoolExecutor(2) as pool:
        list(pool.map(job, [(i, seed * 100000 + i, out) for i in range(requests)]))


if __name__ == "__main__":
    main()
