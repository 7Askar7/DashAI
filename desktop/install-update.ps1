param(
    [Parameter(Mandatory = $true)][string]$Installer,
    [Parameter(Mandatory = $true)][ValidatePattern('^[0-9a-f]{64}$')][string]$ExpectedHash,
    [Parameter(Mandatory = $true)][long]$ExpectedSize,
    [Parameter(Mandatory = $true)][int]$ParentPid,
    [Parameter(Mandatory = $true)][int]$HelperPid,
    [Parameter(Mandatory = $true)][string]$McpMutex,
    [Parameter(Mandatory = $true)][string]$AppPath
)
$ErrorActionPreference = 'Stop'
# PowerShell 7 callers (including GitHub Actions) can pass their module path to
# Windows PowerShell 5.1. Load only the Windows modules used by this native helper.
$env:PSModulePath = "${env:SystemRoot}\System32\WindowsPowerShell\v1.0\Modules"
$updateLog = Join-Path ([System.IO.Path]::GetDirectoryName($Installer)) 'install-update.log'

try {
    # This process uses Windows PowerShell, not the bundled Python runtime.
    # Both frozen processes must exit before their executables/DLLs are replaced.
    foreach ($processId in @($ParentPid, $HelperPid)) {
        $taskProcess = Get-Process -Id $processId -ErrorAction SilentlyContinue
        if ($null -ne $taskProcess -and -not $taskProcess.WaitForExit(60000)) {
            throw 'Agentboard did not finish shutting down; update postponed.'
        }
    }
    $activeMutex = $null
    try {
        $activeMutex = [System.Threading.Mutex]::OpenExisting($McpMutex)
    } catch [System.Threading.WaitHandleCannotBeOpenedException] {
        # No agent connector has an open handle.
    }
    if ($null -ne $activeMutex) {
        $activeMutex.Dispose()
        throw 'An agent connector is still active; update postponed.'
    }
    $installerFile = Get-Item -LiteralPath $Installer
    if ($installerFile.Length -ne $ExpectedSize) {
        throw 'Installer size changed after signature verification.'
    }
    $actualHash = (Get-FileHash -LiteralPath $Installer -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($actualHash -ne $ExpectedHash) {
        throw 'Installer hash changed after signature verification.'
    }
    $setupProcess = Start-Process -FilePath $Installer -ArgumentList @('/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART', '/UPDATE=1') -WindowStyle Hidden -PassThru
    $setupProcess.WaitForExit()
    if ($setupProcess.ExitCode -ne 0) {
        throw "Installer failed with exit code $($setupProcess.ExitCode)."
    }
    Add-Content -LiteralPath $updateLog -Value 'Update installed successfully.' -Encoding UTF8
} catch {
    Add-Content -LiteralPath $updateLog -Value $_.Exception.Message -Encoding UTF8
    if (Test-Path -LiteralPath $AppPath -PathType Leaf) {
        Start-Process -FilePath $AppPath -WindowStyle Hidden
    }
    exit 1
}
