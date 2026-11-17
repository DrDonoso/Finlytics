"""scripts/release_notes.py: the "What's new" section of each GitHub release, from the notes added
since the previous one."""

import importlib.util
import json
import subprocess
from pathlib import Path
from types import ModuleType
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "release_notes.py"


def load_script() -> ModuleType:
    spec = importlib.util.spec_from_file_location("release_notes", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


release_notes = load_script()


def note(kind: str, title: str) -> dict[str, Any]:
    text = {"title": title, "body": f"About {title.lower()}."}
    return {"kind": kind, "es": text, "en": text}


def write(folder: Path, note_id: str, content: dict[str, Any]) -> Path:
    path = folder / f"{note_id}.json"
    path.write_text(json.dumps(content), encoding="utf-8")
    return path


def git(root: Path, *args: str) -> None:
    command = ["git", "-c", "user.name=Test", "-c", "user.email=test@example.com", *args]
    subprocess.run(command, cwd=root, check=True, capture_output=True)


def test_new_things_first_then_improvements_and_fixes(tmp_path: Path) -> None:
    paths = [
        write(tmp_path, "2026-12-01-zoom", note("improved", "Zoom")),
        write(tmp_path, "2026-12-02-photos", note("fixed", "Photos")),
        write(tmp_path, "2026-12-03-backups", note("new", "Backups")),
        write(tmp_path, "2026-12-04-albums", note("new", "Albums")),
    ]
    assert release_notes.markdown(paths) == (
        "## What's new\n\n"
        "### New\n\n"
        "- **Albums**: About albums.\n"
        "- **Backups**: About backups.\n\n"
        "### Improved\n\n"
        "- **Zoom**: About zoom.\n\n"
        "### Fixed\n\n"
        "- **Photos**: About photos.\n\n"
    )
    assert release_notes.markdown([]) == ""


def test_only_the_notes_added_since_the_previous_release(tmp_path: Path) -> None:
    folder = tmp_path / release_notes.NOTES
    folder.mkdir(parents=True)
    git(tmp_path, "init", "--quiet")
    write(folder, "2026-11-17-novedades", note("new", "What's new"))
    git(tmp_path, "add", ".")
    git(tmp_path, "commit", "--quiet", "-m", "First release")
    git(tmp_path, "tag", "20261117")
    # Changing a published note does not announce it again.
    write(folder, "2026-11-17-novedades", note("new", "What's new, reworded"))
    write(folder, "2026-12-01-zoom", note("improved", "Zoom"))
    git(tmp_path, "add", ".")
    git(tmp_path, "commit", "--quiet", "-m", "Second release")

    assert release_notes.added_notes(tmp_path, "20261117") == [folder / "2026-12-01-zoom.json"]
    assert release_notes.added_notes(tmp_path, "") == [
        folder / "2026-11-17-novedades.json",
        folder / "2026-12-01-zoom.json",
    ]


def test_every_note_of_the_app_renders() -> None:
    paths = release_notes.added_notes(ROOT, "")
    assert paths
    text = release_notes.markdown(paths)
    assert text.startswith("## What's new\n")
    assert "- **Now we tell you what's new**: When Finlytics gets something new" in text
