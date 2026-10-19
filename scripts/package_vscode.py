"""Package the native runtime for its actual VS Code platform; never cross-label binaries."""
from __future__ import annotations

import argparse
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def host_target() -> str:
    machine = platform.machine().lower()
    if sys.platform == 'win32' and machine in {'amd64', 'x86_64'}:
        return 'win32-x64'
    if sys.platform == 'darwin' and machine in {'arm64', 'aarch64', 'x86_64'}:
        return 'darwin-arm64' if machine != 'x86_64' else 'darwin-x64'
    raise ValueError('Build on Windows x64 or native macOS Apple Silicon / Intel')


def verify_package(file: Path, version: str, target: str, marketplace: bool) -> None:
    suffix = '.exe' if target == 'win32-x64' else ''
    prefix = 'extension/runtime/Agentboard/'
    with zipfile.ZipFile(file) as archive:
        names = set(archive.namelist())
        required = {'extension/package.json', 'extension/extension.cjs',
                    'extension/assets/agentboard.svg', 'extension/assets/dashai-logo-128.png',
                    prefix + 'Agentboard' + suffix, prefix + 'AgentboardMCP' + suffix,
                    prefix + '_internal/package.json', prefix + '_internal/dist/index.html',
                    prefix + '_internal/THIRD_PARTY_NOTICES.txt'}
        assert required <= names, f'Missing VSIX resources: {required - names}'
        updater = {'extension/updates.cjs', 'extension/update-channel.json',
                   prefix + '_internal/release-channel.json', prefix + '_internal/desktop/install-update.ps1'}
        assert (not names & updater) if marketplace else updater <= names, 'Unexpected updater resources'
        forbidden = {'connector-secrets.json', 'agentboard.sqlite3', 'ed25519-private.key', '.mcp.json'}
        assert not any(n.rsplit('/', 1)[-1] in forbidden for n in names), 'Personal data in VSIX'
        assert not any(n.startswith(('extension/node_modules/', 'extension/tests/')) for n in names), 'Development files in VSIX'
        assert not any('/_internal/' + item in n for n in names
                       for item in ('docs/', '.agents/', '.claude/', 'AGENTS.md', 'CLAUDE.md', 'README.md')), 'Project files in VSIX'
        package = json.loads(archive.read('extension/package.json'))
        system, cpu = target.split('-')
        assert package['version'] == version and package['publisher'] == '7Askar7'
        assert package['name'] == ('dashai' if marketplace else 'agentboard')
        assert package['os'] == [system] and package['cpu'] == [cpu]
        assert not marketplace or ('checkUpdates' not in json.dumps(package) and 'configuration' not in package['contributes'])
        assert package['icon'] == 'assets/dashai-logo-128.png'
        assert target in archive.read('extension.vsixmanifest').decode('utf-8')
        assert json.loads(archive.read(prefix + '_internal/package.json'))['version'] == version
        if system == 'darwin':
            for name in ('Agentboard', 'AgentboardMCP'):
                assert archive.getinfo(prefix + name).external_attr >> 16 & 0o111, 'macOS executable permission missing'
            assert not any(n.endswith('.exe') for n in names), 'Windows executable in macOS VSIX'
        assert archive.testzip() is None, 'Corrupt VSIX'


