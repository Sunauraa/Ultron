"""Answer the questions forms asked that answers.md doesn't answer yet. Each answer is added to answers.md, so
the jobs that stopped on it (logged needs_info) are queued again on the next run, and later forms use it too.

Usage: python ask.py [DIR]   (DIR holds answers.md and questions.json; default: this folder)
At each question: type the answer (or an option's number), press Enter to leave it for later, or type - to
drop it (it will be saved again if another form asks it).

For Claude Code asking you in the chat instead (no keyboard prompt):
  python ask.py --list              the questions waiting, numbered, with the form's options
  python ask.py --answer N "TEXT"   save your answer to question N (TEXT exactly as you gave it, or an option's number)
"""

import sys
import tomllib
from pathlib import Path

import questions


def jobs_of(q: dict) -> str:
    return ", ".join(f"{j['company']} ({j['title']})" for j in q["jobs"][:3]) + (f" and {len(q['jobs']) - 3} more" if len(q["jobs"]) > 3 else "")


def answers_file(folder: Path) -> Path:
    config = tomllib.loads((folder / "config.toml").read_text()).get("apply", {}) if (folder / "config.toml").exists() else {}
    return folder / config.get("answers", "answers.md")


def list_questions(folder: Path) -> None:
    pending = questions.load(folder)
    print(f"{len(pending)} question(s) waiting." if pending else "No questions waiting.")
    for number, q in enumerate(pending, 1):
        print(f"[{number}] {q['question']}\n    asked by: {jobs_of(q)}")
        for k, option in enumerate(q.get("options") or [], 1):
            print(f"    {k}. {option}")


def answer(folder: Path, number: int, reply: str) -> None:
    pending = questions.load(folder)
    if not 1 <= number <= len(pending):
        sys.exit(f"No question {number}: run python ask.py --list")
    q, options = pending[number - 1], pending[number - 1].get("options") or []
    if reply.strip().isdigit() and 1 <= int(reply) <= len(options):
        reply = options[int(reply) - 1]
    if not reply.strip():
        sys.exit("Empty answer: nothing saved")
    print("saved:", questions.append_answer(answers_file(folder), q["question"], reply))
    questions.drop(folder, q["question"])


def main(folder: Path) -> None:
    answers = answers_file(folder)
    pending = questions.load(folder)
    if not pending:
        print("No questions waiting.")
        return
    print(f"{len(pending)} question(s) waiting. Enter: later. -: drop.\n")
    added = 0
    for number, q in enumerate(pending, 1):
        print(f"[{number}/{len(pending)}] {q['question']}\n    asked by: {jobs_of(q)}")
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
    here = Path(__file__).parent.resolve()
    if sys.argv[1:2] == ["--list"]:
        list_questions(here)
    elif sys.argv[1:2] == ["--answer"] and len(sys.argv) == 4 and sys.argv[2].isdigit():
        answer(here, int(sys.argv[2]), sys.argv[3])
    else:
        main(Path(sys.argv[1] if len(sys.argv) > 1 else here).resolve())
