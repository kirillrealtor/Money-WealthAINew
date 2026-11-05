param([switch]$SkipServices, [switch]$SkipInstall)
$ErrorActionPreference = 'Stop'
$projectRoot = $PSScriptRoot
Set-Location -LiteralPath $projectRoot

function Check-Exit([string]$Step) {
    if ($LASTEXITCODE -ne 0) { throw "$Step failed (exit $LASTEXITCODE)." }
}

# Detect portable tooling used by the workspace as well as standard PATH installs.
if (!(Get-Command node -ErrorAction SilentlyContinue)) {
    $portableNode = Get-ChildItem "$env:LOCALAPPDATA/codex-tools/node-*/node.exe" -ErrorAction SilentlyContinue |
        Sort-Object FullName -Descending | Select-Object -First 1
    if ($portableNode) { $env:PATH = "$($portableNode.DirectoryName);$env:PATH" }
}
if (!(Get-Command uv -ErrorAction SilentlyContinue)) {
    $localUv = Join-Path $env:USERPROFILE '.local/bin'
    if (Test-Path (Join-Path $localUv 'uv.exe')) { $env:PATH = "$localUv;$env:PATH" }
}
foreach ($tool in @('uv','node','npm.cmd')) {
    if (!(Get-Command $tool -ErrorAction SilentlyContinue)) {
        throw "Missing $tool. Install uv (https://docs.astral.sh/uv/) and Node.js 22 (https://nodejs.org/)."
    }
}
if ([int]((& node --version) -replace '^v(\d+).*','$1') -lt 22) { throw 'Node.js 22 or newer is required.' }
if (!(Test-Path '.venv/Scripts/python.exe')) { & uv venv --python 3.11 .venv; Check-Exit 'Python environment' }
$pythonExe = Join-Path $projectRoot '.venv/Scripts/python.exe'
if (!$SkipInstall) {
    & uv pip install --python $pythonExe -r backend/requirements-dev.txt; Check-Exit 'Python dependencies'
    Push-Location frontend
    try { & npm.cmd ci; Check-Exit 'Frontend dependencies' } finally { Pop-Location }
}
& $pythonExe scripts/bootstrap_env.py; Check-Exit 'Environment setup'
if (!$SkipServices) {
    if (!(Get-Command docker -ErrorAction SilentlyContinue)) {
        throw 'Environment files are ready. Install/start Docker Desktop, then rerun setup.ps1 to start Postgres/Redis.'
    }
    & docker compose up -d --wait postgres redis; Check-Exit 'Local datastores'
    Push-Location backend
    try {
        & $pythonExe -m scripts.migrate; Check-Exit 'Database migrations'
        & $pythonExe -m scripts.seed_demo; Check-Exit 'Synthetic demo seed'
    } finally { Pop-Location }
} else {
    Write-Host 'Skipped services, migrations and seed. Run setup.ps1 again when Docker Desktop is ready.'
}
Write-Host 'Next: .\start-dev.ps1 backend (terminal 1), .\start-dev.ps1 frontend (terminal 2).'
Write-Host 'Demo login: demo@fathom.app; password is DEMO_PASSWORD in backend/.env.'
