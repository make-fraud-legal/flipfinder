#!/bin/bash
# Quick check that every site still parses (1 page each). Nothing is sent anywhere.
cd "$(dirname "$0")" || exit 1
clear
VENV="$HOME/.flipfinder/venv"
[ -x "$VENV/bin/python" ] || { mkdir -p "$HOME/.flipfinder"; python3 -m venv "$VENV"; "$VENV/bin/python" -m pip install -q -r requirements.txt; }
"$VENV/bin/python" -m flipfinder selftest
echo
read -r -p "Press Enter to close…"
