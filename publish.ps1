# One-click GitHub publisher for lead-scraper-toolkit
# Usage:  right-click publish.ps1 -> "Run with PowerShell"
#         or in PowerShell:  .\publish.ps1

$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot

Write-Host ""
Write-Host "===========================================" -ForegroundColor Cyan
Write-Host "  Publishing lead-scraper-toolkit to GitHub" -ForegroundColor Cyan
Write-Host "===========================================" -ForegroundColor Cyan
Write-Host ""

# --- Check git ---
if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    Write-Host "ERROR: git is not installed." -ForegroundColor Red
    Write-Host "Install from https://git-scm.com/download/win then rerun this script."
    pause; exit 1
}

# --- Check gh CLI ---
$hasGh = (Get-Command gh -ErrorAction SilentlyContinue) -ne $null
if (-not $hasGh) {
    Write-Host "GitHub CLI (gh) is not installed." -ForegroundColor Yellow
    Write-Host "Easiest path: install it from https://cli.github.com"
    Write-Host "Or install via winget:"
    Write-Host "    winget install --id GitHub.cli" -ForegroundColor Gray
    Write-Host ""
    $install = Read-Host "Try winget install now? (y/n)"
    if ($install -eq "y") {
        winget install --id GitHub.cli --accept-source-agreements --accept-package-agreements
        Write-Host "Installed. Please CLOSE this PowerShell window and open a new one, then rerun publish.ps1."
        pause; exit 0
    } else {
        Write-Host "Install gh, then rerun this script. Exiting."
        pause; exit 1
    }
}

# --- Check gh auth ---
Write-Host "[1/5] Checking GitHub auth..."
gh auth status 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "  Not logged in. Opening browser to authenticate..." -ForegroundColor Yellow
    gh auth login --web --hostname github.com --git-protocol https
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Auth failed. Exiting." -ForegroundColor Red
        pause; exit 1
    }
}

# --- Configure git identity if missing ---
$gitName = git config --global user.name
$gitEmail = git config --global user.email
if (-not $gitName) {
    $gitName = Read-Host "Your name for git commits"
    git config --global user.name "$gitName"
}
if (-not $gitEmail) {
    $gitEmail = Read-Host "Your email for git commits"
    git config --global user.email "$gitEmail"
}

# --- Get repo name + visibility ---
Write-Host ""
Write-Host "[2/5] Repo settings..."
$repoName = Read-Host "Repo name [lead-scraper-toolkit]"
if (-not $repoName) { $repoName = "lead-scraper-toolkit" }

$visChoice = Read-Host "Visibility - (p)ublic or (r)ivate? [p]"
$visibility = if ($visChoice -eq "r") { "--private" } else { "--public" }

# --- Init git if needed ---
Write-Host ""
Write-Host "[3/5] Initializing git..."
if (-not (Test-Path .git)) {
    git init
    git branch -M main
} else {
    Write-Host "  (already a git repo)"
}

# --- Stage + commit ---
Write-Host ""
Write-Host "[4/5] Committing files..."
git add .
# Skip commit if nothing changed
$status = git status --porcelain
if ($status) {
    git commit -m "Initial commit - lead scraper + Overture data kit"
} else {
    Write-Host "  (nothing to commit)"
}

# --- Create repo + push ---
Write-Host ""
Write-Host "[5/5] Creating GitHub repo and pushing..."
$existsRepo = gh repo view $repoName 2>$null
if ($LASTEXITCODE -eq 0) {
    Write-Host "  Repo already exists. Pushing to it..."
    $ghUser = gh api user --jq .login
    git remote remove origin 2>$null
    git remote add origin "https://github.com/$ghUser/$repoName.git"
    git push -u origin main
} else {
    gh repo create $repoName $visibility --source=. --push --remote=origin `
        --description "Lead scraper + Overture Maps data kit for finding businesses that need websites"
}

if ($LASTEXITCODE -eq 0) {
    $ghUser = gh api user --jq .login
    $url = "https://github.com/$ghUser/$repoName"
    Write-Host ""
    Write-Host "===========================================" -ForegroundColor Green
    Write-Host "  DONE" -ForegroundColor Green
    Write-Host "===========================================" -ForegroundColor Green
    Write-Host ""
    Write-Host "Your repo:  $url" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "To clone it on any machine:" -ForegroundColor Gray
    Write-Host "    git clone $url.git" -ForegroundColor Gray
    Write-Host ""
    $open = Read-Host "Open it in your browser now? (y/n)"
    if ($open -eq "y") { Start-Process $url }
} else {
    Write-Host "Something went wrong. Scroll up for the error." -ForegroundColor Red
}
pause
