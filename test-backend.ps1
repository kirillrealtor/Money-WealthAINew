param([string[]]$PytestArgs = @())
$ErrorActionPreference = 'Stop'
$projectRoot = $PSScriptRoot
$backendPython = Join-Path $projectRoot '.venv/Scripts/python.exe'
if (!(Test-Path -LiteralPath $backendPython)) { throw 'Run setup.ps1 first to create the Python environment.' }

$dockerCommand = Get-Command docker -ErrorAction SilentlyContinue
$dockerExe = if ($dockerCommand) { $dockerCommand.Source } else { $null }
if (!$dockerExe) {
    foreach ($candidate in @(
        (Join-Path $env:LOCALAPPDATA 'Programs/DockerDesktop/resources/bin/docker.exe'),
        'C:/Program Files/Docker/Docker/resources/bin/docker.exe'
    )) {
        if (Test-Path -LiteralPath $candidate) { $dockerExe = $candidate; break }
    }
}
if (!$dockerExe) { throw 'Install and start Docker Desktop before running integration tests.' }

function Check-TestExit([string]$Step) {
    if ($LASTEXITCODE -ne 0) { throw "$Step failed (exit $LASTEXITCODE)." }
}

# This runner uses only the Compose stack's local development credentials.
# A separate database and Redis namespace prevent the running app's worker from
# claiming test jobs or the test fixtures from clearing the demo's rate limits.
$savedEnvironment = @{}
foreach ($name in @('DATABASE_URL','MIGRATION_DATABASE_URL','REDIS_URL','ENV')) {
    $savedEnvironment[$name] = [Environment]::GetEnvironmentVariable($name, 'Process')
}
Push-Location -LiteralPath $projectRoot
try {
    & $dockerExe compose up -d --wait postgres redis
    Check-TestExit 'Starting local test datastores'
    $exists = & $dockerExe compose exec -T postgres psql -U advisor -d postgres -Atc "SELECT 1 FROM pg_database WHERE datname='financial_advisor_test'"
    Check-TestExit 'Checking test database'
    if ($exists -ne '1') {
        & $dockerExe compose exec -T postgres createdb -U advisor financial_advisor_test
        Check-TestExit 'Creating test database'
    }
    $env:DATABASE_URL = 'postgres://app_user:app_user@127.0.0.1:5433/financial_advisor_test'
    $env:MIGRATION_DATABASE_URL = 'postgres://advisor:advisor@127.0.0.1:5433/financial_advisor_test'
    $env:REDIS_URL = 'redis://127.0.0.1:6380/1'
    $env:ENV = 'test'
    Set-Location -LiteralPath (Join-Path $projectRoot 'backend')
    & $backendPython -m scripts.migrate
    Check-TestExit 'Migrating test database'
    & $backendPython -m pytest @PytestArgs
    Check-TestExit 'Backend tests'
} finally {
    # Never rewrite backend/.env or leave this shell pointing at the test database.
    foreach ($name in $savedEnvironment.Keys) {
        [Environment]::SetEnvironmentVariable($name, $savedEnvironment[$name], 'Process')
    }
    Pop-Location
}
