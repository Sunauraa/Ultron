"""Pull pop-up text and buttons out of SusBench's injection code, as text only. Usage: extract_susbench.py OUT.json"""

import csv
import html
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2] / "external/SusBench"
TYPES = ("pop-up ad", "confirm shaming", "forced action")


def main():
    rows = list(csv.DictReader((ROOT / "task-list.csv").open()))
    wanted = {r["injection_code"]: r["dark_pattern_type"].strip().lower() for r in rows if r["dark_pattern_type"].strip().lower() in TYPES}
    source = (ROOT / "dark-pattern-browser-extension/injection-mapping.js").read_text()
    starts = [(m.start(), m.group(1)) for m in re.finditer(r'^\s{0,4}"?([a-z0-9_]+)"?:\s*\{\s*$', source, re.M) if m.group(1) in {r["injection_code"] for r in rows}]
    out = []
    for i, (start, key) in enumerate(starts):
        if key not in wanted:
            continue
        block = source[start:starts[i + 1][0] if i + 1 < len(starts) else len(source)]
        block = re.sub(r"(?s)<style>.*?</style>|cssText\s*=\s*`.*?`|style=\"[^\"]*\"|/\*.*?\*/", "", block)
        block = re.sub(r"(?m)^\s*//.*$", "", block)
        strings = re.findall(r"(?:textContent|innerText)\s*=\s*[`'\"]([^`]*?)[`'\"]\s*;", block)
        strings += [re.sub(r"<[^>]+>", " ", s) for s in re.findall(r"<(?:h\d|p|span|div|button|a)\b[^>]*>(.*?)</(?:h\d|p|span|div|button|a)>", block, re.S)]
        buttons = re.findall(r"<button\b[^>]*>(.*?)</button>", block, re.S) + re.findall(r"[Bb](?:tn|utton)\w*\.(?:textContent|innerText|innerHTML)\s*=\s*[`'\"](.*?)[`'\"]\s*;", block)
        clean = lambda x: re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", x))).strip()
        buttons = [b for b in dict.fromkeys(clean(b) for b in buttons) if b]
        strings = [s for s in dict.fromkeys(clean(s) for s in strings) if s and s not in buttons and "${" not in s]
        out.append({"key": key, "type": wanted[key], "text": " ".join(strings)[:900], "buttons": buttons})
    Path(sys.argv[1]).write_text(json.dumps(out, ensure_ascii=False, indent=1))
    for n, x in enumerate(out):
        print(n, x["key"], "|", x["text"][:125], "|", x["buttons"])


if __name__ == "__main__":
    main()
