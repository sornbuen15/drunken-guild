# Kanban board read interface (Windows / PowerShell)
# Usage:
#   .\scripts\kanban\kanban_read.ps1 next-id
#   .\scripts\kanban\kanban_read.ps1 list <lane>
#   .\scripts\kanban\kanban_read.ps1 list-all
#   .\scripts\kanban\kanban_read.ps1 get <TASK-ID>
#
# Requirements: PowerShell 5.1+ or PowerShell Core 7+

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$BoardDir    = if ($env:KANBAN_BOARD_DIR) { $env:KANBAN_BOARD_DIR } else { ".claude\board" }
$ValidLanes  = @("backlog", "todo", "in-progress", "done")

function Show-Usage {
    Write-Host "Usage:"
    Write-Host "  kanban_read.ps1 next-id"
    Write-Host "  kanban_read.ps1 list <backlog|todo|in-progress|done>"
    Write-Host "  kanban_read.ps1 list-all"
    Write-Host "  kanban_read.ps1 get <TASK-ID>"
    exit 1
}

function Get-FrontmatterField($FilePath, $Field) {
    $Lines = Get-Content $FilePath
    foreach ($Line in $Lines) {
        if ($Line -match "^${Field}:\s*(.+)") {
            return $Matches[1].Trim()
        }
    }
    return "?"
}

$Cmd = if ($args.Count -gt 0) { $args[0] } else { "" }
if (-not $Cmd) { Show-Usage }

switch ($Cmd) {

    "next-id" {
        $Max = 0
        foreach ($Lane in $ValidLanes) {
            $LaneDir = Join-Path $BoardDir $Lane
            if (-not (Test-Path $LaneDir)) { continue }
            $TaskFiles = Get-ChildItem -Path $LaneDir -Filter "TASK-*.md" -ErrorAction SilentlyContinue
            foreach ($File in $TaskFiles) {
                if ($File.Name -match "TASK-(\d+)") {
                    $Num = [int]$Matches[1]
                    if ($Num -gt $Max) { $Max = $Num }
                }
            }
        }
        "{0:D3}" -f ($Max + 1)
    }

    "list" {
        $Lane = if ($args.Count -gt 1) { $args[1] } else { "" }
        if (-not $Lane) { Write-Host "Error: lane required for 'list'"; Show-Usage }
        $LaneDir = Join-Path $BoardDir $Lane
        if (-not (Test-Path $LaneDir)) {
            Write-Host "Lane '$Lane' does not exist at $LaneDir"
            exit 1
        }
        $Files = Get-ChildItem -Path $LaneDir -Filter "TASK-*.md" -ErrorAction SilentlyContinue |
                 Sort-Object Name
        if ($Files.Count -eq 0) {
            Write-Host "(empty)"
        } else {
            foreach ($File in $Files) {
                $Id       = Get-FrontmatterField $File.FullName "id"
                $Title    = Get-FrontmatterField $File.FullName "title"
                $Priority = Get-FrontmatterField $File.FullName "priority"
                $Assigned = Get-FrontmatterField $File.FullName "assigned_to"
                "{0,-12} {1,-8} {2,-20} {3}" -f $Id, $Priority, $Assigned, $Title
            }
        }
    }

    "list-all" {
        foreach ($Lane in $ValidLanes) {
            $LaneDir = Join-Path $BoardDir $Lane
            if (-not (Test-Path $LaneDir)) { continue }
            $Count = (Get-ChildItem -Path $LaneDir -Filter "TASK-*.md" -ErrorAction SilentlyContinue).Count
            Write-Host "=== $Lane ($Count) ==="
            & $MyInvocation.MyCommand.Path "list" $Lane
            Write-Host ""
        }
    }

    "get" {
        $TaskId = if ($args.Count -gt 1) { $args[1] } else { "" }
        if (-not $TaskId) { Write-Host "Error: TASK-ID required for 'get'"; Show-Usage }

        $Found = $null
        foreach ($Lane in $ValidLanes) {
            $LaneDir = Join-Path $BoardDir $Lane
            if (-not (Test-Path $LaneDir)) { continue }
            $Match = Get-ChildItem -Path $LaneDir -Filter "${TaskId}_*.md" -ErrorAction SilentlyContinue |
                     Select-Object -First 1
            if ($Match) { $Found = $Match; break }
        }

        if (-not $Found) {
            Write-Host "Error: $TaskId not found in any lane"
            exit 1
        }

        Write-Host "File: $($Found.FullName)"
        Write-Host "---"
        Get-Content $Found.FullName
    }

    default {
        Write-Host "Error: unknown command '$Cmd'"
        Show-Usage
    }
}
