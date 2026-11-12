"""Answer the questions forms asked that answers.md doesn't answer yet. Each answer is added to answers.md, so
the jobs that stopped on it (logged needs_info) are queued again on the next run, and later forms use it too.

Usage: python ask.py [DIR]   (DIR holds answers.md and questions.json; default: this folder)
At each question: type the answer (or an option's number), press Enter to leave it for later, or type - to
drop it (it will be saved again if another form asks it).
"""

import sys
import tomllib
from pathlib import Path

import questions


def main(folder: Path) -> None:
    config = tomllib.loads((folder / "config.toml").read_text()).get("apply", {}) if (folder / "config.toml").exists() else {}
    answers = folder / config.get("answers", "answers.md")
    pending = questions.load(folder)
    if not pending:
        print("No questions waiting.")
        return
    print(f"{len(pending)} question(s) waiting. Enter: later. -: drop.\n")
    added = 0
    for number, q in enumerate(pending, 1):
        jobs = ", ".join(f"{j['company']} ({j['title']})" for j in q["jobs"][:3]) + (f" and {len(q['jobs']) - 3} more" if len(q["jobs"]) > 3 else "")
        print(f"[{number}/{len(pending)}] {q['question']}\n    asked by: {jobs}")
        options = q.get("options") or []
        for k, option in enumerate(options, 1):
            print(f"    {k}. {option}")
        try:
            reply = input("> ").strip()
        except EOFError:
            break
        if not reply:
            continue
        if reply == "-":
            questions.drop(folder, q["question"])
            continue
        if reply.isdigit() and 1 <= int(reply) <= len(options):
            reply = options[int(reply) - 1]
        print("    saved:", questions.append_answer(answers, q["question"], reply), "\n")
        questions.drop(folder, q["question"])
        added += 1
    print(f"Added {added} answer(s) to {answers.name}." + (" Their jobs are retried on the next run." if added else ""))


if __name__ == "__main__":
    main(Path(sys.argv[1] if len(sys.argv) > 1 else Path(__file__).parent).resolve())
