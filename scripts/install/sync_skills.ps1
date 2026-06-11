# Sync skills from this repo to %USERPROFILE%\.claude\skills\
# Usage: .\scripts\install\sync_skills.ps1
#
# Requirements: PowerShell 5.1+ or PowerShell Core 7+ (Windows / macOS / Linux)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$ScriptDir       = Split-Path -Parent $MyInvocation.MyCommand.Path
$LocalSkillsDir  = Resolve-Path (Join-Path $ScriptDir "..\..\skills")
$GlobalSkillsDir = Join-Path $HOME ".claude\skills"
$IndexFile       = Join-Path $GlobalSkillsDir "INDEX.md"

Write-Host "=================================================" -ForegroundColor Blue
Write-Host "   Claude Agentic Skills Synchronizer           " -ForegroundColor Blue
Write-Host "=================================================" -ForegroundColor Blue

if (-not (Test-Path $LocalSkillsDir)) {
    Write-Host "Error: skills directory not found at $LocalSkillsDir" -ForegroundColor Red
    exit 1
}

New-Item -ItemType Directory -Force -Path $GlobalSkillsDir | Out-Null

Write-Host ""
Write-Host "Source: $LocalSkillsDir"
Write-Host "Target: $GlobalSkillsDir"
Write-Host ""

$NewCount     = 0
$UpdatedCount = 0

# Collect all SKILL.md files, sorted for deterministic index order
$SkillFiles = Get-ChildItem -Path $LocalSkillsDir -Filter "SKILL.md" -Recurse |
              Sort-Object FullName

# Build index content in memory; write atomically at the end
$IndexLines = @(
    "# Skill Index",
    "",
    "Map task keywords to their absolute skill file paths. Load ONLY the relevant skill before executing.",
    ""
)

foreach ($SkillFile in $SkillFiles) {
    $SkillDir  = $SkillFile.DirectoryName
    $SkillName = Split-Path -Leaf $SkillDir

    if ($SkillName -eq "skills") { continue }

    $TargetDir = Join-Path $GlobalSkillsDir $SkillName
    $IsNew     = -not (Test-Path $TargetDir)

    New-Item -ItemType Directory -Force -Path $TargetDir | Out-Null

    # Copy files, skipping identical ones (checksum comparison)
    $SrcFiles = Get-ChildItem -Path $SkillDir -Recurse -File
    foreach ($SrcFile in $SrcFiles) {
        $Relative = $SrcFile.FullName.Substring($SkillDir.Length).TrimStart('\', '/')
        $DestPath = Join-Path $TargetDir $Relative
        $DestDir  = Split-Path -Parent $DestPath

        New-Item -ItemType Directory -Force -Path $DestDir | Out-Null

        $ShouldCopy = $true
        if (Test-Path $DestPath) {
            $SrcHash  = (Get-FileHash $SrcFile.FullName -Algorithm MD5).Hash
            $DestHash = (Get-FileHash $DestPath         -Algorithm MD5).Hash
            $ShouldCopy = ($SrcHash -ne $DestHash)
        }

        if ($ShouldCopy) {
            Copy-Item -Path $SrcFile.FullName -Destination $DestPath -Force
        }
    }

    if ($IsNew) {
        Write-Host "  [+] Installed: $SkillName" -ForegroundColor Green
        $NewCount++
    } else {
        Write-Host "  [*] Updated:   $SkillName"
        $UpdatedCount++
    }

    # Extract trigger command and description for INDEX
    $Content = Get-Content $SkillFile.FullName -Raw
    $Trigger = ""
    if ($Content -match "Trigger/Keywords:\*\*\s*(.+)") {
        $TriggerLine = $Matches[1]
        if ($TriggerLine -match "(/[a-zA-Z][a-zA-Z-]+)") {
            $Trigger = $Matches[1]
        }
    }
    $Desc = ""
    if ($Content -match "\*\*Description:\*\*\s*(.+)") {
        $Desc = $Matches[1].Substring(0, [Math]::Min(80, $Matches[1].Length))
    }

    $HomeSkillPath = "`$HOME/.claude/skills/$SkillName/SKILL.md"
    if ($Trigger) {
        $IndexLines += "- ``$SkillName`` (``$Trigger``) — $Desc"
    } else {
        $IndexLines += "- ``$SkillName`` — $Desc"
    }
    $IndexLines += "  Path: $HomeSkillPath"
    $IndexLines += ""
}

# Atomic write: write to temp then move
$TempIndex = [System.IO.Path]::GetTempFileName()
$IndexLines | Set-Content -Path $TempIndex -Encoding UTF8
Move-Item -Path $TempIndex -Destination $IndexFile -Force

# Mirror local copy for CLAUDE.md skill_routing
$LocalIndex = Join-Path $LocalSkillsDir "INDEX.md"
Copy-Item -Path $IndexFile -Destination $LocalIndex -Force

Write-Host ""
Write-Host "Sync complete." -ForegroundColor Green
Write-Host "  $NewCount new  |  $UpdatedCount updated"
Write-Host "  INDEX.md regenerated: $IndexFile"
Write-Host "  INDEX.md mirrored:    $LocalIndex"
