param(
    [string]$ManifestUrl = $env:AGENTBOARD_UPDATE_MANIFEST_URL,
    [string]$PublicKey = $env:AGENTBOARD_UPDATE_PUBLIC_KEY,
    [string]$PythonExecutable = 'python',
    [string]$InnoCompiler,
    [switch]$SkipDependencies,
    [switch]$SkipFrontend
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot
$pythonExe = Join-Path $projectRoot '.venv-build\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonExe)) {
    & $PythonExecutable -m venv .venv-build
    if ($LASTEXITCODE -ne 0) { throw 'Could not create the Python build environment.' }
}
& $pythonExe -c 'import sys; assert sys.version_info[:2] == (3, 14), "Desktop builds require Python 3.14; select -PythonExecutable when creating .venv-build"'
if ($LASTEXITCODE -ne 0) { throw 'The desktop build environment must use Python 3.14.' }
if (-not $SkipDependencies) {
    $buildRequirements = if (Test-Path -LiteralPath 'requirements-build-lock.txt') { 'requirements-build-lock.txt' } else { 'requirements-build.txt' }
    & $pythonExe -m pip install -r $buildRequirements
    if ($LASTEXITCODE -ne 0) { throw 'Python build dependencies failed.' }
    & npm ci
    if ($LASTEXITCODE -ne 0) { throw 'npm ci failed.' }
}
if (-not $SkipFrontend) {
    & npm run build
    if ($LASTEXITCODE -ne 0) { throw 'Frontend build failed.' }
}
if (-not (Test-Path -LiteralPath 'dist\index.html')) { throw 'Built frontend is missing.' }

$version = (Get-Content -LiteralPath 'package.json' -Raw -Encoding UTF8 | ConvertFrom-Json).version
if ($version -notmatch '^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$') { throw 'Use a three-part numeric release version.' }
$generated = Join-Path $projectRoot 'build\desktop'
New-Item -ItemType Directory -Path $generated -Force | Out-Null
$channelArgs = @('scripts/release.py', 'channel', '--output', (Join-Path $generated 'release-channel.json'))
if ($ManifestUrl -and -not $PublicKey) {
    $PublicKey = (Get-Content -LiteralPath 'packaging\update-public-key.txt' -Raw -Encoding UTF8).Trim()
}
if ($ManifestUrl -or $PublicKey) { $channelArgs += @('--manifest-url', $ManifestUrl, '--public-key', $PublicKey) }
& $pythonExe @channelArgs
if ($LASTEXITCODE -ne 0) { throw 'Release channel validation failed.' }

$fileVersion = ($version -split '\.') -join ', '
$versionInfo = @"
VSVersionInfo(ffi=FixedFileInfo(filevers=($fileVersion, 0), prodvers=($fileVersion, 0), mask=0x3f, flags=0x0, OS=0x40004, fileType=0x1, subtype=0x0, date=(0, 0)), kids=[StringFileInfo([StringTable('040904B0', [StringStruct('CompanyName', 'DashAI'), StringStruct('FileDescription', 'DashAI local workspace'), StringStruct('FileVersion', '$version'), StringStruct('ProductName', 'DashAI'), StringStruct('ProductVersion', '$version')])]), VarFileInfo([VarStruct('Translation', [1033, 1200])])])
"@
[System.IO.File]::WriteAllText((Join-Path $generated 'version-info.txt'), $versionInfo, [System.Text.UTF8Encoding]::new($false))
& $pythonExe scripts/third_party_notices.py
if ($LASTEXITCODE -ne 0) { throw 'Dependency license collection failed.' }
& $pythonExe -m PyInstaller --noconfirm --log-level WARN --workpath build\desktop\pyinstaller --distpath artifacts\desktop packaging\agentboard.spec
if ($LASTEXITCODE -ne 0) { throw 'PyInstaller failed.' }

if (-not $InnoCompiler) {
    $candidates = @("$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe", "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe")
    $InnoCompiler = $candidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
}
if (-not $InnoCompiler -or -not (Test-Path -LiteralPath $InnoCompiler)) {
    throw 'Install official Inno Setup 6.7+ from https://jrsoftware.org/isdl.php, or pass -InnoCompiler.'
}
$bundle = Join-Path $projectRoot 'artifacts\desktop\Agentboard'
$releaseDir = Join-Path $projectRoot 'artifacts\releases'
& $InnoCompiler /Qp "/DAppVersion=$version" "/DBundleDir=$bundle" "/DReleaseDir=$releaseDir" packaging\agentboard.iss
if ($LASTEXITCODE -ne 0) { throw 'Installer compilation failed.' }
Write-Output (Join-Path $releaseDir "Agentboard-Setup-$version.exe")
