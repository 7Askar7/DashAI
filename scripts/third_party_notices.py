"""Collect installed dependency license texts for the redistributable bundle."""
from importlib.metadata import distributions
from pathlib import Path
import json
import sys
import sysconfig

root = Path(__file__).resolve().parents[1]
parts = ["Agentboard dependency notices\n\nPython build environment licenses follow.\n"]
interpreter = Path(sys.base_prefix)
python_license = next(path for path in (interpreter / 'LICENSE.txt', Path(sysconfig.get_path('stdlib')) / 'LICENSE.txt') if path.is_file())
parts.extend(["\n=== CPython ===\n", python_license.read_text(encoding="utf-8")])
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
lock = json.loads((root / 'package-lock.json').read_text(encoding='utf-8'))
for relative, metadata in lock['packages'].items():
    if not relative.startswith('node_modules/') or metadata.get('dev'):
        continue
    folder = root / relative
    if not folder.is_dir():
        continue
    parts.append(f"\n=== npm {relative.removeprefix('node_modules/')} {metadata.get('version', '')} ===\n")
    for path in folder.iterdir():
        if path.is_file() and path.name.lower().startswith(('license', 'copying', 'notice')):
            parts.append(path.read_text(encoding='utf-8', errors='replace'))
    parts.append(f"License metadata: {metadata.get('license', 'See upstream package')}\n")
output = root / "build" / "desktop" / "THIRD_PARTY_NOTICES.txt"
output.parent.mkdir(parents=True, exist_ok=True)
output.write_text("\n".join(parts), encoding="utf-8")
