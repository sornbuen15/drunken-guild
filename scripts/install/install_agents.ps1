# Install agents from this repo to %USERPROFILE%\.claude\agents\
# Usage: .\scripts\install\install_agents.ps1 [-IndexOnly]
#
# -IndexOnly rebuilds the repository's agents/INDEX.md and writes nothing
# else -- not to ~/.claude, not to any target. It is the switch safe for an
# agent: AGENTS.md says an agent does not install, so this is the only mode
# an agent may run unattended. Without it, this script performs a real
# install into the operator's ~/.claude/agents and must not be run by an
# agent (DG-423, the same incident that added -IndexOnly to
# install_skills.ps1).
#
# Requirements: PowerShell 5.1+ or PowerShell Core 7+ (Windows / macOS / Linux)
#
# [CmdletBinding()] is load-bearing, not boilerplate: a "simple" param block
# (no CmdletBinding) lets PowerShell silently swallow a misspelled switch
# (`-IndexOnlyy`) or a stray positional argument, bind $IndexOnly = $false
# either way, and fall straight through to a real install -- the exact
# incident this switch exists to prevent, reproduced against this script
# before the attribute was added: a typo and a stray argument both ran a
# full install, exit 0, nothing refused. CmdletBinding turns both into a
# terminating "parameter cannot be found" / "positional parameter cannot be
# found" error instead.

[CmdletBinding()]
param(
    [switch]$IndexOnly
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$ScriptDir       = $PSScriptRoot
$LocalAgentsDir  = Resolve-Path (Join-Path $ScriptDir "..\..\agents")
$GlobalAgentsDir = Join-Path $HOME ".claude\agents"
$LocalIndex      = Join-Path $LocalAgentsDir "INDEX.md"
$LocalSkillsDir  = Join-Path $ScriptDir "..\..\skills"
$GlobalSkillsDir = Join-Path $HOME ".claude\skills"
$SourcesJson     = Join-Path $LocalAgentsDir "_sources.json"

Write-Host "=================================================" -ForegroundColor Blue
Write-Host "   Claude Agents Synchronizer                   " -ForegroundColor Blue
Write-Host "=================================================" -ForegroundColor Blue

if (-not (Test-Path $LocalAgentsDir)) {
    Write-Host "Error: agents directory not found at $LocalAgentsDir" -ForegroundColor Red
    exit 1
}

# DG-402. agents/<role>.md is generated from skills/roles/<role>/SKILL.md +
# agents/_sources.json (model, tools -- Claude-only concepts no portable skill
# frontmatter should carry). One Python script, shared with install_agents.sh
# rather than re-implemented here, is what keeps this byte-identical to the
# bash output (DG-280/DG-378/DG-380's lesson applied to a new
# generated-and-committed artefact). This writes only inside the repository's
# own agents/ -- never under $GlobalAgentsDir -- so it runs in both
# -IndexOnly and a real install.
if (Test-Path $SourcesJson) {
    $GeneratorScript = Join-Path $ScriptDir "_generate_agents.py"
    & python3 $GeneratorScript $LocalAgentsDir $LocalSkillsDir $SourcesJson
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Error: regenerating agents\*.md from skills\roles\ failed." -ForegroundColor Red
        exit 1
    }
}

# Everything below this point that writes or creates anything outside the
# repository is gated on $IndexOnly being false. $GlobalAgentsDir is the
# target's root and the first thing a real install creates -- -IndexOnly
# never reaches that call.
if ($IndexOnly) {
    Write-Host "  -IndexOnly: rebuilding agents/INDEX.md, installing nothing" -ForegroundColor Yellow
} else {
    New-Item -ItemType Directory -Force -Path $GlobalAgentsDir | Out-Null
}

Write-Host ""
Write-Host "Source: $LocalAgentsDir"
Write-Host "Target: $GlobalAgentsDir"
Write-Host ""

$NewCount        = 0
$UpdatedCount    = 0
$MissingRoleSkill = $false

# DG-402, HIGH review finding. Claude Code skips a subagent's `skills:`
# preload silently when the named skill is not installed -- "If a listed
# skill is missing or disabled ... Claude Code skips it and logs a warning
# to the debug log" (https://code.claude.com/docs/en/subagents) -- so a
# worker/reviewer/manager installed before its role skill would run with
# effectively no role prompt and no visible error at all. Refuse per role
# adapter instead, naming the missing skill and the command to run first.
$RoleSources = $null
if (Test-Path $SourcesJson) {
    $RoleSources = Get-Content -LiteralPath $SourcesJson -Encoding UTF8 -Raw | ConvertFrom-Json
}

# Collect all .md agent files (top-level only), sorted for deterministic output.
# INDEX.md is generated below, not an agent -- it lives in agents/ so the repo
# carries the same index the install does, which means it has to be excluded
# here or the next run would install the index as an extra agent.
$AgentFiles = Get-ChildItem -Path $LocalAgentsDir -Filter "*.md" -File |
              Where-Object { $_.Name -ne "INDEX.md" } |
              Sort-Object Name

# AGENTS.md routes all agent discovery through INDEX.md, so a run that installs
# agents without refreshing it leaves a live dangling reference.
$IndexLines = New-Object System.Collections.Generic.List[string]
$IndexLines.Add("# Agent Index")
$IndexLines.Add("")
$IndexLines.Add("Map a task to the agent that owns it. Read this before delegating $([char]0x2014) do NOT guess agent")
$IndexLines.Add("names or paths from memory.")
$IndexLines.Add("")
$IndexLines.Add("Generated by ``scripts/install/install_agents`` (.sh and .ps1 write identical bytes). Do not")
$IndexLines.Add("edit by hand; edit the agent frontmatter instead.")
$IndexLines.Add("")

