"""Join the two recordings of record_demo.py into one side-by-side video, with each agent's tool calls as it made them.

The page images are the screenshots taken during the runs; the tool calls and their times come from Claude Code's
own session log (~/.claude/projects/*/SESSION.jsonl). Both sides play on one clock, sped up by the factor shown.
Usage: python compose_demo.py OUT.mp4
"""

import json
import re
import sys
from datetime import datetime
from pathlib import Path

import imageio_ffmpeg
from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
DEMO = HERE.parent.parent.parent / "tmp" / "demo"
W, H, FPS = 1920, 1080, 12
COL, GAP, TOP, HEAD, SHOT_H = 940, 13, 96, 52, 661
BG, PANEL, INK, MUTED, LINE = (233, 237, 241), (247, 249, 251), (20, 32, 43), (84, 99, 111), (198, 208, 217)
ACCENT, GO, STOP, HOLD = (29, 78, 216), (15, 122, 79), (180, 35, 24), (154, 91, 0)
SANS, BOLD, MONO = (f"/usr/share/fonts/truetype/dejavu/{n}.ttf" for n in ("DejaVuSans", "DejaVuSans-Bold", "DejaVuSansMono"))
NAMES = {"ultron": "Claude Code + Ultron", "playwright": "Claude Code + Playwright MCP (baseline)"}


