#!/usr/bin/env bash
#
# macOS Finder double-click entry point.
# Double-clicking a .command file opens it in Terminal automatically.
# Delegates to the shared shell script.
#
# Usage:
#   ./scripts/start-teacher-console.command [options]

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
exec "${SCRIPT_DIR}/start-teacher-console.sh" "$@"
