$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Push-Location $projectRoot
try {
    if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
        throw "Docker was not found. Install Docker Desktop, start it, and run this script again."
    }
    docker info *> $null
    if ($LASTEXITCODE -ne 0) {
        throw "Docker Desktop is installed but is not running. Start Docker Desktop and retry."
    }
    if (-not (Test-Path ".env")) {
        Copy-Item ".env.example" ".env"
        Write-Host "Created local .env from .env.example." -ForegroundColor Yellow
    }

    # Rotate only the known development TOKEN_SECRET. Do not silently change
    # POSTGRES_PASSWORD because an existing PostgreSQL volume keeps its own password.
    $envText = Get-Content ".env" -Raw
    $secretMatch = [regex]::Match($envText, '(?m)^TOKEN_SECRET=(.*)$')
    $currentSecret = if ($secretMatch.Success) { $secretMatch.Groups[1].Value.Trim() } else { "" }
    $weakSecret = ($currentSecret.Length -lt 32) -or ($currentSecret -match '(?i)replace|change|local-only|example|secret-here')
    if ($weakSecret) {
        $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
        $randomBytes = New-Object byte[] 48
        $rng.GetBytes($randomBytes)
        $rng.Dispose()
        $newSecret = [Convert]::ToBase64String($randomBytes).TrimEnd('=').Replace('+', '-').Replace('/', '_')
        if ($secretMatch.Success) {
            $envText = [regex]::Replace($envText, '(?m)^TOKEN_SECRET=.*$', "TOKEN_SECRET=$newSecret")
        } else {
            $envText = $envText.TrimEnd() + "`r`nTOKEN_SECRET=$newSecret`r`n"
        }
        Set-Content -Path ".env" -Value $envText -NoNewline -Encoding ascii
        Write-Host "Generated a random TOKEN_SECRET in .env. Existing sessions must sign in again; account and document volumes are preserved." -ForegroundColor Yellow
    }

    # Audit history has its own stable key. Do not rotate it on each app launch;
    # changing it without a planned key-transition would make old event hashes unverifiable.
    $envText = Get-Content ".env" -Raw
    $auditMatch = [regex]::Match($envText, '(?m)^AUDIT_HMAC_SECRET=(.*)$')
    $currentAuditSecret = if ($auditMatch.Success) { $auditMatch.Groups[1].Value.Trim() } else { "" }
    $weakAuditSecret = ($currentAuditSecret.Length -lt 32) -or ($currentAuditSecret -match '(?i)replace|change|local-only|example|secret-here')
    if ($weakAuditSecret) {
        $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
        $randomBytes = New-Object byte[] 48
        $rng.GetBytes($randomBytes)
        $rng.Dispose()
        $newAuditSecret = [Convert]::ToBase64String($randomBytes).TrimEnd('=').Replace('+', '-').Replace('/', '_')
        if ($auditMatch.Success) {
            $envText = [regex]::Replace($envText, '(?m)^AUDIT_HMAC_SECRET=.*$', "AUDIT_HMAC_SECRET=$newAuditSecret")
        } else {
            $envText = $envText.TrimEnd() + "`r`nAUDIT_HMAC_SECRET=$newAuditSecret`r`n"
        }
        Set-Content -Path ".env" -Value $envText -NoNewline -Encoding ascii
        Write-Host "Generated an independent AUDIT_HMAC_SECRET in .env. Keep it stable to preserve audit-chain verification." -ForegroundColor Yellow
    }

    Write-Host "Building and starting DocuSentra services..." -ForegroundColor Cyan
    docker compose up --build -d
    if ($LASTEXITCODE -ne 0) {
        $apiLogs = (docker compose logs --tail=100 api 2>&1 | Out-String)
        if ($apiLogs -match "event_hash_mismatch|legacy_event_hash_mismatch|No valid prior key was available|No valid prior TOKEN_SECRET-keyed") {
            Write-Host $apiLogs -ForegroundColor DarkYellow
            Write-Host "The existing audit history cannot be verified using the available keys. Do not delete volumes or rerun key generation." -ForegroundColor Yellow
            Write-Host "After checking your backup, run .\recover-audit-chain.ps1 and type ARCHIVE only if you accept preserving the old history as UNVERIFIED." -ForegroundColor Yellow
            throw "Audit recovery is required for this local database. Existing user/document data has not been deleted."
        }
        Write-Host $apiLogs -ForegroundColor DarkYellow
        throw "Docker Compose failed. Inspect the API logs above or run 'docker compose logs --tail=100 api'."
    }
    docker compose ps
    Write-Host "`nDocuSentra is starting. Open http://localhost:8080" -ForegroundColor Green
    Write-Host "API docs: http://localhost:8000/docs (local development only)"
    Write-Host "Health:   http://localhost:8000/api/health"
    Start-Process "http://localhost:8080"
}
finally { Pop-Location }
