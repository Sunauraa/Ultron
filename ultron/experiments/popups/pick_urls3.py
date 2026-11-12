"""Pick unused sites from the Tranco list for more training pop-ups. Usage: pick_urls3.py TRANCO.zip OUT_PREFIX PARTS

Skips every site already crawled, so the test sets stay on sites the model never trains on.
Half are European domains, where consent banners are common; the rest are global, in rank order.
"""

import re
import sys
import zipfile
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[2]
EU = re.compile(r"\.(de|fr|it|es|nl|pl|se|no|dk|fi|at|be|ch|pt|cz|ro|hu|gr|ie|sk|bg|hr|si|lt|lv|ee|uk|eu)$")
EACH = 10000


def site(line):
    host = urlparse(line.strip()).netloc or line.strip()
    return host.removeprefix("www.")


def main():
    used = set()
    for path in (ROOT / "data/popups/captures").glob("urls*.txt"):
        if path.name.startswith("urls3_"):  # this script's own output
            continue
        used |= {site(x) for x in path.open() if x.strip()}
    eu, world = [], []
    for line in zipfile.ZipFile(sys.argv[1]).read("top-1m.csv").decode().splitlines():
        name = site(line.split(",")[-1])
        if name in used or name.endswith((".vn", ".gouv.fr", ".gov.uk")):  # government sites share one template with test sites
            continue
        (eu if EU.search(name) else world).append(name)
    picked = eu[:EACH] + world[:EACH]
    parts = int(sys.argv[3])
    for i in range(parts):
        Path(f"{sys.argv[2]}{i}.txt").write_text("".join(f"https://{x}\n" for x in picked[i::parts]))
    print(len(used), "used;", len(eu), "eu left;", len(world), "world left; picked", len(picked))


if __name__ == "__main__":
    main()
