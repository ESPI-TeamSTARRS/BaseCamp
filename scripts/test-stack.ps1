<#
.SYNOPSIS
  Met a jour un clone de test de main et reconstruit la pile Basecamp en local.

.DESCRIPTION
  1. Clone le depot dans -Path si absent, sinon fetch + reset --hard sur origin/main
     (le clone de test n'est jamais modifie a la main : tout travail local y est perdu).
  2. Cree .env depuis .env.example au premier lancement (valeurs factices) et y fixe
     GATEWAY_PORT. Un .env existant n'est jamais ecrase.
  3. Lance `docker compose -p basecamp-test up -d --build --wait`.
  4. Affiche l'adresse a ouvrir et l'etat des services.

  Compatible Windows PowerShell 5.1 et PowerShell 7. Aucun secret : .env est ignore par Git.

.EXAMPLE
  .\scripts\test-stack.ps1
  .\scripts\test-stack.ps1 -Port 8181
  .\scripts\test-stack.ps1 -Down
#>
[CmdletBinding()]
param(
    # Clone de test, distinct du depot de developpement et de ses worktrees.
    [string]$Path = $(if ($env:BASECAMP_TEST_DIR) { $env:BASECAMP_TEST_DIR } else { Join-Path $HOME 'Desktop\Projects\BaseCamp-test' }),
    # Port de la passerelle (127.0.0.1). 8180 evite le 8080 des piles de developpement.
    [int]$Port = 8180,
    # Depot a cloner au premier lancement (defaut : origin du depot qui contient ce script).
    [string]$RepoUrl,
    # Arrete la pile de test (conserve les donnees) au lieu de la mettre a jour.
    [switch]$Down,
    # Avec -Down : supprime aussi les volumes (donnees).
    [switch]$Purge
)

$ErrorActionPreference = 'Stop'
$ProjectName = 'basecamp-test'
$Branch = 'main'

function Invoke-Native {
    param([string]$Exe, [string[]]$Arguments)
    & $Exe @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Echec : $Exe $($Arguments -join ' ') (code $LASTEXITCODE)"
    }
}

function Set-EnvValue {
    param([string]$File, [string]$Key, [string]$Value)
    $lines = Get-Content -LiteralPath $File
    $found = $false
    $out = foreach ($line in $lines) {
        if ($line -match "^\s*$([regex]::Escape($Key))=") { $found = $true; "$Key=$Value" } else { $line }
    }
    if (-not $found) { $out = @($out) + "$Key=$Value" }
    # LF, UTF-8 sans BOM : comme le reste du depot.
    [System.IO.File]::WriteAllText($File, (($out -join "`n") + "`n"), (New-Object System.Text.UTF8Encoding($false)))
}

# --- Garde-fous sur le chemin -------------------------------------------------
$Path = [System.IO.Path]::GetFullPath($Path)
$scriptRepo = (& git -C $PSScriptRoot rev-parse --show-toplevel 2>$null)
if ($scriptRepo -and ([System.IO.Path]::GetFullPath($scriptRepo) -eq $Path) -eq $false -and $Path.StartsWith([System.IO.Path]::GetFullPath($scriptRepo) + [System.IO.Path]::DirectorySeparatorChar, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "Le clone de test ne doit pas etre dans un depot de developpement ($scriptRepo)."
}

if ($Down) {
    if (-not (Test-Path -LiteralPath (Join-Path $Path 'docker-compose.yml'))) { throw "Aucun clone de test dans $Path." }
    Push-Location $Path
    try {
        $downArgs = @('compose', '-p', $ProjectName, 'down')
        if ($Purge) { $downArgs += '-v' }
        Invoke-Native 'docker' $downArgs
    } finally { Pop-Location }
    return
}

# --- 1. Clone / mise a jour de main -------------------------------------------
if (-not (Test-Path -LiteralPath (Join-Path $Path '.git'))) {
    if (-not $RepoUrl) { $RepoUrl = (& git -C $PSScriptRoot remote get-url origin) }
    if (-not $RepoUrl) { throw 'Depot introuvable : passer -RepoUrl.' }
    if ((Test-Path -LiteralPath $Path) -and (Get-ChildItem -LiteralPath $Path -Force | Select-Object -First 1)) {
        throw "$Path existe et n'est pas un clone Git : le vider ou choisir un autre -Path."
    }
    Write-Host "Clonage de $RepoUrl dans $Path"
    Invoke-Native 'git' @('clone', '--branch', $Branch, $RepoUrl, $Path)
} else {
    Write-Host "Mise a jour de $Path sur origin/$Branch"
    Invoke-Native 'git' @('-C', $Path, 'fetch', '--prune', 'origin', $Branch)
    Invoke-Native 'git' @('-C', $Path, 'checkout', '--force', $Branch)
    Invoke-Native 'git' @('-C', $Path, 'reset', '--hard', "origin/$Branch")
    # Supprime les fichiers non suivis ; les fichiers ignores (.env) sont conserves.
    Invoke-Native 'git' @('-C', $Path, 'clean', '-fd')
}
$sha = (& git -C $Path log -1 --format='%h %s').Trim()
Write-Host "Version testee : $sha"

# --- 2. Configuration locale (.env factice, non versionne) --------------------
$envFile = Join-Path $Path '.env'
if (-not (Test-Path -LiteralPath $envFile)) {
    Copy-Item -LiteralPath (Join-Path $Path '.env.example') -Destination $envFile
    Set-EnvValue $envFile 'GATEWAY_PORT' "$Port"
    Set-EnvValue $envFile 'NEXT_PUBLIC_SITE_URL' "http://localhost:$Port"
    Write-Host '.env cree depuis .env.example (valeurs factices).'
}
$currentPort = ((Get-Content -LiteralPath $envFile | Where-Object { $_ -match '^GATEWAY_PORT=' }) -replace '^GATEWAY_PORT=', '').Trim()
if (-not $currentPort) { $currentPort = '8080' }

# --- 3. Reconstruction de la pile ---------------------------------------------
Push-Location $Path
try {
    Invoke-Native 'docker' @('compose', '-p', $ProjectName, 'up', '-d', '--build', '--wait', '--remove-orphans')

    # --- 4. Resultat -----------------------------------------------------------
    Write-Host ''
    Invoke-Native 'docker' @('compose', '-p', $ProjectName, 'ps', '--all')
    Write-Host ''
    Write-Host "Application : http://127.0.0.1:$currentPort/"
    try {
        $r = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:$currentPort/api/shop/health/ready" -TimeoutSec 5
        Write-Host "Sante shop (/api/shop/health/ready) : HTTP $($r.StatusCode)"
    } catch {
        Write-Warning "Sante shop injoignable : $($_.Exception.Message)"
    }
} finally {
    Pop-Location
}
