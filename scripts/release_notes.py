"""The "What's new" section of a GitHub release: the notes added since the previous release.

The notes are the interface's own (``frontend/src/whatsNew/notes/``, see AGENTS.md). The
release workflow puts this section before GitHub's generated list of pull requests::

    python scripts/release_notes.py [<previous release tag>]

It prints Markdown in English, or nothing when no note was added; without a tag (the first
release) every note counts. Standard library only: the workflow runs it with the runner's Python."""

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NOTES = "frontend/src/whatsNew/notes"
SECTIONS = (("new", "New"), ("improved", "Improved"), ("fixed", "Fixed"))


def added_notes(root: Path, since: str) -> list[Path]:
    """Note files added after the ``since`` commit or tag (every note when it is empty)."""
    if not since:
        return sorted((root / NOTES).glob("*.json"))
    names = subprocess.run(
        ["git", "diff", "--name-only", "--diff-filter=A", since, "HEAD", "--", NOTES],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.split()
    return sorted(root / name for name in names if name.endswith(".json"))


def markdown(paths: list[Path]) -> str:
    """New things first, then improvements and fixes, the newest first in each."""
    notes = {path.stem: json.loads(path.read_text(encoding="utf-8")) for path in paths}
    lines: list[str] = []
    for kind, heading in SECTIONS:
        ids = sorted((key for key, note in notes.items() if note["kind"] == kind), reverse=True)
        if ids:
            lines += ["", f"### {heading}", ""]
        for key in ids:
            text = notes[key]["en"]
            lines.append(f"- **{text['title']}**: {text['body']}")
    return "\n".join(["## What's new", *lines, "", ""]) if lines else ""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("since", nargs="?", default="", help="tag of the previous release")
    args = parser.parse_args()
    sys.stdout.buffer.write(markdown(added_notes(ROOT, args.since)).encode("utf-8"))


if __name__ == "__main__":
    main()
