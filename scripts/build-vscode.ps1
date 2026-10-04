param([switch]$SkipDependencies)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot
$extensionRoot = Join-Path $projectRoot 'vscode-extension'
$version = (Get-Content -LiteralPath 'package.json' -Raw -Encoding UTF8 | ConvertFrom-Json).version
$extensionVersion = (Get-Content -LiteralPath (Join-Path $extensionRoot 'package.json') -Raw -Encoding UTF8 | ConvertFrom-Json).version
if ($version -ne $extensionVersion) { throw 'Root and extension release versions must match.' }
if ($version -notmatch '^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$') { throw 'Use a three-part numeric release version.' }

$nodeMajor = [int]((& node --version).TrimStart('v').Split('.')[0])
function Invoke-BuildNode {
    param([string[]]$NodeArgs)
    if ($nodeMajor -ge 22) { & node @NodeArgs }
    else { & npx --yes --package=node@22 -- node @NodeArgs }
    if ($LASTEXITCODE -ne 0) { throw 'VS Code build tooling failed.' }
}
if (-not $SkipDependencies) {
    if ($nodeMajor -ge 22) { & npm ci --prefix $extensionRoot --ignore-scripts }
    else { & npx --yes --package=node@22 --package=npm@10.9.4 -- npm ci --prefix $extensionRoot --ignore-scripts }
    if ($LASTEXITCODE -ne 0) { throw 'Extension build dependencies failed.' }
}
$vsceCli = Join-Path $extensionRoot 'node_modules\@vscode\vsce\vsce'
if (-not (Test-Path -LiteralPath $vsceCli)) { throw 'Install extension build dependencies first.' }

$bundle = Join-Path $projectRoot 'artifacts\desktop\Agentboard'
foreach ($name in @('Agentboard.exe', 'AgentboardMCP.exe', '_internal\package.json')) {
    if (-not (Test-Path -LiteralPath (Join-Path $bundle $name))) { throw "Missing frozen runtime: $name. Run build-desktop.ps1 first." }
}
$bundleVersion = (Get-Content -LiteralPath (Join-Path $bundle '_internal\package.json') -Raw -Encoding UTF8 | ConvertFrom-Json).version
if ($bundleVersion -ne $version) { throw 'Frozen runtime is stale. Rebuild the desktop bundle before packaging VSIX.' }
$binaryVersion = & (Join-Path $bundle 'AgentboardMCP.exe') --version
if ($LASTEXITCODE -ne 0 -or $binaryVersion.Trim() -ne $version) { throw 'Frozen executable version does not match the release.' }
if (Get-ChildItem -LiteralPath $bundle | Where-Object Name -NotIn @('Agentboard.exe', 'AgentboardMCP.exe', '_internal')) { throw 'Frozen bundle contains unexpected resources.' }
if (Get-ChildItem -LiteralPath $bundle -Recurse -File | Where-Object Name -In @('connector-secrets.json', 'agentboard.sqlite3', 'ed25519-private.key', '.mcp.json')) { throw 'Personal data must never enter a VSIX.' }

# A fresh staging directory avoids mixing assets from earlier builds.
$staging = Join-Path $projectRoot "build\vscode\$version-$([guid]::NewGuid().ToString('N'))"
New-Item -ItemType Directory -Path (Join-Path $staging 'runtime') -Force | Out-Null
foreach ($name in @('package.json', '.vscodeignore', 'extension.cjs', 'updates.cjs', 'update-channel.json', 'README.md')) {
    Copy-Item -LiteralPath (Join-Path $extensionRoot $name) -Destination $staging
}
if (Test-Path -LiteralPath (Join-Path $extensionRoot 'LICENSE')) { Copy-Item -LiteralPath (Join-Path $extensionRoot 'LICENSE') -Destination $staging }
Copy-Item -LiteralPath (Join-Path $extensionRoot 'assets') -Destination $staging -Recurse
Copy-Item -LiteralPath (Join-Path $projectRoot 'public\brand\dashai-logo-128.png') -Destination (Join-Path $staging 'assets')
Copy-Item -LiteralPath $bundle -Destination (Join-Path $staging 'runtime') -Recurse
$releaseDir = Join-Path $projectRoot 'artifacts\releases'
New-Item -ItemType Directory -Path $releaseDir -Force | Out-Null
$vsix = Join-Path $releaseDir "Agentboard-VSCode-$version-win32-x64.vsix"
Push-Location -LiteralPath $staging
try { Invoke-BuildNode @($vsceCli, 'package', '--target', 'win32-x64', '--no-dependencies', '--skip-license', '--out', $vsix) }
finally { Pop-Location }
$verifyPackage = @'
import json, sys, zipfile
with zipfile.ZipFile(sys.argv[1]) as archive:
    names = set(archive.namelist())
    required = {'extension/package.json', 'extension/extension.cjs', 'extension/updates.cjs',
                'extension/update-channel.json', 'extension/assets/agentboard.svg', 'extension/assets/dashai-logo-128.png',
                'extension/runtime/Agentboard/Agentboard.exe', 'extension/runtime/Agentboard/AgentboardMCP.exe',
                'extension/runtime/Agentboard/_internal/package.json',
                'extension/runtime/Agentboard/_internal/dist/index.html',
                'extension/runtime/Agentboard/_internal/THIRD_PARTY_NOTICES.txt'}
    assert required <= names, f'Missing VSIX resources: {required - names}'
    forbidden = {'connector-secrets.json', 'agentboard.sqlite3', 'ed25519-private.key', '.mcp.json'}
    assert not any(name.rsplit('/', 1)[-1] in forbidden for name in names), 'Personal data in VSIX'
    assert not any(name.startswith(('extension/node_modules/', 'extension/tests/')) for name in names), 'Development files in VSIX'
    package = json.loads(archive.read('extension/package.json'))
    assert package['version'] == sys.argv[2] and package['publisher'] == '7Askar7' and package['name'] == 'agentboard'
    assert package['icon'] == 'assets/dashai-logo-128.png'
    assert 'win32-x64' in archive.read('extension.vsixmanifest').decode('utf-8'), 'Missing Windows x64 target'
print('VSIX resources and data isolation: PASS')
'@
$verifyPackage | & (Join-Path $projectRoot '.venv-build\Scripts\python.exe') - $vsix $version
if ($LASTEXITCODE -ne 0) { throw 'Packaged VSIX verification failed.' }
Write-Output $vsix
