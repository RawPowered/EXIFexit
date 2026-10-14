# Check tracked paths and committed history before pushing.
param([switch]$PathsOnly)
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Push-Location $root
try {
    $tracked = @(git ls-files)
    if ($LASTEXITCODE -ne 0) { throw "Cannot read the Git index." }
    if ($tracked.Count -eq 0) { throw "No tracked files: stage the intended source files first." }
    $blocked = @($tracked | Where-Object {
        $_ -match '(?i)(^|/)(PDFs|private|samples|output|artifacts|bin|obj|__pycache__|\.venv|\.git|\.vs)(/|$)' -or
        $_ -match '(?i)\.(pdf|jpg|jpeg|jpe|jfif|png|tif|tiff|webp|bmp|gif|ico|pem|key|p12|pfx|keystore|jks|log|bak|tmp|pyc|pyo|dll|exe|pdb)$' -or
        $_ -match '(?i)(^|/)(\.env($|\.(?!example$))|id_rsa[^/]*|id_ed25519[^/]*|credentials[^/]*\.json|secrets[^/]*\.json)$'
    })
    if ($blocked.Count -gt 0) {
        $blocked | ForEach-Object { Write-Host "Blocked tracked path: $_" }
        throw "Remove private or generated files from the index before pushing."
    }
    Write-Host "Tracked-path check passed ($($tracked.Count) files)."
    if (-not $PathsOnly) {
        if (-not (Get-Command gitleaks -ErrorAction SilentlyContinue)) {
            throw "Install Gitleaks and add it to PATH, or use -PathsOnly for the path check."
        }
        gitleaks git . --redact --no-banner
        if ($LASTEXITCODE -ne 0) { throw "Gitleaks history scan failed." }
        gitleaks dir . --redact --no-banner
        if ($LASTEXITCODE -ne 0) { throw "Gitleaks working-tree scan failed." }
    }
} finally {
    Pop-Location
}
