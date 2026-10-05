"""Export the API's OpenAPI schema for the frontend type generator.

Usage
─────
    python scripts/export_openapi.py            # rewrite frontend/src/api/openapi.json
    python scripts/export_openapi.py --check    # fail if the committed file is stale

The output feeds ``frontend/scripts/gen-api-types.mjs`` (``npm run gen:api``),
which turns it into ``frontend/src/api/schema.gen.ts``. CI runs both with
``--check``, so a backend schema change that is not re-exported fails the build.

No database or network access is needed: building the schema only imports the
app, whose lifespan never runs here.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "frontend" / "src" / "api" / "openapi.json"


def render_schema() -> str:
    # Importing the app builds Settings(); a dummy key keeps a missing
    # AUTH_SECRET from logging a warning. The schema does not depend on it.
    os.environ.setdefault("AUTH_SECRET", "openapi-export-not-a-real-secret")
    from finlytics.app import app

    spec = app.openapi()
    return json.dumps(spec, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--check",
        action="store_true",
        help="exit 1 instead of writing when the committed schema is out of date",
    )
    args = parser.parse_args()

    rendered = render_schema()
    relative = OUTPUT.relative_to(ROOT).as_posix()

    if args.check:
        current = OUTPUT.read_text(encoding="utf-8") if OUTPUT.exists() else None
        if current != rendered:
            print(
                f"{relative} is out of date. Run `python scripts/export_openapi.py`, "
                "then `npm run gen:api` in frontend/, and commit the result.",
                file=sys.stderr,
            )
            return 1
        print(f"{relative} is up to date.")
        return 0

    OUTPUT.write_text(rendered, encoding="utf-8", newline="\n")
    print(f"Wrote {relative}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
