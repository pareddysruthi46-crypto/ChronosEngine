#!/usr/bin/env bash
set -Eeuo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_ROOT"

echo "========================================"
echo " ChronosEngine - Evaluation Demo"
echo "========================================"

# The dashboard uses Python curses, which requires a Unix-like environment.
case "$(uname -s)" in
    Linux*|Darwin*)
        ;;
    *)
        echo "ERROR: Run this demo in Linux, macOS, or WSL."
        echo "Native Windows PowerShell and Git Bash are not supported."
        exit 1
        ;;
esac

# Locate Python.
PYTHON_BIN="${PYTHON_BIN:-python3}"
if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
    PYTHON_BIN="python"
fi

if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
    echo "ERROR: Python 3 is not installed or not on PATH."
    exit 1
fi

"$PYTHON_BIN" -c '
import sys
if sys.version_info < (3, 10):
    raise SystemExit("Python 3.10 or newer is required.")
print("Python:", sys.version.split()[0])
'

# Use a persistent virtual environment outside the repository.
VENV_DIR="${CHRONOS_VENV:-"$HOME/.venvs/chronosengine-demo"}"

if [[ ! -x "$VENV_DIR/bin/python" ]]; then
    echo "Creating virtual environment: $VENV_DIR"
    mkdir -p "$(dirname "$VENV_DIR")"
    "$PYTHON_BIN" -m venv "$VENV_DIR"
fi

# Activate the demo environment.
source "$VENV_DIR/bin/activate"
PYTHON_BIN="$VENV_DIR/bin/python"

# Check required build and runtime dependencies.
if ! "$PYTHON_BIN" -c "import Cython, setuptools, psutil" >/dev/null 2>&1; then
    echo "Installing required Python packages..."
    "$PYTHON_BIN" -m pip install --upgrade pip setuptools wheel Cython "psutil>=7.0.0"
fi

# Verify the terminal dashboard dependency.
if ! "$PYTHON_BIN" -c "import curses" >/dev/null 2>&1; then
    echo "ERROR: Python curses support is unavailable."
    echo "Use a Python build with curses support in Linux or WSL."
    exit 1
fi

# Verify that a C++ compiler is available for the Cython extension.
if ! command -v c++ >/dev/null 2>&1 &&
   ! command -v g++ >/dev/null 2>&1 &&
   ! command -v clang++ >/dev/null 2>&1; then
    echo "ERROR: No C++ compiler found."
    echo "Install a C++ build toolchain and run this script again."
    exit 1
fi

# Compile the matching engine extension before starting the pipeline.
echo
echo "[1/2] Building Cython matching engine..."
"$PYTHON_BIN" setup.py build_ext --inplace

# Keep demo database output outside the Git repository.
DATABASE_PATH="${CHRONOS_DATABASE:-"$HOME/.local/state/chronosengine/demo_trade_ledger.db"}"
mkdir -p "$(dirname "$DATABASE_PATH")"

echo
echo "[2/2] Starting the integrated pipeline and dashboard..."
echo "Database: $DATABASE_PATH"
echo "Press Q inside the dashboard to stop the demo."
echo

export PYTHONPATH="$PROJECT_ROOT${PYTHONPATH:+:$PYTHONPATH}"

exec "$PYTHON_BIN" -m chronosengine.production_dashboard \
    --database "$DATABASE_PATH" \
    "$@"