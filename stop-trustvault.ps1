$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Push-Location $projectRoot
try {
    docker compose down
    if ($LASTEXITCODE -ne 0) { throw "Could not stop TrustVault. Check Docker Desktop and try again." }
    Write-Host "TrustVault stopped. Database and private file volumes were preserved." -ForegroundColor Green
}
finally { Pop-Location }
