$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Push-Location $projectRoot
try {
    if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
        throw "Docker was not found. Install Docker Desktop, start it, and retry."
    }
    docker info *> $null
    if ($LASTEXITCODE -ne 0) { throw "Docker Desktop is not running. Start it and retry." }
    if (-not (Test-Path ".env")) {
        throw "No .env file found. Run .\start-trustvault.ps1 once to create local config, then run this recovery script again."
    }
    $appEnvLine = Get-Content ".env" | Where-Object { $_ -match '^APP_ENV=' } | Select-Object -First 1
    if ($appEnvLine -and $appEnvLine.Substring(8).Trim().ToLowerInvariant() -eq "production") {
        throw "This break-glass audit archive recovery is disabled in production. Restore the original key or follow an approved incident-recovery process."
    }

    Write-Host "TRUSTVAULT AUDIT RECOVERY" -ForegroundColor Yellow
    Write-Host "The current audit chain cannot be verified with the available key candidates." -ForegroundColor Yellow
    Write-Host "This operation preserves every existing audit row and its original hash in an append-only archive, labels that history UNVERIFIED, and begins a new HMAC chain. Users, documents, shares, and file storage are not deleted." -ForegroundColor Yellow
    Write-Host "A database backup will be created before any recovery change." -ForegroundColor Yellow
    $confirmation = Read-Host "Type ARCHIVE to confirm this one-time development recovery"
    if ($confirmation -cne "ARCHIVE") { Write-Host "Cancelled; no recovery changes made." -ForegroundColor Cyan; exit 1 }

    docker compose up -d db
    if ($LASTEXITCODE -ne 0) { throw "Could not start the existing database service. No recovery was attempted." }
    Start-Sleep -Seconds 3

    $stamp = Get-Date -Format "yyyyMMdd-HHmmss"
    $containerBackup = "/tmp/trustvault-pre-audit-recovery-$stamp.sql"
    $hostBackup = Join-Path $projectRoot "trustvault-pre-audit-recovery-$stamp.sql"
    docker exec trustvault-db pg_dump -U trustvault -d trustvault -f $containerBackup
    if ($LASTEXITCODE -ne 0) { throw "PostgreSQL backup failed. Recovery aborted; fix database access before retrying." }
    docker cp "trustvault-db:$containerBackup" $hostBackup
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path $hostBackup)) { throw "Could not copy the database backup to the project folder. Recovery aborted." }
    Write-Host "Database backup created: $hostBackup" -ForegroundColor Green

    function Read-EnvValue([string]$Name) {
        $line = Get-Content ".env" | Where-Object { $_ -match "^$([regex]::Escape($Name))=" } | Select-Object -First 1
        if ($null -eq $line) { return "" }
        return $line.Substring($Name.Length + 1).Trim()
    }
    function Set-EnvValue([string]$Name, [string]$Value) {
        $lines = [System.Collections.Generic.List[string]]::new()
        if (Test-Path ".env") { foreach ($line in (Get-Content ".env")) { $lines.Add($line) } }
        $pattern = "^$([regex]::Escape($Name))="
        $found = $false
        $output = [System.Collections.Generic.List[string]]::new()
        foreach ($line in $lines) {
            if ($line -match $pattern) {
                if (-not $found) { $output.Add("$Name=$Value"); $found = $true }
            } else { $output.Add($line) }
        }
        if (-not $found) { $output.Add("$Name=$Value") }
        Set-Content -Path ".env" -Value $output -Encoding ascii
    }
    function New-StrongSecret {
        $rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
        $bytes = New-Object byte[] 48
        $rng.GetBytes($bytes)
        $rng.Dispose()
        return [Convert]::ToBase64String($bytes).TrimEnd('=').Replace('+','-').Replace('/','_')
    }
    function Is-StrongSecret([string]$Value) {
        if ([string]::IsNullOrWhiteSpace($Value) -or $Value.Length -lt 32 -or $Value -match '(?i)change-me|replace-this|local-only|example|secret-here|password|default') { return $false }
        if (($Value.ToCharArray() | Select-Object -Unique).Count -lt 12) { return $false }
        return $true
    }

    # Secrets are generated only when absent/weak. The database password is never rotated here.
    $tokenSecret = Read-EnvValue "TOKEN_SECRET"
    if (-not (Is-StrongSecret $tokenSecret)) {
        $tokenSecret = New-StrongSecret
        Set-EnvValue "TOKEN_SECRET" $tokenSecret
        Write-Host "Generated and saved a stable local TOKEN_SECRET." -ForegroundColor Green
    }
    $auditSecret = Read-EnvValue "AUDIT_HMAC_SECRET"
    if ((-not (Is-StrongSecret $auditSecret)) -or ($auditSecret -ceq $tokenSecret)) {
        do { $auditSecret = New-StrongSecret } while ($auditSecret -ceq $tokenSecret)
        Set-EnvValue "AUDIT_HMAC_SECRET" $auditSecret
        Write-Host "Generated and saved a stable independent AUDIT_HMAC_SECRET for the new chain." -ForegroundColor Green
    }

    docker compose build api
    if ($LASTEXITCODE -ne 0) { throw "API image build failed. The database backup is safe at $hostBackup." }
    Set-EnvValue "TRUSTVAULT_AUDIT_RECOVERY" "archive_unverified"
    docker compose up -d --force-recreate api
    if ($LASTEXITCODE -ne 0) { throw "API container did not start for recovery. Database backup is safe at $hostBackup; inspect docker compose logs api." }

    function Wait-ForApi([int]$Seconds) {
        $tries = [Math]::Ceiling($Seconds / 2)
        for ($i = 0; $i -lt $tries; $i++) {
            try {
                $response = Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/health" -TimeoutSec 2
                if ($response.status -eq "ok") { return $true }
            } catch { }
            Start-Sleep -Seconds 2
        }
        return $false
    }

    if (-not (Wait-ForApi 90)) {
        docker compose logs --tail=100 api
        throw "Recovery did not reach a healthy API. Recovery mode remains set for diagnosis; do not delete volumes. Database backup: $hostBackup"
    }

    # Remove the one-time flag and restart once more to prove ordinary startup verifies the new chain.
    Set-EnvValue "TRUSTVAULT_AUDIT_RECOVERY" ""
    docker compose up -d --force-recreate api
    if ($LASTEXITCODE -ne 0) { throw "Could not restart API with recovery disabled. Database backup: $hostBackup" }
    if (-not (Wait-ForApi 60)) {
        docker compose logs --tail=100 api
        throw "API did not stay healthy after recovery mode was disabled. Database backup: $hostBackup"
    }

    docker compose up -d
    if ($LASTEXITCODE -ne 0) { throw "API recovered, but all services did not start. Run docker compose ps and inspect logs." }
    Write-Host "`nVerifying audit chain after recovery..." -ForegroundColor Cyan
    docker compose exec -T api python -m app.verify_audit
    if ($LASTEXITCODE -ne 0) { throw "Audit verification command failed. Preserve the backup and inspect API logs." }
    docker compose ps
    Write-Host "`nRecovery completed. Open http://localhost:8080" -ForegroundColor Green
    Write-Host "Archived audit events remain available as PRESERVED_BUT_UNVERIFIED in the administrator audit archives endpoint." -ForegroundColor Yellow
    Write-Host "Backup: $hostBackup" -ForegroundColor Green
}
finally { Pop-Location }
