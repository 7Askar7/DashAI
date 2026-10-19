#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
if [[ "$(uname -s)" != Darwin ]]; then
  echo 'macOS binaries must be built on a native macOS host.' >&2
  exit 1
fi
python3 -m venv .venv-build
.venv-build/bin/python -c 'import sys; assert sys.version_info[:2] == (3, 14), "Build requires Python 3.14"'
.venv-build/bin/python -m pip install -r requirements-build-lock.txt
npm ci
npm ci --prefix vscode-extension --ignore-scripts
npm run build
.venv-build/bin/python scripts/third_party_notices.py
.venv-build/bin/python -m PyInstaller --noconfirm --log-level WARN --workpath build/desktop/pyinstaller --distpath artifacts/desktop packaging/agentboard.spec
.venv-build/bin/python scripts/package_vscode.py --marketplace
