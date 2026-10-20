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
    [switch]$Purge,
    # Utilise -Path tel quel (ex. le dossier principal) : pull --ff-only sur main au lieu de reset/clean,
    # .env jamais modifie, port impose par variable d'environnement (un .env existant est requis).
    [switch]$InPlace
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
} elseif ($InPlace) {
    Write-Host "Mise a jour (fast-forward) de $Path sur origin/$Branch"
    $current = (& git -C $Path branch --show-current).Trim()
    if ($current -ne $Branch) { throw "$Path est sur '$current' : -InPlace exige la branche $Branch." }
    if (& git -C $Path status --porcelain --untracked-files=no) { throw "$Path a des modifications locales : les valider ou les ranger avant." }
    Invoke-Native 'git' @('-C', $Path, 'pull', '--ff-only', 'origin', $Branch)
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
if ($InPlace) {
    if (-not (Test-Path -LiteralPath $envFile)) { throw "$envFile manquant : le creer depuis .env.example." }
    $env:GATEWAY_PORT = "$Port"
    $env:NEXT_PUBLIC_SITE_URL = "http://localhost:$Port"
} elseif (-not (Test-Path -LiteralPath $envFile)) {
    Copy-Item -LiteralPath (Join-Path $Path '.env.example') -Destination $envFile
    Set-EnvValue $envFile 'GATEWAY_PORT' "$Port"
    Set-EnvValue $envFile 'NEXT_PUBLIC_SITE_URL' "http://localhost:$Port"
    Write-Host '.env cree depuis .env.example (valeurs factices).'
} else {
    # .env existant : jamais ecrase, mais on y ajoute les variables apparues depuis dans .env.example.
    $have = @(Get-Content -LiteralPath $envFile | ForEach-Object { if ($_ -match '^\s*([A-Za-z_][A-Za-z0-9_]*)=') { $Matches[1] } })
    $missing = @(Get-Content -LiteralPath (Join-Path $Path '.env.example') | Where-Object { $_ -match '^\s*([A-Za-z_][A-Za-z0-9_]*)=' -and ($have -notcontains $Matches[1]) })
    if ($missing.Count -gt 0) {
        $content = [System.IO.File]::ReadAllText($envFile).TrimEnd("`r", "`n")
        [System.IO.File]::WriteAllText($envFile, ($content + "`n" + ($missing -join "`n") + "`n"), (New-Object System.Text.UTF8Encoding($false)))
        Write-Host "$($missing.Count) variable(s) ajoutee(s) au .env depuis .env.example."
    }
}

# Cles de signature d'auth (ignorees par Git, generation idempotente).
if (Test-Path -LiteralPath (Join-Path $Path 'scripts\init-auth-keys.sh')) {
    $sh = Join-Path (Split-Path (Split-Path (Get-Command git).Source)) 'bin\sh.exe'
    if (-not (Test-Path -LiteralPath $sh)) { $sh = 'sh' }
    Push-Location $Path
    try { Invoke-Native $sh @('scripts/init-auth-keys.sh') } finally { Pop-Location }
}
if ($InPlace) { $currentPort = "$Port" } else { $currentPort = ((Get-Content -LiteralPath $envFile | Where-Object { $_ -match '^GATEWAY_PORT=' }) -replace '^GATEWAY_PORT=', '').Trim() }
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
