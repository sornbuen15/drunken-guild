# Sync agents from this repo to %USERPROFILE%\.claude\agents\
# Usage: .\scripts\install\sync_agents.ps1
#
# Requirements: PowerShell 5.1+ or PowerShell Core 7+ (Windows / macOS / Linux)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$ScriptDir       = $PSScriptRoot
$LocalAgentsDir  = Resolve-Path (Join-Path $ScriptDir "..\..\agents")
$GlobalAgentsDir = Join-Path $HOME ".claude\agents"

Write-Host "=================================================" -ForegroundColor Blue
Write-Host "   Claude Agents Synchronizer                   " -ForegroundColor Blue
Write-Host "=================================================" -ForegroundColor Blue

if (-not (Test-Path $LocalAgentsDir)) {
    Write-Host "Error: agents directory not found at $LocalAgentsDir" -ForegroundColor Red
    exit 1
}

New-Item -ItemType Directory -Force -Path $GlobalAgentsDir | Out-Null

Write-Host ""
Write-Host "Source: $LocalAgentsDir"
Write-Host "Target: $GlobalAgentsDir"
Write-Host ""

$NewCount     = 0
$UpdatedCount = 0

# Collect all .md agent files (top-level only), sorted for deterministic output
$AgentFiles = Get-ChildItem -Path $LocalAgentsDir -Filter "*.md" -File |
              Sort-Object Name

foreach ($AgentFile in $AgentFiles) {
    $AgentName  = [System.IO.Path]::GetFileNameWithoutExtension($AgentFile.Name)
    $TargetFile = Join-Path $GlobalAgentsDir "$AgentName.md"
    $IsNew      = -not (Test-Path $TargetFile)

    $ShouldCopy = $true
    if (Test-Path $TargetFile) {
        $SrcHash  = (Get-FileHash $AgentFile.FullName -Algorithm MD5).Hash
        $DestHash = (Get-FileHash $TargetFile         -Algorithm MD5).Hash
        $ShouldCopy = ($SrcHash -ne $DestHash)
    }

    if ($ShouldCopy) {
        Copy-Item -Path $AgentFile.FullName -Destination $TargetFile -Force
    }

    if ($IsNew) {
        Write-Host "  [+] Installed: $AgentName" -ForegroundColor Green
        $NewCount++
    } else {
        Write-Host "  [*] Updated:   $AgentName"
        $UpdatedCount++
    }
}

Write-Host ""
Write-Host "Sync complete." -ForegroundColor Green
Write-Host "  $NewCount new  |  $UpdatedCount updated"
Write-Host "  Agents installed to: $GlobalAgentsDir"
