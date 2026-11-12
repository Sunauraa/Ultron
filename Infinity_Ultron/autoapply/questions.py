"""Questions answers.md doesn't answer yet. Ultron saves them when a job is logged needs_info; ask.py puts them to
the user and writes the answers into answers.md (which re-queues those jobs on the next run)."""

from __future__ import annotations

import fcntl
import json
import re
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

FILE = "questions.json"


def label_key(label: str) -> str:
    return re.sub(r"[\s*✱]+", " ", label).strip().casefold()


@contextmanager
def locked(folder: Path):
    with (folder / f".{FILE}.lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        path = folder / FILE
        items = json.loads(path.read_text()) if path.exists() else []
        yield items
        path.write_text(json.dumps(items, indent=1, ensure_ascii=False) + "\n")


def load(folder: Path) -> list[dict]:
    path = folder / FILE
    return json.loads(path.read_text()) if path.exists() else []


def add(folder: Path, fields: list[dict], job: dict) -> int:
    """Save each field's question once, noting which jobs asked it. Returns how many fields were saved."""
    with locked(folder) as items:
        by_key = {label_key(q["question"]): q for q in items}
        for f in fields:
            question = re.sub(r"[\s*✱]+$", "", f["label"]).strip()
            entry = by_key.get(label_key(question))
            if entry is None:
                entry = {"question": question, "kind": f["kind"], "options": f.get("options") or [], "jobs": [],
                         "saved": datetime.now(timezone.utc).isoformat(timespec="seconds")}
                items.append(entry)
                by_key[label_key(question)] = entry
            if job.get("url") not in [j["url"] for j in entry["jobs"]]:
                entry["jobs"].append({k: job.get(k, "") for k in ("url", "company", "title")})
    return len(fields)


def drop(folder: Path, question: str) -> None:
    with locked(folder) as items:
        items[:] = [q for q in items if label_key(q["question"]) != label_key(question)]


def answers_line(question: str, answer: str) -> str:
    """One answers.md line. A label can't hold ':' or '#' (they end it), and a long question keeps its last sentence."""
    label = re.sub(r"\s+", " ", question.replace(":", " -").replace("#", "No.")).strip()
    if len(label) > 300:
        sentences = re.findall(r"[^.?!]+[?]", label) or [label[-300:]]
        label = sentences[-1].strip()[:300]
    return f"{label}: {' '.join(answer.split())}"


def append_answer(answers: Path, question: str, answer: str) -> str:
    line = answers_line(question, answer)
    text = answers.read_text() if answers.exists() else ""
    header = "# Added when a form asked (ask.py or add_answer)"
    if header not in text:
        text = text.rstrip("\n") + f"\n\n{header}\n"
    answers.write_text(text.rstrip("\n") + f"\n{line}\n")
    return line
