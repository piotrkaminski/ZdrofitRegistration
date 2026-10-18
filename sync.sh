#!/usr/bin/env bash
set -e

# Resolve project directory regardless of current working directory
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
cd "$SCRIPT_DIR"

PYTHON_BIN="$SCRIPT_DIR/.venv/bin/python3"

# Ensure virtual environment and dependencies exist
if [ ! -f "$PYTHON_BIN" ]; then
    echo "[!] Nie znaleziono środowiska wirtualnego .venv. Tworzenie i instalowanie pakietów..."
    python3 -m venv "$SCRIPT_DIR/.venv"
    "$SCRIPT_DIR/.venv/bin/pip" install --upgrade pip
    "$SCRIPT_DIR/.venv/bin/pip" install -r "$SCRIPT_DIR/requirements.txt"
fi

# Ensure log directory exists
mkdir -p "$SCRIPT_DIR/logs"

# Determine arguments: default to --sync if no action flag is specified
HAS_ACTION=false
for arg in "$@"; do
    if [[ "$arg" == "--sync" || "$arg" == "--auto" || "$arg" == "--login" || "$arg" == "--list" || "$arg" == "--schedule-help" || "$arg" == "--now" ]]; then
        HAS_ACTION=true
        break
    fi
done

if [ "$HAS_ACTION" = false ]; then
    CLI_ARGS=("--sync" "$@")
else
    CLI_ARGS=("$@")
fi

# Run with caffeinate to prevent Mac from sleeping during execution or countdown
exec /usr/bin/caffeinate -i "$PYTHON_BIN" "$SCRIPT_DIR/register.py" "${CLI_ARGS[@]}"
