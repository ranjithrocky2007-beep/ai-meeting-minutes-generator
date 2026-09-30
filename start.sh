#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# start.sh — launch the Meeting Summarizer backend + serve the frontend
# ─────────────────────────────────────────────────────────────────────────────
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Check for ffmpeg (required for video → audio extraction)
if ! command -v ffmpeg &> /dev/null; then
  echo "ERROR: ffmpeg is not installed."
  echo "  macOS:   brew install ffmpeg"
  echo "  Ubuntu:  sudo apt-get install -y ffmpeg"
  exit 1
fi

# Create/activate virtual environment if not already active
if [ -z "$VIRTUAL_ENV" ]; then
  if [ ! -d "$SCRIPT_DIR/.venv" ]; then
    echo "Creating virtual environment…"
    python3 -m venv "$SCRIPT_DIR/.venv"
  fi
  source "$SCRIPT_DIR/.venv/bin/activate"
fi

# Install / upgrade dependencies
echo "Installing dependencies…"
pip install --quiet --upgrade pip
pip install --quiet -r "$SCRIPT_DIR/requirements.txt"

# Launch
echo ""
echo "Starting Meeting Summarizer at http://127.0.0.1:8000"
echo "Press Ctrl+C to stop."
echo ""
cd "$SCRIPT_DIR/backend"
uvicorn main:app --host 127.0.0.1 --port 8000 --reload