def package(target: str, marketplace: bool) -> Path:
    if target != host_target():
        raise ValueError('Target does not match this build host; native binaries are required')
    if target != 'win32-x64' and not marketplace:
        raise ValueError('macOS packages use Marketplace updates')
    extension = ROOT / 'vscode-extension'
    bundle = ROOT / 'artifacts/desktop/Agentboard'
    version = json.loads((ROOT / 'package.json').read_text(encoding='utf-8'))['version']
    assert re.fullmatch(r'(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)', version)
    assert json.loads((extension / 'package.json').read_text(encoding='utf-8'))['version'] == version
    assert json.loads((bundle / '_internal/package.json').read_text(encoding='utf-8'))['version'] == version
    suffix = '.exe' if target == 'win32-x64' else ''
    assert {p.name for p in bundle.iterdir()} == {'Agentboard' + suffix, 'AgentboardMCP' + suffix, '_internal'}
    forbidden = {'connector-secrets.json', 'agentboard.sqlite3', 'ed25519-private.key', '.mcp.json'}
    for file in bundle.rglob('*'):
        assert file.name not in forbidden, 'Personal data in runtime'
        if file.is_symlink():
            assert not Path(os.readlink(file)).is_absolute() and file.resolve().is_relative_to(bundle.resolve()), 'External runtime symlink'
    actual = subprocess.check_output([str(bundle / ('AgentboardMCP' + suffix)), '--version'], text=True, timeout=30).strip()
    assert actual == version, 'Frozen runtime version mismatch'
    parent = ROOT / 'build/vscode'
    parent.mkdir(parents=True, exist_ok=True)
    assert parent.resolve().is_relative_to(ROOT.resolve())
    release = ROOT / 'artifacts/releases'
    release.mkdir(parents=True, exist_ok=True)
    output = release / f'{"DashAI-Marketplace" if marketplace else "Agentboard-VSCode"}-{version}-{target}.vsix'
    with tempfile.TemporaryDirectory(prefix=version + '-', dir=parent) as directory:
        staging = Path(directory)
        # Includes TemporaryDirectory cleanup: all recursive operations stay in this verified workspace staging.
        assert staging.resolve().is_relative_to(parent.resolve())
        for name in ('package.json', '.vscodeignore', 'extension.cjs', 'README.md'):
            shutil.copy2(extension / name, staging / name)
        if (extension / 'LICENSE').is_file():
            shutil.copy2(extension / 'LICENSE', staging / 'LICENSE')
        shutil.copytree(extension / 'assets', staging / 'assets')
        shutil.copy2(ROOT / 'public/brand/dashai-logo-128.png', staging / 'assets')
        shutil.copytree(bundle, staging / 'runtime/Agentboard', symlinks=True)
        manifest = json.loads((staging / 'package.json').read_text(encoding='utf-8'))
        system, cpu = target.split('-')
        manifest.update(os=[system], cpu=[cpu])
        if marketplace:
            manifest['name'] = 'dashai'
            contributes = manifest['contributes']
            contributes['commands'] = [c for c in contributes['commands'] if c['command'] != 'agentboard.checkUpdates']
            for view in contributes['viewsWelcome']:
                view['contents'] = re.sub(r'\n\[[^\]]*\]\(command:agentboard\.checkUpdates\)', '', view['contents'])
            contributes.pop('configuration', None)
            for name in ('runtime/Agentboard/_internal/release-channel.json', 'runtime/Agentboard/_internal/desktop'):
                file = staging / name
                assert file.resolve().is_relative_to(staging.resolve())
                if file.is_dir():
                    shutil.rmtree(file)
                elif file.exists():
                    file.unlink()
        else:
            for name in ('updates.cjs', 'update-channel.json'):
                shutil.copy2(extension / name, staging / name)
        (staging / 'package.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        node = ['node'] if int(subprocess.check_output(['node', '--version'], text=True).split('.')[0][1:]) >= 22 else [shutil.which('npx'), '--yes', '--package=node@22', '--', 'node']
        subprocess.run([*node, str(extension / 'node_modules/@vscode/vsce/vsce'), 'package', '--target', target,
                        '--follow-symlinks', '--no-dependencies', '--skip-license', '--out', str(output)], cwd=staging, check=True)
    verify_package(output, version, target, marketplace)
    print(f'VSIX resources, native target and data isolation: PASS\n{output}')
    return output


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--target', choices=['win32-x64', 'darwin-arm64', 'darwin-x64'])
    parser.add_argument('--marketplace', action='store_true')
    args = parser.parse_args()
    package(args.target or host_target(), args.marketplace)
