#!/bin/bash
# Kanban board write interface.
# Usage:
#   kanban_write.sh create <lane> <NNN> <slug> <content-file>
#   kanban_write.sh move <TASK-ID> <target-lane>
#   kanban_write.sh done <TASK-ID>

set -euo pipefail

BOARD_DIR="${KANBAN_BOARD_DIR:-.claude/board}"

VALID_LANES="backlog todo in-progress done"

usage() {
  echo "Usage:"
  echo "  $0 create <lane> <NNN> <slug> <content-file>"
  echo "  $0 move <TASK-ID> <target-lane>"
  echo "  $0 done <TASK-ID>"
  exit 1
}

is_valid_lane() {
  local target="$1"
  for lane in $VALID_LANES; do
    [ "$lane" = "$target" ] && return 0
  done
  return 1
}

find_task_file() {
  local task_id="$1"
  for lane in $VALID_LANES; do
    local lane_dir="$BOARD_DIR/$lane"
    [ -d "$lane_dir" ] || continue
    local match
    match=$(find "$lane_dir" -maxdepth 1 -name "${task_id}_*.md" 2>/dev/null | head -1 || true)
    if [ -n "$match" ]; then
      echo "$match"
      return 0
    fi
  done
  return 1
}

cmd="${1:-}"
[ -z "$cmd" ] && usage

case "$cmd" in

  create)
    lane="${2:-}"
    nnn="${3:-}"
    slug="${4:-}"
    content_file="${5:-}"

    [ -z "$lane" ] || [ -z "$nnn" ] || [ -z "$slug" ] || [ -z "$content_file" ] && {
      echo "Error: create requires lane, NNN, slug, and content-file"
      usage
    }

    is_valid_lane "$lane" || {
      echo "Error: '$lane' is not a valid lane. Valid lanes: $VALID_LANES"
      exit 1
    }

    [ -f "$content_file" ] || {
      echo "Error: content file '$content_file' not found"
      exit 1
    }

    padded=$(printf "%03d" "$((10#$nnn))")
    target_dir="$BOARD_DIR/$lane"
    mkdir -p "$target_dir"
    dest="$target_dir/TASK-${padded}_${slug}.md"

    if [ -f "$dest" ]; then
      echo "Error: $dest already exists — refusing to overwrite"
      exit 1
    fi

    cp "$content_file" "$dest"
    echo "Created: $dest"
    ;;

  move)
    task_id="${2:-}"
    target_lane="${3:-}"

    [ -z "$task_id" ] || [ -z "$target_lane" ] && {
      echo "Error: move requires TASK-ID and target-lane"
      usage
    }

    is_valid_lane "$target_lane" || {
      echo "Error: '$target_lane' is not a valid lane. Valid lanes: $VALID_LANES"
      exit 1
    }

    src=$(find_task_file "$task_id") || {
      echo "Error: $task_id not found in any lane"
      exit 1
    }

    target_dir="$BOARD_DIR/$target_lane"
    mkdir -p "$target_dir"
    dest="$target_dir/$(basename "$src")"

    if [ "$src" = "$dest" ]; then
      echo "Task $task_id is already in '$target_lane'"
      exit 0
    fi

    mv "$src" "$dest"
    echo "Moved: $task_id → $target_lane/"
    echo "File: $dest"
    ;;

  done)
    task_id="${2:-}"
    [ -z "$task_id" ] && { echo "Error: TASK-ID required"; usage; }

    src=$(find_task_file "$task_id") || {
      echo "Error: $task_id not found in any lane"
      exit 1
    }

    target_dir="$BOARD_DIR/done"
    mkdir -p "$target_dir"
    dest="$target_dir/$(basename "$src")"
    mv "$src" "$dest"
    echo "Done: $task_id → done/"
    echo "File: $dest"
    ;;

  *)
    echo "Error: unknown command '$cmd'"
    usage
    ;;
esac
