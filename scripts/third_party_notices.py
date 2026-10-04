"""Collect installed dependency license texts for the redistributable bundle."""
from importlib.metadata import distributions
from pathlib import Path
import sys

root = Path(__file__).resolve().parents[1]
parts = ["Agentboard dependency notices\n\nPython build environment licenses follow.\n"]
interpreter = Path(sys.base_prefix)
parts.extend(["\n=== CPython ===\n", (interpreter / "LICENSE.txt").read_text(encoding="utf-8")])
for path in (interpreter / "tcl").glob("*/license.terms"):
    parts.extend([f"\n=== {path.parent.name} ===\n", path.read_text(encoding="utf-8")])
for package in sorted(distributions(), key=lambda item: item.metadata.get("Name", "").lower()):
    parts.append(f"\n=== {package.metadata['Name']} {package.version} ===\n")
    found = False
    for entry in package.files or []:
        if ".dist-info" not in str(entry) or not (
            "licenses" in entry.parts or entry.name.lower().startswith(("license", "copying", "notice"))
        ):
            continue
        path = Path(package.locate_file(entry))
        if path.is_file():
            parts.append(path.read_text(encoding="utf-8", errors="replace"))
            found = True
    if not found:
        parts.append(f"License metadata: {package.metadata.get('License-Expression') or package.metadata.get('License') or 'See upstream package'}\n")
for name in ("react", "react-dom", "lucide-react", "scheduler"):
    folder = root / "node_modules" / name
    for path in folder.glob("*LICENSE*"):
        if path.is_file():
            parts.extend([f"\n=== npm {name} ===\n", path.read_text(encoding="utf-8")])
output = root / "build" / "desktop" / "THIRD_PARTY_NOTICES.txt"
output.parent.mkdir(parents=True, exist_ok=True)
output.write_text("\n".join(parts), encoding="utf-8")
