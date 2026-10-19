param([switch]$SkipDependencies, [switch]$Marketplace)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot
$extensionRoot = Join-Path $projectRoot 'vscode-extension'
$version = (Get-Content -LiteralPath 'package.json' -Raw -Encoding UTF8 | ConvertFrom-Json).version
$extensionVersion = (Get-Content -LiteralPath (Join-Path $extensionRoot 'package.json') -Raw -Encoding UTF8 | ConvertFrom-Json).version
if ($version -ne $extensionVersion) { throw 'Root and extension release versions must match.' }
if ($version -notmatch '^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$') { throw 'Use a three-part numeric release version.' }

$nodeMajor = [int]((& node --version).TrimStart('v').Split('.')[0])
if (-not $SkipDependencies) {
    if ($nodeMajor -ge 22) { & npm ci --prefix $extensionRoot --ignore-scripts }
    else { & npx --yes --package=node@22 --package=npm@10.9.4 -- npm ci --prefix $extensionRoot --ignore-scripts }
    if ($LASTEXITCODE -ne 0) { throw 'Extension build dependencies failed.' }
}
$vsceCli = Join-Path $extensionRoot 'node_modules\@vscode\vsce\vsce'
if (-not (Test-Path -LiteralPath $vsceCli)) { throw 'Install extension build dependencies first.' }

$python = Join-Path $projectRoot '.venv-build\Scripts\python.exe'
$packageArgs = @('scripts/package_vscode.py', '--target', 'win32-x64')
if ($Marketplace) { $packageArgs += '--marketplace' }
& $python @packageArgs
if ($LASTEXITCODE -ne 0) { throw 'VSIX packaging or verification failed.' }
