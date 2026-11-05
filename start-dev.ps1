param([Parameter(Mandatory=$true)][ValidateSet('backend','frontend')][string]$Service)
$ErrorActionPreference = 'Stop'
if ($Service -eq 'backend') {
    Set-Location -LiteralPath (Join-Path $PSScriptRoot 'backend')
    & "$PSScriptRoot/.venv/Scripts/python.exe" -m scripts.migrate
    if ($LASTEXITCODE -ne 0) { throw 'Migrations failed; backend was not started.' }
    & "$PSScriptRoot/.venv/Scripts/python.exe" -m uvicorn app.main:app --reload --port 3000
} else {
    if (!(Get-Command node -ErrorAction SilentlyContinue)) {
        $portableNode = Get-ChildItem "$env:LOCALAPPDATA/codex-tools/node-*/node.exe" -ErrorAction SilentlyContinue |
            Sort-Object FullName -Descending | Select-Object -First 1
        if ($portableNode) { $env:PATH = "$($portableNode.DirectoryName);$env:PATH" }
    }
    Set-Location -LiteralPath (Join-Path $PSScriptRoot 'frontend')
    & npm.cmd run dev
}
