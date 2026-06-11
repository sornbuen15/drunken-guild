#!/bin/bash
# Kanban board read interface.
# Usage:
#   kanban_read.sh next-id
#   kanban_read.sh list <lane>
#   kanban_read.sh list-all
#   kanban_read.sh get <TASK-ID>

set -euo pipefail

BOARD_DIR="${KANBAN_BOARD_DIR:-.claude/board}"

VALID_LANES="backlog todo in-progress done"

usage() {
  echo "Usage:"
  echo "  $0 next-id"
  echo "  $0 list <backlog|todo|in-progress|done>"
  echo "  $0 list-all"
  echo "  $0 get <TASK-ID>"
  exit 1
}

cmd="${1:-}"
[ -z "$cmd" ] && usage

case "$cmd" in

  next-id)
    # Find the highest existing TASK-NNN across all lanes, increment by 1.
    max=0
    for lane in $VALID_LANES; do
      lane_dir="$BOARD_DIR/$lane"
      [ -d "$lane_dir" ] || continue
      while IFS= read -r f; do
        [ -z "$f" ] && continue
        num=$(basename "$f" | grep -oE 'TASK-[0-9]+' | grep -oE '[0-9]+' | head -1 || true)
        [ -z "$num" ] && continue
        # Strip leading zeros for arithmetic
        num=$((10#$num))
        [ "$num" -gt "$max" ] && max=$num
      done < <(find "$lane_dir" -maxdepth 1 -name "TASK-*.md" 2>/dev/null)
    done
    printf "%03d\n" $((max + 1))
    ;;

  list)
    lane="${2:-}"
    [ -z "$lane" ] && { echo "Error: lane required for 'list'"; usage; }
    lane_dir="$BOARD_DIR/$lane"
    if [ ! -d "$lane_dir" ]; then
      echo "Lane '$lane' does not exist at $lane_dir"
      exit 1
    fi
    task_count=0
    while IFS= read -r f; do
      [ -z "$f" ] && continue
      id=$(grep -m1 "^id:" "$f" 2>/dev/null | awk '{print $2}' || true)
      title=$(grep -m1 "^title:" "$f" 2>/dev/null | sed 's/^title: //' || true)
      priority=$(grep -m1 "^priority:" "$f" 2>/dev/null | awk '{print $2}' || true)
      assigned=$(grep -m1 "^assigned_to:" "$f" 2>/dev/null | awk '{print $2}' || true)
      printf "%-12s %-8s %-20s %s\n" "${id:-?}" "${priority:-?}" "${assigned:-?}" "${title:-$(basename "$f")}"
      task_count=$((task_count + 1))
    done < <(find "$lane_dir" -maxdepth 1 -name "TASK-*.md" 2>/dev/null | sort)
    [ "$task_count" -eq 0 ] && echo "(empty)"
    ;;

  list-all)
    for lane in $VALID_LANES; do
      lane_dir="$BOARD_DIR/$lane"
      [ -d "$lane_dir" ] || continue
      count=$(find "$lane_dir" -maxdepth 1 -name "TASK-*.md" 2>/dev/null | wc -l | tr -d ' ')
      echo "=== $lane ($count) ==="
      "$0" list "$lane" || true
      echo ""
    done
    ;;

  get)
    task_id="${2:-}"
    [ -z "$task_id" ] && { echo "Error: TASK-ID required for 'get'"; usage; }
    found=""
    for lane in $VALID_LANES; do
      lane_dir="$BOARD_DIR/$lane"
      [ -d "$lane_dir" ] || continue
      match=$(find "$lane_dir" -maxdepth 1 -name "${task_id}_*.md" 2>/dev/null | head -1 || true)
      if [ -n "$match" ]; then
        found="$match"
        break
      fi
    done
    if [ -z "$found" ]; then
      echo "Error: $task_id not found in any lane"
      exit 1
    fi
    echo "File: $found"
    echo "---"
    cat "$found"
    ;;

  *)
    echo "Error: unknown command '$cmd'"
    usage
    ;;
esac
