"""Check Python syntax, source-file length and required deployment files."""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXCLUDED_DIRS = {".venv", "venv", "__pycache__", "tmp", ".pytest_cache"}
REQUIRED_FILES = (
    "passenger_wsgi.py",
    "requirements.txt",
    ".env.example",
    "app/main.py",
    "app/database.py",
    "scripts/check_database.py",
    "scripts/create_admin.py",
)


def main() -> int:
    failed = False

    for relative in REQUIRED_FILES:
        if not (ROOT / relative).is_file():
            print(f"MANJKA DATOTEKA: {relative}")
            failed = True

    for path in sorted(ROOT.rglob("*.py")):
        if any(part in EXCLUDED_DIRS for part in path.parts):
            continue
        try:
            source = path.read_text(encoding="utf-8")
            ast.parse(source, filename=str(path))
        except (OSError, UnicodeError, SyntaxError) as exc:
            failed = True
            if isinstance(exc, SyntaxError):
                print(f"NAPAKA SINTAKSE {path.relative_to(ROOT)}:{exc.lineno}: {exc.msg}")
            else:
                print(f"NAPAKA PRI BRANJU {path.relative_to(ROOT)}: {exc}")
            continue

        line_count = len(source.splitlines())
        if line_count > 700:
            failed = True
            print(f"PREVEČ VRSTIC {path.relative_to(ROOT)}: {line_count} (največ 700)")
        else:
            print(f"OK {path.relative_to(ROOT)}: sintaksa, {line_count} vrstic")

    if failed:
        print("PREVERJANJE NI USPELO.")
        return 1

    print("USPEH: struktura, Python sintaksa in omejitev 700 vrstic so v redu.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
