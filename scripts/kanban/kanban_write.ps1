# Kanban board write interface (Windows / PowerShell)
# Usage:
#   .\scripts\kanban\kanban_write.ps1 create <lane> <NNN> <slug> <content-file>
#   .\scripts\kanban\kanban_write.ps1 move <TASK-ID> <target-lane>
#   .\scripts\kanban\kanban_write.ps1 done <TASK-ID>
#
# Requirements: PowerShell 5.1+ or PowerShell Core 7+

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$BoardDir   = if ($env:KANBAN_BOARD_DIR) { $env:KANBAN_BOARD_DIR } else { ".claude\board" }
$ValidLanes = @("backlog", "todo", "in-progress", "done")

function Show-Usage {
    Write-Host "Usage:"
    Write-Host "  kanban_write.ps1 create <lane> <NNN> <slug> <content-file>"
    Write-Host "  kanban_write.ps1 move <TASK-ID> <target-lane>"
    Write-Host "  kanban_write.ps1 done <TASK-ID>"
    exit 1
}

function Assert-ValidLane($Lane) {
    if ($ValidLanes -notcontains $Lane) {
        Write-Host "Error: '$Lane' is not a valid lane. Valid: $($ValidLanes -join ', ')"
        exit 1
    }
}

function Find-TaskFile($TaskId) {
    foreach ($Lane in $ValidLanes) {
        $LaneDir = Join-Path $BoardDir $Lane
        if (-not (Test-Path $LaneDir)) { continue }
        $Match = Get-ChildItem -Path $LaneDir -Filter "${TaskId}_*.md" -ErrorAction SilentlyContinue |
                 Select-Object -First 1
        if ($Match) { return $Match.FullName }
    }
    return $null
}

$Cmd = if ($args.Count -gt 0) { $args[0] } else { "" }
if (-not $Cmd) { Show-Usage }

switch ($Cmd) {

    "create" {
        if ($args.Count -lt 5) {
            Write-Host "Error: create requires lane, NNN, slug, and content-file"
            Show-Usage
        }
        $Lane        = $args[1]
        $Nnn         = $args[2]
        $Slug        = $args[3]
        $ContentFile = $args[4]

        Assert-ValidLane $Lane

        if (-not (Test-Path $ContentFile)) {
            Write-Host "Error: content file '$ContentFile' not found"
            exit 1
        }

        $Padded    = "{0:D3}" -f ([int]$Nnn)
        $TargetDir = Join-Path $BoardDir $Lane
        New-Item -ItemType Directory -Force -Path $TargetDir | Out-Null
        $Dest = Join-Path $TargetDir "TASK-${Padded}_${Slug}.md"

        if (Test-Path $Dest) {
            Write-Host "Error: $Dest already exists — refusing to overwrite"
            exit 1
        }

        Copy-Item -Path $ContentFile -Destination $Dest
        Write-Host "Created: $Dest"
    }

    "move" {
        if ($args.Count -lt 3) {
            Write-Host "Error: move requires TASK-ID and target-lane"
            Show-Usage
        }
        $TaskId     = $args[1]
        $TargetLane = $args[2]

        Assert-ValidLane $TargetLane

        $Src = Find-TaskFile $TaskId
        if (-not $Src) {
            Write-Host "Error: $TaskId not found in any lane"
            exit 1
        }

        $TargetDir = Join-Path $BoardDir $TargetLane
        New-Item -ItemType Directory -Force -Path $TargetDir | Out-Null
        $Dest = Join-Path $TargetDir (Split-Path -Leaf $Src)

        if ($Src -eq $Dest) {
            Write-Host "Task $TaskId is already in '$TargetLane'"
            exit 0
        }

        Move-Item -Path $Src -Destination $Dest
        Write-Host "Moved: $TaskId -> $TargetLane/"
        Write-Host "File: $Dest"
    }

    "done" {
        $TaskId = if ($args.Count -gt 1) { $args[1] } else { "" }
        if (-not $TaskId) { Write-Host "Error: TASK-ID required"; Show-Usage }

        $Src = Find-TaskFile $TaskId
        if (-not $Src) {
            Write-Host "Error: $TaskId not found in any lane"
            exit 1
        }

        $TargetDir = Join-Path $BoardDir "done"
        New-Item -ItemType Directory -Force -Path $TargetDir | Out-Null
        $Dest = Join-Path $TargetDir (Split-Path -Leaf $Src)
        Move-Item -Path $Src -Destination $Dest
        Write-Host "Done: $TaskId -> done/"
        Write-Host "File: $Dest"
    }

    default {
        Write-Host "Error: unknown command '$Cmd'"
        Show-Usage
    }
}
