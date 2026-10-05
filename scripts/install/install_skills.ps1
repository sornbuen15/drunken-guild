# Install skills from this repo to %USERPROFILE%\.claude\skills\
# Usage: .\scripts\install\install_skills.ps1 [-IndexOnly] [-Prune [-PruneApply]]
#
# -Prune / -PruneApply are DG-359's half of install_skills.sh's fix, kept
# consistent across both installers. This script copied skills in and
# removed nothing -- an install left retired skill directories installed
# beside the ones this repository ships, and nothing ever reported them on
# Windows at all. Removal is opt-in, dry-run by default, and -- after review
# finding #1 -- restricted to names this repository actually knows are
# retired:
#   (no switch)              -- unchanged: nothing reported, nothing removed
#   -Prune                    -- list what -PruneApply would remove, remove nothing
#   -Prune -PruneApply        -- remove ONLY orphans listed on
#                                scripts/install/retired_skills.txt; anything
#                                else unshipped is reported "unrecognised" and
#                                never removed -- an unshipped directory is
#                                not proof it is safe to delete. The first cut
#                                of this feature pruned any orphan and deleted
#                                a hand-written, never-shipped skill.
# -PruneApply alone (without -Prune) is refused. A reparse point (symlink or
# junction) is never followed or removed, listed or applied: its Attributes
# are checked before every Remove-Item (review finding #2).
#
# -IndexOnly rebuilds the repository's skills/INDEX.md and writes nothing
# else -- not to ~/.claude, not to any target. It is the switch safe for an
# agent: AGENTS.md says an agent does not install, so this is the only mode
# an agent may run unattended. Without it, this script performs a real
# install into the operator's ~/.claude/skills and must not be run by an
# agent (DG-423 -- an agent on Windows ran this without the switch, because
# it did not exist yet, and overwrote the Boss's ~/.claude/skills with
# unmerged branch content).
#
# DG-371 gave the project a Windows workstation, and DG-378 is what the
# first real run found: the index this wrote had no slash commands in it at
# all.
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
    [switch]$IndexOnly,
    [switch]$Prune,
    [switch]$PruneApply
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# DG-450. A read-only, one-level-at-a-time walk that stops at the first
# reparse point it finds rather than descending into it. `Get-ChildItem
# -Recurse` is not used here on purpose: on Windows PowerShell 5.1 it follows
# a directory symlink or a junction straight into its target, which is the
# very hazard a scan for a nested link exists to catch rather than trigger.
# Returns the first nested reparse point's full path, or $null.
function Find-NestedReparsePoint {
    param([Parameter(Mandatory)][string]$Directory)

    $pending = [System.Collections.Generic.Queue[string]]::new()
    $pending.Enqueue($Directory)
    while ($pending.Count -gt 0) {
        $current = $pending.Dequeue()
        foreach ($child in Get-ChildItem -LiteralPath $current -Force) {
            if ($child.Attributes -band [System.IO.FileAttributes]::ReparsePoint) {
                return $child.FullName
            }
            if ($child.PSIsContainer) {
                $pending.Enqueue($child.FullName)
            }
        }
    }
    return $null
}

if ($IndexOnly -and ($Prune -or $PruneApply)) {
    Write-Host "-IndexOnly writes nothing outside the repo; it has nothing to prune." -ForegroundColor Red
    exit 1
}
if ($PruneApply -and -not $Prune) {
    Write-Host "-PruneApply requires -Prune: list what would be removed first." -ForegroundColor Red
    exit 1
}

# An empty or unset $HOME must refuse outright, not resolve to a path
# relative to wherever the process happens to be -- that is how a run could
# touch an unintended tree instead of failing loudly (DG-359 review finding
# #3). PowerShell's own $HOME falls back to $env:USERPROFILE when unset, so
# both are checked explicitly.
if ([string]::IsNullOrWhiteSpace($HOME) -and [string]::IsNullOrWhiteSpace($env:USERPROFILE)) {
    Write-Host "`$HOME and `$env:USERPROFILE are both empty or unset. Refusing to guess an install target." -ForegroundColor Red
    exit 1
}

$ScriptDir       = $PSScriptRoot
$ProjectRoot     = Resolve-Path (Join-Path $ScriptDir "..\..")
$LocalSkillsDir  = Resolve-Path (Join-Path $ScriptDir "..\..\skills")
$GlobalSkillsDir = Join-Path $HOME ".claude\skills"
$IndexFile       = Join-Path $GlobalSkillsDir "INDEX.md"
$LocalIndex      = Join-Path $LocalSkillsDir "INDEX.md"
$ExternalFile    = Join-Path $LocalSkillsDir ".external"
$RetiredFile     = Join-Path $ScriptDir "retired_skills.txt"
$ExtrasDir       = Join-Path $ProjectRoot "plugins\drunken-extras\skills"

Write-Host "=================================================" -ForegroundColor Blue
Write-Host "   Claude Agentic Skills Synchronizer           " -ForegroundColor Blue
Write-Host "=================================================" -ForegroundColor Blue

