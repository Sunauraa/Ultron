"""Hand labels for the final test (sites not in any training or tuning data). Run: labels_final.py

Written before any model was scored on these. Same conventions as labels_big.py. Kept out of
testset.json on purpose, so tuning scripts can't reach it. Writes final_test.json.
DROPPED: 40 is a country form I can't judge, 47 and 224 lack a clear action in the capture, 114 may
come from my capture's own blocking, 211 is an unlabelled button on no real pop-up.
"""

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
LEAVE = "leave alone"
L = "L"
NOT_POPUPS = {16, 21, 24, 33, 36, 38, 41, 69, 76, 82, 83, 96, 98, 144, 146, 159, 163, 177, 189, 217, 218, 220, 222, 244, 245, 249, 250, 252, 263,
              265, 267, 280, 286, 291, 294, 312, 314}
DROPPED = {40, 47, 114, 211, 224}
LABELS = {
    0: [4], 1: [2], 2: [2], 3: [0], 4: [3], 5: [3], 6: [2], 7: [1], 8: [1, 3], 9: [8], 10: [2], 11: [0], 12: [1], 13: [0], 14: [0], 15: [1], 17: [1], 18: [3],
    19: [3], 20: [5], 22: [3], 23: [1], 25: [4], 26: [0], 27: [2], 28: [1], 29: [1], 30: [0], 31: [4], 32: [2], 34: [2], 35: [0], 37: [2], 39: [L], 42: [2],
    43: [0], 44: [3], 45: [1], 46: [2], 48: [2], 49: [0], 50: [2], 51: [2], 52: [1], 53: [0, L], 54: [6], 55: [1], 56: [1], 57: [2], 58: [1], 59: [0], 60: [3],
    61: [0], 62: [L], 63: [1], 64: [L], 65: [0, 3], 66: [4], 67: [4], 68: [0], 70: [2], 71: [1], 72: [6], 73: [0, 3], 74: [2], 75: [0], 77: [2], 78: [1], 79: [4],
    80: [0], 81: [0], 84: [0], 85: [0], 86: [5], 87: [1], 88: [0, 2], 89: [0], 90: [0], 91: [0], 92: [2], 93: [0], 94: [0, 3], 95: [4], 97: [0], 99: [3], 100: [1],
    101: [1], 102: [2], 103: [1, 3], 104: [3, 6], 105: [1], 106: [1], 107: [4], 108: [3], 109: [3], 110: [2], 111: [3], 112: [L], 113: [2], 115: [2], 116: [2],
    117: [1], 118: [3], 119: [2], 120: [2], 121: [2], 122: [1, 3], 123: [2], 124: [5], 125: [8], 126: [2], 127: [2], 128: [0], 129: [0], 130: [2], 131: [7],
    132: [0], 133: [1], 134: [3], 135: [1], 136: [4], 137: [0], 138: [0], 139: [5], 140: [1], 141: [4], 142: [3], 143: [4], 145: [0], 147: [0], 148: [2], 149: [3],
    150: [1], 151: [4], 152: [1, 3], 153: [4], 154: [0, 3], 155: [0, 2], 156: [5], 157: [0], 158: [1], 160: [2], 161: [0], 162: [4], 164: [4], 165: [0], 166: [4],
    167: [2], 168: [0], 169: [L], 170: [1], 171: [3], 172: [0], 173: [0, 3], 174: [2], 175: [0], 176: [L], 178: [0], 179: [L], 180: [1], 181: [3], 182: [0, L],
    183: [1], 184: [2], 185: [2], 186: [0], 187: [1], 188: [4, 5, 6], 190: [1], 191: [9], 192: [1], 193: [1], 194: [1], 195: [1], 196: [1], 197: [1], 198: [0, 2],
    199: [2], 200: [1], 201: [1], 202: [0], 203: [2], 204: [1], 205: [2], 206: [2], 207: [7], 208: [0], 209: [1], 210: [2], 212: [1], 213: [1], 214: [1], 215: [0],
    216: [2], 219: [5], 221: [1], 223: [2], 225: [4], 226: [2], 227: [1], 228: [3], 229: [2], 230: [1], 231: [2, 4], 232: [1], 233: [3], 234: [2], 235: [0, 2],
    236: [1], 237: [0], 238: [2], 239: [1], 240: [0], 241: [0, 3], 242: [1], 243: [0], 246: [0], 247: [3], 248: [2, 4], 251: [3, 5], 253: [1], 254: [1], 255: [1],
    256: [4, 5], 257: [L], 258: [1], 259: [1], 260: [0, 4], 261: [1], 262: [0], 264: [2, 4], 266: [5], 268: [2, 4], 269: [1, 3], 270: [0, 5], 271: [3], 272: [1],
    273: [1], 274: [0, 3], 275: [L], 276: [2], 277: [6], 278: [2, 4], 279: [1], 281: [0, 3], 282: [1], 283: [2], 284: [1, 3], 285: [L], 287: [2], 288: [2], 289: [0],
    290: [2, 4], 292: [1], 293: [0], 295: [1, 2], 296: [1], 297: [3], 298: [1], 299: [0], 300: [4], 301: [2], 302: [1], 303: [1, 3], 304: [2], 305: [0, 4], 306: [3],
    307: [1], 308: [0, 3], 309: [2, 4], 310: [L], 311: [2], 313: [1], 315: [1], 316: [2], 317: [2], 318: [2], 319: [1, 2], 320: [2], 321: [2], 322: [L],
}
# Buttons that take an offer or make a claim for the user, counted as traps if clicked.
TRAPS = {18: [0], 53: [], 62: [0], 67: [0], 112: [0, 1], 125: [3], 133: [4], 145: [6], 157: [6], 169: [1], 176: [0], 179: [1], 182: [1], 196: [4], 203: [1],
         242: [0], 257: [0], 275: [1], 310: [0]}


def main():
    items = json.loads((ROOT / "big/final_items.json").read_text())
    ids = {x["id"] for x in items}
    missing = ids - set(LABELS) - NOT_POPUPS - DROPPED
    assert not missing and not set(LABELS) & (NOT_POPUPS | DROPPED) and not NOT_POPUPS & DROPPED, sorted(missing)
    rows = []
    for x in items:
        if x["id"] in DROPPED:
            continue
        cookie = re.search("cookie|cooki|kakor|eväste|ciastecz|süti|kaka", x["text"], re.I) is not None
        common = {"set": "final", "url": x["url"], "text": x["text"], "buttons": x["buttons"]}
        if x["id"] in NOT_POPUPS:
            rows.append({**common, "split": "final_np", "kind": "not_popup", "acceptable": [LEAVE], "traps": []})
        else:
            acceptable = [LEAVE if a == L else x["buttons"][a] for a in LABELS[x["id"]]]
            rows.append({**common, "split": "final", "kind": "cookie" if cookie else "other", "acceptable": acceptable, "traps": [x["buttons"][a] for a in TRAPS.get(x["id"], [])]})
    (ROOT / "final_test.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1))
    pop = [x for x in rows if x["split"] == "final"]
    print(len(pop), "pop-ups,", sum(x["kind"] == "cookie" for x in pop), "cookie,", sum(bool(x["traps"]) for x in pop), "with traps;", len(rows) - len(pop), "not pop-ups")


if __name__ == "__main__":
    main()