def font(path: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(path, size)


def wall(stamp: str) -> float:
    return datetime.fromisoformat(stamp.replace("Z", "+00:00")).timestamp()


def summary(name: str, args: dict) -> str:
    """One short line per tool call."""
    if name == "ToolSearch":
        return "load the tools"
    name = name.replace("mcp__ultron__", "").replace("mcp__playwright__browser_", "").replace("mcp__playwright__", "")
    if name == "fill" or name == "fill_form":
        return f"{name}: {len(args.get('entries') or args.get('fields') or [])} fields"
    if name in ("open_job", "navigate"):
        return f"{name}: {re.sub(r'^https?://', '', args.get('url', ''))[:40]}"
    if name == "log":
        return f"log: {args.get('status', '')}"
    if name == "submit":
        return "submit (reviewed)" if args.get("reviewed") else "submit"
    target = args.get("element") or args.get("text") or args.get("value") or ""
    return f"{name}: {str(target)[:44]}" if target else name


def tool_calls(session: str) -> list[tuple[float, str]]:
    path = next(Path.home().glob(f".claude/projects/*/{session}.jsonl"))
    calls = []
    for line in path.read_text().splitlines():
        entry = json.loads(line)
        if entry.get("type") != "assistant":
            continue
        for block in entry["message"].get("content", []):
            if isinstance(block, dict) and block.get("type") == "tool_use":
                calls.append((wall(entry["timestamp"]), summary(block["name"], block.get("input") or {})))
    return calls


def load(arm: str) -> dict:
    record = json.loads((DEMO / arm / "result.json").read_text())
    start = record.get("start_wall")
    if start is None:  # recorded before start_wall was saved: run.sh prints "run start" a moment after launch
        start = wall(re.search(r"(\S+) run start", record["run_output"]).group(1))
    frames = sorted((float(p.stem.split("_")[1]), p) for p in (DEMO / arm / "frames").glob("*.jpg"))
    calls = [(t - start, text) for t, text in tool_calls(record["claude"]["session_id"])]
    return {"arm": arm, "record": record, "frames": frames, "calls": calls, "end": record["agent_seconds"]}


def outcome(record: dict) -> tuple[str, tuple]:
    s = record["score"]
    if not s["submitted"]:
        return "Nothing sent", STOP
    bad = len(s["wrong"]) + len(s["missing"]) + len(s["extra"])
    return ("Every scored field right", GO) if not bad else (f"{bad} field(s) wrong, missing or extra", STOP)


def column(canvas: Image.Image, x: int, side: dict, t: float, speed: int) -> None:
    draw = ImageDraw.Draw(canvas)
    draw.rectangle([x, TOP, x + COL, H - 52], fill=PANEL, outline=LINE)
    draw.text((x + 16, TOP + 12), NAMES[side["arm"]], font=font(BOLD, 26), fill=ACCENT if side["arm"] == "ultron" else INK)
    shown = [p for s, p in side["frames"] if s <= min(t, side["end"])]  # the agent's page, not the press of Submit after it
    y = TOP + HEAD
    if shown:
        canvas.paste(Image.open(shown[-1]).convert("RGB").resize((COL - 2, SHOT_H)), (x + 1, y))
    else:
        draw.rectangle([x + 1, y, x + COL - 1, y + SHOT_H], fill=BG)
        draw.text((x + 24, y + 24), "Claude Code is starting…", font=font(SANS, 22), fill=MUTED)
    y += SHOT_H + 10
    done = t >= side["end"]
    calls = [c for c in side["calls"] if c[0] <= t]
    clock = min(t, side["end"])
    status = f"{int(clock // 60)}:{int(clock % 60):02d}   ·   {len(calls)} tool calls"
    draw.text((x + 16, y), status, font=font(MONO, 22), fill=INK)
    if done:
        claude = side["record"]["claude"]
        draw.rectangle([x + 1, y - 10 - 58, x + COL - 1, y - 10], fill=GO)
        draw.text((x + 18, y - 10 - 46), f"Done: {claude.get('num_turns', '?')} turns, ${claude.get('total_cost_usd', 0):.2f}. "
                  "The form waits for you to check and submit.", font=font(BOLD, 21), fill=(255, 255, 255))
    for i, (_, text) in enumerate(calls[-6:]):
        draw.text((x + 16, y + 36 + 26 * i), "› " + text, font=font(MONO, 18), fill=INK if i == len(calls[-6:]) - 1 else MUTED)


def card(lines: list[tuple[str, int, tuple, str]]) -> Image.Image:
    canvas = Image.new("RGB", (W, H), BG)
    draw = ImageDraw.Draw(canvas)
    y = 300
    for text, size, colour, face in lines:
        draw.text((140, y), text, font=font(face, size), fill=colour)
        y += int(size * 1.6)
    return canvas


def table(sides: list[dict]) -> Image.Image:
    canvas = Image.new("RGB", (W, H), BG)
    draw = ImageDraw.Draw(canvas)
    draw.text((140, 150), "Same job, same applicant, same Claude Code", font=font(BOLD, 44), fill=INK)
    rows = [("", *[NAMES[s["arm"]] for s in sides])]
    for s in sides:
        c, sc = s["record"]["claude"], s["record"]["score"]
        u = c.get("usage", {})
        s["cells"] = [f"{int(s['end'] // 60)} min {int(s['end'] % 60)} s", str(c.get("num_turns", "?")),
                      f"{(u.get('input_tokens', 0) + u.get('cache_read_input_tokens', 0) + u.get('cache_creation_input_tokens', 0)) / 1000:.0f}k",
                      f"${c.get('total_cost_usd', 0):.2f}", str(len(sc["wrong"])), str(len(sc["missing"])), str(len(sc["extra"])),
                      outcome(s["record"])[0]]
    labels = ["Time", "Turns", "Input tokens (mostly cached)", "Cost", "Wrong fields", "Required fields left empty", "Fields that should be empty",
              "The application"]
    for i, label in enumerate(labels):
        rows.append((label, *[s["cells"][i] for s in sides]))
    y = 260
    for r, row in enumerate(rows):
        face = BOLD if r == 0 else SANS
        draw.text((140, y), row[0], font=font(SANS, 28), fill=MUTED)
        for k, cell in enumerate(row[1:]):
            draw.text((640 + 600 * k, y), cell, font=font(face if r else BOLD, 28 if r else 26), fill=INK)
        y += 58
        draw.line([140, y - 12, 1780, y - 12], fill=LINE)
    draw.text((140, y + 20), "Scored on the request the page sent when Submit was pressed (offline; nothing reached the site).",
              font=font(SANS, 22), fill=MUTED)
    return canvas


def main(out: Path) -> None:
    sides = [load("ultron"), load("playwright")]
    finish = max(max(s["end"] for s in sides), max(s["frames"][-1][0] for s in sides))
    speed = max(4, -(-int(finish) // 70))
    writer = imageio_ffmpeg.write_frames(str(out), (W, H), fps=FPS, codec="libx264", quality=8, macro_block_size=1,
                                         pix_fmt_out="yuv420p", output_params=["-movflags", "+faststart"])
    writer.send(None)

    def hold(image: Image.Image, seconds: float) -> None:
        for _ in range(int(seconds * FPS)):
            writer.send(image.tobytes())

    hold(card([("Ultron", 72, INK, BOLD),
               ("Until Landing That Role, Overnight, Nonstop.", 34, ACCENT, BOLD),
               ("Claude Code applies to a job for you.", 40, INK, SANS),
               ("Left: through Ultron.  Right: through Playwright MCP, the usual browser tools.", 30, MUTED, SANS),
               ("A recorded Figma job page, served offline. A fictional applicant. Nothing reached Figma.", 26, MUTED, SANS)]), 4.5)
    for n in range(int((finish + 3) * FPS / speed)):
        t = n * speed / FPS
        canvas = Image.new("RGB", (W, H), BG)
        draw = ImageDraw.Draw(canvas)
        draw.text((24, 22), "Ultron", font=font(BOLD, 34), fill=INK)
        draw.text((170, 32), "approval mode: the agent fills, you press Submit", font=font(SANS, 22), fill=MUTED)
        draw.text((W - 190, 28), f"{speed}× speed", font=font(BOLD, 28), fill=ACCENT)
        for i, side in enumerate(sides):
            column(canvas, 12 + i * (COL + GAP + 12), side, t, speed)
        draw.text((24, H - 40), "Real Claude Code, run by run.sh with the same flags in both. Page served from its recording; "
                  "after the agent stops, Submit is pressed as you would.", font=font(SANS, 19), fill=MUTED)
        writer.send(canvas.tobytes())
    hold(table(sides), 8)
    writer.close()
    print(out, speed)


if __name__ == "__main__":
    main(Path(sys.argv[1]))
