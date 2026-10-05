#!/bin/bash
# Double-click to (re)connect Facebook Marketplace scanning on this Mac.
cd "$(dirname "$0")" || exit 1
clear
VENV="$HOME/.flipfinder/venv"
if [ ! -x "$VENV/bin/python" ]; then
  echo "Run 'Setup FlipFinder' first."
  read -r -p "Press Enter to close…"; exit 1
fi
"$VENV/bin/python" scripts/setup_facebook.py
echo
read -r -p "Press Enter to close…"
