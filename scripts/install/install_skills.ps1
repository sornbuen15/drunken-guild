# Install skills from this repo to %USERPROFILE%\.claude\skills\
# Usage: .\scripts\install\install_skills.ps1
#
# KNOWN GAP -- this does less than install_skills.sh, and the difference is
# stated rather than hidden. The shell version also accepts --index-only
# to rebuild skills/INDEX.md without installing anything. That is not
# implemented here.
#
# Not an oversight and not a TODO left lying around: --index-only has never
# been run on Windows, and shipping an untested install script that writes to
# a shared config directory is worse than shipping one that does less and
# says so.
#
# The rest of this script is no longer in that position. DG-371 gave the
# project a Windows workstation, and DG-378 is what the first real run found:
# the index this wrote had no slash commands in it at all.
#
# Requirements: PowerShell 5.1+ or PowerShell Core 7+ (Windows / macOS / Linux)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$ScriptDir       = $PSScriptRoot
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

    # Trigger and description for INDEX.md, ported from install_skills.sh
    # (DG-378). What was here before matched nothing at all: `Trigger/Keywords:`
    # and `**Description:**` are the shapes skills used before they carried YAML
    # frontmatter. The first appears in none of the eleven SKILL.md files, so
    # every row this wrote lost its slash command, and `jira-tickets` -- the one
    # skill with no legacy `**Description:**` body line either -- came out blank
    # after the dash.
    #
    # -Encoding UTF8 is not decoration. Windows PowerShell 5.1 reads with the
    # machine's ANSI code page unless told otherwise, and every description here
    # is full of em-dashes; on a machine whose code page is not UTF-8 that puts
    # mojibake into a file that is committed. Same disease as the `cut -c`
    # locale bug in DG-280: output that depends on who ran the generator.
    $Lines = @(Get-Content -LiteralPath $SkillFile.FullName -Encoding UTF8)

    # The slash command must be the one that *follows* "Trigger on". Matching
    # the first `/word` on the line instead published `scrutinize` as `/more`,
    # taken from the phrase "a simpler/more elegant approach" earlier in its own
    # description -- and `prd`, whose description says "brief/requirements/spec",
    # would go the same way. An index that names the wrong command is worse than
    # one that names none: the agent types it and gets nothing.
    $Trigger = ""
    foreach ($Line in $Lines) {
        if ($Line -match 'Trigger/Keywords:') {
            $Rest = $Line
            if ($Line -match '^.*Trigger/Keywords:\*\* (.*)$') { $Rest = $Matches[1] }
            if ($Rest -match '(/[a-zA-Z][a-zA-Z-]+)') { $Trigger = $Matches[1] }
            break
        }
    }
    if (-not $Trigger) {
        foreach ($Line in $Lines) {
            if ($Line -match 'Trigger on `?(/[a-zA-Z][a-zA-Z-]*)') {
                $Trigger = $Matches[1]
                break
            }
        }
    }

    # The description is what an agent reads to decide whether a skill is
    # relevant at all, and CLAUDE.md routes every lookup through this index -- so
    # a blank one makes the skill effectively invisible. Both frontmatter forms
    # are handled, quoted or not: the folded `description: >` block and the
    # inline one. The old `**Description:**` body line stays as a last resort for
    # anything older. This mirrors the awk block in install_skills.sh.
    $Desc = ""
    if ($Lines.Count -gt 0 -and $Lines[0] -eq "---") {
        $InBlock = $false
        for ($i = 1; $i -lt $Lines.Count; $i++) {
            $Line = $Lines[$i]
            if ($Line -eq "---") { break }
            if ($InBlock) {
                if ($Line -match '^\s+\S') {
                    # The awk joins folded lines with `printf "%s "`, so the
                    # description ends in a space. Truncation strips it back off.
                    $Desc += ($Line -replace '^\s+', '') + " "
                    continue
                }
                break
            }
            if ($Line -match '^description:\s*[>|]') { $InBlock = $true; continue }
            if ($Line -match '^description:\s*\S') {
                $Desc = $Line -replace '^description:\s*', ''
                $Desc = $Desc -replace '^"', ''
                $Desc = $Desc -replace '"$', ''
                break
            }
        }
    }
    if (-not $Desc) {
        foreach ($Line in $Lines) {
            if ($Line -match '\*\*Description:\*\*') {
                $Desc = $Line
                if ($Line -match '^.*\*\*Description:\*\* (.*)$') { $Desc = $Matches[1] }
                break
            }
        }
    }
    if (-not $Desc) {
        Write-Host "  [!] $SkillName has no description - it will be invisible in the index." -ForegroundColor Yellow
    }
    $Desc = $Desc.Substring(0, [Math]::Min(160, $Desc.Length)).TrimEnd()

    $HomeSkillPath = "`$HOME/.claude/skills/$SkillName/SKILL.md"
    if ($Trigger) {
        $IndexLines += "- ``$SkillName`` (``$Trigger``) — $Desc"
    } else {
        $IndexLines += "- ``$SkillName`` — $Desc"
    }
    $IndexLines += "  Path: $HomeSkillPath"
    $IndexLines += ""
}

# INDEX.md is generated *and* committed, so what this writes has to be exactly
# what install_skills.sh writes and exactly what survives a commit. Three
# separate things made the Windows output differ from the macOS one byte for
# byte, on a file that is in git:
#
#   - `Set-Content -Encoding UTF8` prepends a BOM on Windows PowerShell 5.1;
#   - it ends every line with CRLF;
#   - every entry above appends a blank line, so the file ended in one, and
#     `end-of-file-fixer` strips it on commit (DG-280 -- a generator whose
#     output the commit hook edits can never produce the file that is in git).
#
# Writing the bytes through .NET settles all three the same way on 5.1 and 7.
$IndexText = ($IndexLines -join "`n").TrimEnd("`n") + "`n"
$Utf8NoBom = New-Object System.Text.UTF8Encoding $false

# Atomic write: write to temp then move
$TempIndex = [System.IO.Path]::GetTempFileName()
[System.IO.File]::WriteAllText($TempIndex, $IndexText, $Utf8NoBom)
Move-Item -Path $TempIndex -Destination $IndexFile -Force

# Mirror local copy for CLAUDE.md skill_routing
$LocalIndex = Join-Path $LocalSkillsDir "INDEX.md"
Copy-Item -Path $IndexFile -Destination $LocalIndex -Force

Write-Host ""
Write-Host "Sync complete." -ForegroundColor Green
Write-Host "  $NewCount new  |  $UpdatedCount updated"
Write-Host "  INDEX.md regenerated: $IndexFile"
Write-Host "  INDEX.md mirrored:    $LocalIndex"