foreach ($AgentFile in $AgentFiles) {
    $AgentName  = [System.IO.Path]::GetFileNameWithoutExtension($AgentFile.Name)

    # -IndexOnly never creates, reads or writes anything under
    # $GlobalAgentsDir. That decision only matters for the install messages,
    # which -IndexOnly does not print.
    if (-not $IndexOnly) {
        $RoleSkill = $null
        if ($RoleSources -and ($RoleSources.PSObject.Properties.Name -contains $AgentName)) {
            $RoleSkill = $RoleSources.$AgentName.skill
        }
        if ($RoleSkill) {
            $RoleSkillFile = Join-Path $GlobalSkillsDir "$RoleSkill\SKILL.md"
            if (-not (Test-Path $RoleSkillFile)) {
                Write-Host "  [x] Refusing: $AgentName needs the '$RoleSkill' skill, not installed at $RoleSkillFile" -ForegroundColor Red
                Write-Host "      Run install_skills.ps1 first, then re-run install_agents.ps1." -ForegroundColor Red
                $MissingRoleSkill = $true
                continue
            }
        }

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

    # Checked against DG-378 and clean: unlike install_skills.ps1, this reads
    # the same frontmatter keys install_agents.sh reads -- `^description: ` and
    # `^model: ` -- so it never depended on the pre-frontmatter `**Description:**`
    # body line and never published a blank row. Verified by running it, not by
    # reading it: a sandboxed run on Windows produced all three agents with full
    # descriptions and correct models.
    #
    # That run also surfaced a drift from install_agents.sh -- a BOM, CRLF, a
    # trailing blank line, `-` for the em-dash, a Substring cut that kept the
    # space the shell strips, and its own filename in the header -- so a Windows
    # run and a macOS run rewrote each other's committed agents/INDEX.md. Fixed
    # in DG-380: the em-dash is written as [char]0x2014 so this file stays ASCII
    # for Windows PowerShell 5.1, and the write path is DG-378's.
    #
    # Both may legitimately be absent; Select-Object -First 1 on an empty match
    # yields $null rather than throwing, which is what we want here.
    $Content = Get-Content -LiteralPath $AgentFile.FullName -Encoding UTF8
    $Desc  = ($Content | Where-Object { $_ -match '^description: ' } | Select-Object -First 1)
    $Model = ($Content | Where-Object { $_ -match '^model: ' }       | Select-Object -First 1)
    if ($Desc)  { $Desc  = $Desc  -replace '^description: ', '' } else { $Desc  = "" }
    if ($Model) { $Model = $Model -replace '^model: ', ''       } else { $Model = "" }
    # Same cut as _truncate.py: the first 200 characters, trailing space dropped.
    $Desc = $Desc.Substring(0, [Math]::Min(200, $Desc.Length)).TrimEnd()

    $IndexLines.Add("- ``$AgentName`` (``$Model``) $([char]0x2014) $Desc")
    $IndexLines.Add("  Path: `$HOME/.claude/agents/$AgentName.md")
    $IndexLines.Add("")
}

if ($MissingRoleSkill) {
    Write-Host ""
    Write-Host "Install refused for one or more role adapters -- see above." -ForegroundColor Red
    exit 1
}

# The DG-378 write path, for the same reason: this index is committed, so it
# must be the bytes install_agents.sh writes and a commit accepts -- no BOM, LF,
# and no trailing blank line for end-of-file-fixer to strip.
$IndexText = ($IndexLines -join "`n").TrimEnd("`n") + "`n"
$Utf8NoBom = New-Object System.Text.UTF8Encoding $false

# -IndexOnly writes only the repository's own agents/INDEX.md and returns
# here -- before $GlobalAgentsDir\INDEX.md is ever touched.
if ($IndexOnly) {
    $TempIndex = [System.IO.Path]::GetTempFileName()
    [System.IO.File]::WriteAllText($TempIndex, $IndexText, $Utf8NoBom)
    Move-Item -Path $TempIndex -Destination $LocalIndex -Force

    Write-Host ""
    Write-Host "Done." -ForegroundColor Green -NoNewline
    Write-Host " Rebuilt $LocalIndex. Nothing was installed."
    exit 0
}

$IndexFile = Join-Path $GlobalAgentsDir "INDEX.md"
$TempIndex = [System.IO.Path]::GetTempFileName()
[System.IO.File]::WriteAllText($TempIndex, $IndexText, $Utf8NoBom)
Move-Item -Path $TempIndex -Destination $IndexFile -Force
Copy-Item -Path $IndexFile -Destination $LocalIndex -Force

Write-Host ""
Write-Host "Sync complete." -ForegroundColor Green
Write-Host "  $NewCount new  |  $UpdatedCount updated"
Write-Host "  Agents installed to: $GlobalAgentsDir"
Write-Host "  INDEX.md: $IndexFile"

# Anything installed that this repo does not produce. Reported, never deleted.
$Installed = Get-ChildItem -Path $GlobalAgentsDir -Filter "*.md" -File |
             Where-Object { $_.Name -ne "INDEX.md" } |
             ForEach-Object { [System.IO.Path]::GetFileNameWithoutExtension($_.Name) }
$Ours = $AgentFiles | ForEach-Object { [System.IO.Path]::GetFileNameWithoutExtension($_.Name) }
$Orphans = $Installed | Where-Object { $Ours -notcontains $_ }
if ($Orphans) {
    Write-Host ""
    Write-Host "Installed but not produced here:" -ForegroundColor Yellow
    foreach ($Orphan in $Orphans) { Write-Host "  ~/.claude/agents/$Orphan.md" }
    Write-Host "  Left in place. Add the source to agents/, or remove them yourself."
}
