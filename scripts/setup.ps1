$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Push-Location -LiteralPath $projectRoot
try {
    if (-not (Test-Path -LiteralPath '.venv/Scripts/python.exe')) {
        python -m venv .venv
        if ($LASTEXITCODE -ne 0) { throw 'Не удалось создать Python venv' }
    }
    & .venv/Scripts/python.exe -m pip install -r requirements-lock.txt
    if ($LASTEXITCODE -ne 0) { throw 'Не удалось установить Python dependencies' }
    npm ci
    if ($LASTEXITCODE -ne 0) { throw 'Не удалось установить frontend dependencies' }
    npm run build
    if ($LASTEXITCODE -ne 0) { throw 'Сборка не прошла' }
    Write-Host 'Готово. Запуск: npm start. Коннекторы: npm run connectors:setup.'
} finally {
    Pop-Location
}
