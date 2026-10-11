#!/bin/bash
set -euo pipefail
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd -- "$SCRIPT_DIR/../.." && pwd)"
PYTHON="$PROJECT_ROOT/src/backend/.venv/bin/python"
if [[ ! -x "$PYTHON" ]]; then
  echo "backend/.venv Python 설치를 확인하세요." >&2
  exit 1
fi
exec "$PYTHON" "$PROJECT_ROOT/scripts/service_control.py" backend stop "$@"
