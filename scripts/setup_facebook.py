"""Facebook Marketplace scanner for your Mac.

Installs a private browser for FlipFinder, lets you log in to Facebook once, then adds a
background job (macOS launchd) that scans Marketplace every 3 hours while the Mac is awake
and sends the results to your GitHub repo. Remove it any time with:
    launchctl bootout gui/$(id -u)/com.flipfinder.fb ; rm ~/Library/LaunchAgents/com.flipfinder.fb.plist
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOME = os.path.expanduser("~/.flipfinder")
APP = os.path.join(HOME, "app")          # copy outside Documents/Desktop so launchd can read it
PLIST = os.path.expanduser("~/Library/LaunchAgents/com.flipfinder.fb.plist")
B, G, Y, R, X = "\033[1m", "\033[32m", "\033[33m", "\033[31m", "\033[0m"


def run(cmd, **kw):
    print("  $", " ".join(cmd[:4]), "…" if len(cmd) > 4 else "", flush=True)
    return subprocess.run(cmd, **kw)


def main():
    py = sys.executable
    print(f"{B}Facebook Marketplace scanner{X}")
    print("1/4 Installing the browser engine (one-time, ~150 MB)…")
    run([py, "-m", "pip", "install", "-q", "playwright"], check=True)
    run([py, "-m", "playwright", "install", "chromium"], check=True)

    print("2/4 Copying FlipFinder to ~/.flipfinder/app …")
    if os.path.exists(APP):
        shutil.rmtree(APP)
    shutil.copytree(ROOT, APP, ignore=shutil.ignore_patterns(".git", "state", "site", "demo_*", "__pycache__", "tests"))

    print(f"3/4 Log in to Facebook. {Y}Use your normal account; FlipFinder only reads Marketplace listings.{X}")
    run([py, "-m", "flipfinder", "fb-login"], cwd=APP, check=True)

    print("4/4 Scheduling a scan every 3 hours…")
    log = os.path.join(HOME, "fb.log")
    plist = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>com.flipfinder.fb</string>
  <key>ProgramArguments</key><array><string>{py}</string><string>-m</string><string>flipfinder</string><string>fb-scan</string></array>
  <key>WorkingDirectory</key><string>{APP}</string>
  <key>StartInterval</key><integer>10800</integer>
  <key>RunAtLoad</key><true/>
  <key>StandardOutPath</key><string>{log}</string>
  <key>StandardErrorPath</key><string>{log}</string>
</dict></plist>
"""
    os.makedirs(os.path.dirname(PLIST), exist_ok=True)
    uid = os.getuid()
    subprocess.run(["launchctl", "bootout", f"gui/{uid}/com.flipfinder.fb"], capture_output=True)
    with open(PLIST, "w") as f:
        f.write(plist)
    r = subprocess.run(["launchctl", "bootstrap", f"gui/{uid}", PLIST], capture_output=True, text=True)
    if r.returncode != 0:
        subprocess.run(["launchctl", "load", "-w", PLIST])
    print(f"{G}✓ Facebook scanner is running now and every 3 hours. Log: {log}{X}")
    print("  (If Facebook logs you out later, run 'Setup Facebook Scanner' again.)")


if __name__ == "__main__":
    main()
