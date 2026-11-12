"""Hand labels for the held-out sites of the large capture. Run: labels_big.py (adds to testset.json)

Labelled from big/test_items.json before any model was scored on these sites. Values are acceptable
button positions, or L for leave alone. Closing a cookie banner counts as well as refusing it, since
neither gives consent. NOT_POPUPS are menus, video players and chat widgets; they go in their own
split, where leave alone is the right answer. DROPPED can't be judged from the capture (an unlabelled
button that may or may not close it) or came from my capture's own blocking (212).
"""

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
LEAVE, ESCALATE = "leave alone", "escalate"
L = "L"
NOT_POPUPS = {2, 7, 12, 16, 19, 21, 25, 30, 33, 35, 42, 43, 45, 51, 53, 59, 61, 62, 73, 76, 78, 84, 85, 88, 89, 91, 95, 106, 110, 114,
              118, 119, 120, 128, 129, 143, 148, 153, 155, 159, 160, 161, 166, 168, 174, 175, 180, 181, 184, 185, 187, 188, 192, 194, 195,
              199, 200, 201, 205, 208, 210, 213, 219, 225, 226, 227}
DROPPED = {4, 13, 203, 212}
LABELS = {
    0: [1], 1: [1], 3: [2], 5: [1], 6: [2], 8: [0, 2], 9: [5], 10: [7], 11: [2], 14: [3], 15: [4], 17: [7], 18: [3], 20: [3], 22: [3], 23: [2],
    24: [1], 26: [L], 27: [3], 28: [0], 29: [2], 31: [1], 32: [0, L], 34: [0, 3], 36: [2], 37: [4], 38: [4], 39: [4], 40: [0, 3], 41: [1], 44: [2],
    46: [2], 47: [1], 48: [1], 49: [2, 4], 50: [0], 52: [0, 4], 54: [2], 55: [2], 56: [L], 57: [2], 58: [3], 60: [4], 63: [3], 64: [1], 65: [0],
    66: [2], 67: [6], 68: [4], 69: [4, L], 70: [4, 5], 71: [1], 72: [2], 74: [0, 2], 75: [0], 77: [1], 79: [0, 3], 80: [0], 81: [2], 82: [2], 83: [2],
    86: [1], 87: [3], 90: [2], 92: [2], 93: [2], 94: [1], 96: [2], 97: [0], 98: [L], 99: [1], 100: [0], 101: [0], 102: [0], 103: [2], 104: [1, 2],
    105: [1], 107: [3], 108: [L], 109: [1], 111: [0], 112: [2], 113: [1], 115: [2], 116: [1], 117: [0, 2], 121: [0], 122: [2], 123: [L], 124: [0],
    125: [3], 126: [2], 127: [2], 130: [3], 131: [3], 132: [1], 133: [1], 134: [1], 135: [7], 136: [1], 137: [5], 138: [2], 139: [1], 140: [1],
    141: [1], 142: [3], 144: [4], 145: [1], 146: [1], 147: [4], 149: [1], 150: [0], 151: [0], 152: [4], 154: [1], 156: [2], 157: [2], 158: [0, L],
    162: [2], 163: [L], 164: [1], 165: [3], 167: [1], 169: [3], 170: [1], 171: [1], 172: [1], 173: [2], 176: [3], 177: [1], 178: [3], 179: [3],
    182: [1, 4], 183: [4], 186: [3], 189: [0], 190: [0], 191: [2], 193: [2], 196: [2], 197: [2], 198: [1], 202: [2], 204: [2], 206: [3, 5], 207: [4],
    209: [1], 211: [1, 3], 214: [2], 215: [0], 216: [9], 217: [3], 218: [1], 220: [3], 221: [1], 222: [1], 223: [1], 224: [7, 9], 228: [4],
}
# Buttons that take the offer or make a claim for the user, counted as traps if clicked.
TRAPS = {26: [0], 32: [1], 74: [1], 140: [0], 158: [1], 163: [0], 221: [0]}


def main():
    items = [x for x in json.loads((ROOT / "big/test_items.json").read_text())]
    assert set(LABELS) | NOT_POPUPS | DROPPED == {x["id"] for x in items} and not set(LABELS) & (NOT_POPUPS | DROPPED) and not NOT_POPUPS & DROPPED
    rows = []
    for x in items:
        if x["id"] in DROPPED:
            continue
        lang = "vi" if re.search("[ăâđêôơưàáảãạèéẻẽẹìíỉĩịòóỏõọùúủũụỳýỷỹỵ]", x["text"], re.I) else "other"
        cookie = re.search("cookie|cooki|kakor|eväste|ciastecz", x["text"], re.I) is not None
        common = {"set": "fresh", "lang": lang, "url": x["url"], "text": x["text"], "buttons": x["buttons"]}
        if x["id"] in NOT_POPUPS:
            rows.append({**common, "split": "fresh_np", "kind": "not_popup", "acceptable": [LEAVE], "traps": []})
        else:
            acceptable = [LEAVE if a == L else x["buttons"][a] for a in LABELS[x["id"]]]
            traps = [x["buttons"][a] for a in TRAPS.get(x["id"], [])]
            rows.append({**common, "split": "fresh", "kind": "cookie" if cookie else "other", "acceptable": acceptable, "traps": traps})
    path = ROOT / "testset.json"
    kept = [x for x in json.loads(path.read_text()) if x["set"] != "fresh"]
    path.write_text(json.dumps(kept + rows, ensure_ascii=False, indent=1))
    fresh = [x for x in rows if x["split"] == "fresh"]
    print(len(fresh), "pop-ups,", sum(x["lang"] == "vi" for x in fresh), "vi,", sum(x["kind"] == "cookie" for x in fresh), "cookie;", len(rows) - len(fresh), "not pop-ups")


if __name__ == "__main__":
    main()
