#!/bin/bash
# Double-click me (first time: right-click → Open). Sets up FlipFinder on GitHub.
cd "$(dirname "$0")" || exit 1
clear
echo "🚗  FlipFinder setup"
echo
if ! xcode-select -p >/dev/null 2>&1; then
  echo "macOS needs its free developer tools (git + Python). A window will pop up — click Install."
  echo "When it's finished, double-click this file again."
  xcode-select --install 2>/dev/null
  read -r -p "Press Enter to close…"
  exit 1
fi
VENV="$HOME/.flipfinder/venv"
if [ ! -x "$VENV/bin/python" ]; then
  echo "Preparing Python (one-time)…"
  mkdir -p "$HOME/.flipfinder"
  python3 -m venv "$VENV" || { echo "Could not create Python environment"; read -r; exit 1; }
fi
"$VENV/bin/python" -m pip install -q --upgrade pip
"$VENV/bin/python" -m pip install -q -r requirements.txt pynacl || { echo "Package install failed — check your internet and try again."; read -r; exit 1; }
"$VENV/bin/python" scripts/setup_github.py
echo
read -r -p "Press Enter to close…"
