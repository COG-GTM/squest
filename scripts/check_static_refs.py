import re
import os
import sys
import contextlib
import io
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "Squest.settings")

import django

with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
    django.setup()

from django.contrib.staticfiles import finders


STATIC_REF = re.compile(r"{%\s*static\s+['\"]([^'\"]+)")


def main():
    refs = {}
    for template in (ROOT / "templates").rglob("*.html"):
        for line_number, line in enumerate(template.read_text(errors="ignore").splitlines(), 1):
            for path in STATIC_REF.findall(line):
                refs.setdefault(path, []).append(f"{template.relative_to(ROOT)}:{line_number}")

    missing = []
    for path, locations in sorted(refs.items()):
        resolved = finders.find(path)
        if path.startswith("/") or resolved is None:
            missing.append((path, locations))

    print(f"Checked {len(refs)} distinct static paths.")
    if missing:
        print("Missing static paths:")
        for path, locations in missing:
            print(f"- {path}: {', '.join(locations)}")
    else:
        print("No missing static paths.")

    return 1 if missing else 0


if __name__ == "__main__":
    raise SystemExit(main())