if (-not (Test-Path $LocalSkillsDir)) {
    Write-Host "Error: skills directory not found at $LocalSkillsDir" -ForegroundColor Red
    exit 1
}

# Everything below this point that writes or creates anything outside the
# repository is gated on $IndexOnly being false. $GlobalSkillsDir is the
# target's root and the first thing a real install creates -- -IndexOnly
# never reaches that call.
if ($IndexOnly) {
    Write-Host "  -IndexOnly: rebuilding skills/INDEX.md, installing nothing" -ForegroundColor Yellow
} else {
    New-Item -ItemType Directory -Force -Path $GlobalSkillsDir | Out-Null
}

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

    # -IndexOnly never creates, reads or writes anything under
    # $GlobalSkillsDir -- not even the Test-Path below that decides whether a
    # skill is "new". That decision only matters for the install messages,
    # which -IndexOnly does not print.
    if (-not $IndexOnly) {
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
    # relevant at all, and AGENTS.md routes every lookup through this index -- so
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

# -IndexOnly writes only the repository's own skills/INDEX.md and returns
# here -- before $IndexFile (under $GlobalSkillsDir) is ever touched.
if ($IndexOnly) {
    $TempIndex = [System.IO.Path]::GetTempFileName()
    [System.IO.File]::WriteAllText($TempIndex, $IndexText, $Utf8NoBom)
    Move-Item -Path $TempIndex -Destination $LocalIndex -Force

    Write-Host ""
    Write-Host "Done." -ForegroundColor Green -NoNewline
    Write-Host " Rebuilt $LocalIndex. Nothing was installed."
    exit 0
}

# Atomic write: write to temp then move
$TempIndex = [System.IO.Path]::GetTempFileName()
[System.IO.File]::WriteAllText($TempIndex, $IndexText, $Utf8NoBom)
Move-Item -Path $TempIndex -Destination $IndexFile -Force

# Mirror local copy for AGENTS.md skill_routing
Copy-Item -Path $IndexFile -Destination $LocalIndex -Force

Write-Host ""
Write-Host "Sync complete." -ForegroundColor Green
Write-Host "  $NewCount new  |  $UpdatedCount updated"
Write-Host "  INDEX.md regenerated: $IndexFile"
Write-Host "  INDEX.md mirrored:    $LocalIndex"

# Anything installed that this repo does not produce. Reported, never deleted
# unless it is on $RetiredFile and -PruneApply is the operator's own choice --
# DG-359, ported from install_skills.sh so the two installers agree about
# both what "installed but not ours" means and what is actually safe to
# remove (review finding #1: "not ours" is not the same claim as "retired").
$Ours = @($SkillFiles | ForEach-Object { Split-Path -Leaf $_.DirectoryName })
$External = @()
if (Test-Path $ExternalFile) {
    $External = @(
        Get-Content -LiteralPath $ExternalFile -Encoding UTF8 |
            Where-Object { $_ -match '\S' -and $_ -notmatch '^\s*#' } |
            ForEach-Object { $_.Trim() }
    )
}
$Known = @($Ours + $External)

# Names on $RetiredFile that are shipped today under
# plugins/drunken-extras/skills/ are shipped, not retired -- the list is not
# proof against drift either, and "currently shipped elsewhere" must win
# over "on the retired list", the same rule doctor's `_check_ai_layer` and
# install_skills.sh apply.
$RetiredListed = @()
if (Test-Path $RetiredFile) {
    $RetiredListed = @(
        Get-Content -LiteralPath $RetiredFile -Encoding UTF8 |
            ForEach-Object { $_.TrimEnd("`r") } |
            Where-Object { $_ -match '\S' -and $_ -notmatch '^\s*#' } |
            ForEach-Object { $_.Trim() }
    )
}
$Extras = @()
if (Test-Path $ExtrasDir) {
    $Extras = @(
        Get-ChildItem -Path $ExtrasDir -Filter "SKILL.md" -Recurse |
            ForEach-Object { Split-Path -Leaf $_.DirectoryName }
    )
}
$Retired = @($RetiredListed | Where-Object { $Extras -notcontains $_ })

$Installed = @(
    Get-ChildItem -Path $GlobalSkillsDir -Directory |
        Where-Object { Test-Path (Join-Path $_.FullName "SKILL.md") } |
        ForEach-Object { $_.Name }
)
$Orphans = @($Installed | Where-Object { $Known -notcontains $_ } | Sort-Object)

if ($Orphans.Count -gt 0) {
    Write-Host ""
    $RetiredOrphans      = @($Orphans | Where-Object { $Retired -contains $_ })
    $UnrecognisedOrphans = @($Orphans | Where-Object { $Retired -notcontains $_ })

    if ($Prune) {
        if ($PruneApply) {
            Write-Host "Removing (-PruneApply) -- retired, on ${RetiredFile}:" -ForegroundColor Yellow
        } else {
            Write-Host "Would remove (-Prune, dry run) -- retired, on ${RetiredFile}:" -ForegroundColor Yellow
        }
        if ($RetiredOrphans.Count -gt 0) {
            foreach ($name in $RetiredOrphans) {
                $target = Join-Path $GlobalSkillsDir $name
                # Never follow or remove a link. A reparse point covers both
                # a symlink and a Windows junction -- `Remove-Item -Recurse`
                # on one has a history of recursing into the TARGET's
                # contents rather than removing the link itself (review
                # finding #2).
                $item = Get-Item -LiteralPath $target -Force
                if ($item.Attributes -band [System.IO.FileAttributes]::ReparsePoint) {
                    Write-Host "  $target (link, not touched)"
                    continue
                }

                # A read-only scan, one level at a time, never `-Recurse`:
                # that one call follows a reparse point into its target on
                # Windows PowerShell 5.1 (the hazard this scan exists to
                # avoid), and on PowerShell Core it skips the target's
                # contents but still requires a pass to notice the link was
                # there at all. Walking manually means every directory is
                # listed before it is ever descended into, and a reparse
                # point found along the way stops that branch of the walk
                # rather than being pushed onto it -- its target is never
                # read, recursed into, or removed. A nested link means the
                # whole retired directory is reported and left alone, on
                # both the preview and the apply run.
                $nestedLink = Find-NestedReparsePoint -Directory $target
                if ($nestedLink) {
                    $relative = $nestedLink.Substring($target.Length).TrimStart('\', '/')
                    Write-Host "  $target (nested link at $relative, skipped -- never recursed into or removed)" -ForegroundColor Yellow
                    continue
                }

                # The preview and the apply run both name what they are about
                # to remove whole: a retired directory holding only the
                # SKILL.md this repository shipped is one thing, and one a
                # user dropped their own notes or subfolders into is
                # another -- the old output said just "$target" either way
                # and removed both the same, silently, on -PruneApply.
                $topEntries = @(Get-ChildItem -LiteralPath $target -Force)
                $totalFiles = @(Get-ChildItem -LiteralPath $target -Recurse -Force -File).Count
                if ($topEntries.Count -eq 1 -and $topEntries[0].Name -eq "SKILL.md" -and -not $topEntries[0].PSIsContainer) {
                    Write-Host "  $target ($totalFiles file)"
                } else {
                    Write-Host "  $target ($totalFiles files -- holds more than SKILL.md)"
                }
                if ($PruneApply) {
                    Remove-Item -LiteralPath $target -Recurse -Force
                }
            }
        } else {
            Write-Host "  (none)"
        }
        if ($PruneApply) {
            Write-Host "  Removed. The operator chose -PruneApply; nothing here decided on its own."
        } else {
            Write-Host "  Nothing removed. Re-run with -Prune -PruneApply to remove these."
        }
        if ($UnrecognisedOrphans.Count -gt 0) {
            Write-Host ""
            Write-Host "Unrecognised, never pruned automatically:" -ForegroundColor Yellow
            foreach ($name in $UnrecognisedOrphans) {
                Write-Host "  $(Join-Path $GlobalSkillsDir $name)"
            }
            Write-Host "  Add to skills/.external if it is yours, or to $RetiredFile if it is retired."
        }
    } else {
        Write-Host "Installed but not produced here:" -ForegroundColor Yellow
        foreach ($name in $Orphans) {
            Write-Host "  $(Join-Path $GlobalSkillsDir $name)"
        }
        Write-Host "  Left in place. Add to skills/.external if intended. -Prune lists what -Prune -PruneApply would remove -- only names on $RetiredFile, never anything else."
    }
}

# A name on $RetiredFile is not guaranteed to be a directory at all: it might
# be a plain file (an operator's own note, or a leftover from a manual edit)
# sharing the name of something this repository once shipped. $Installed
# above only ever looks for a directory holding SKILL.md, so a plain file
# here was previously invisible to every list this script prints -- never
# counted as installed, never reported as an orphan, never reaching this far
# at all. It is reported, on every -Prune run, independently of $Orphans, and
# never touched: a plain file is not a skill directory, so nothing here
# decides what it is safe to do with it.
if ($Prune) {
    $RetiredFiles = @(
        $Retired | Where-Object {
            $p = Join-Path $GlobalSkillsDir $_
            if (-not (Test-Path -LiteralPath $p)) { return $false }
            $i = Get-Item -LiteralPath $p -Force
            (-not $i.PSIsContainer) -and -not ($i.Attributes -band [System.IO.FileAttributes]::ReparsePoint)
        }
    )
    if ($RetiredFiles.Count -gt 0) {
        Write-Host ""
        Write-Host "Retired name on disk as a plain file:" -ForegroundColor Yellow
        foreach ($name in $RetiredFiles) {
            Write-Host "  $(Join-Path $GlobalSkillsDir $name) (not a skill directory, left alone)"
        }
    }
}
