"""FlipFinder one-time setup (run via 'Setup FlipFinder.command' on your Mac).

Creates your GitHub repo, uploads the bot, turns on the free dashboard (GitHub Pages),
stores your Telegram bot as a hidden secret and starts the first scan.
Tokens you paste are typed by YOU into this terminal; they're only sent to GitHub/Telegram
and kept in ~/.flipfinder/env (readable only by your user) for the Facebook scanner."""
from __future__ import annotations

import base64
import getpass
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import webbrowser

import requests

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOME = os.path.expanduser("~/.flipfinder")
API = "https://api.github.com"
SKIP = {".git", "state", "site", "demo_site", "demo_state", "__pycache__", ".venv", ".DS_Store", ".pytest_cache"}

B, G, Y, R, X = "\033[1m", "\033[32m", "\033[33m", "\033[31m", "\033[0m"


def say(msg=""):
    print(msg, flush=True)


def ask(prompt, default=None):
    v = input(f"{prompt}{f' [{default}]' if default else ''}: ").strip()
    return v or (default or "")


def yes(prompt, default=True):
    v = input(f"{prompt} ({'Y/n' if default else 'y/N'}): ").strip().lower()
    return default if not v else v.startswith("y")


def save_env(updates: dict):
    os.makedirs(HOME, exist_ok=True)
    p = os.path.join(HOME, "env")
    cur = {}
    if os.path.exists(p):
        for line in open(p):
            if "=" in line:
                k, v = line.strip().split("=", 1)
                cur[k] = v
    cur.update({k: v for k, v in updates.items() if v})
    with open(p, "w") as f:
        for k, v in cur.items():
            f.write(f"{k}={v}\n")
    os.chmod(p, 0o600)
    return cur


def load_env():
    p = os.path.join(HOME, "env")
    out = {}
    if os.path.exists(p):
        for line in open(p):
            if "=" in line:
                k, v = line.strip().split("=", 1)
                out[k] = v
    return out


class GH:
    def __init__(self, token):
        self.s = requests.Session()
        self.s.headers.update({"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json",
                               "X-GitHub-Api-Version": "2022-11-28"})
        self.token = token

    def req(self, method, path, **kw):
        r = self.s.request(method, API + path, timeout=30, **kw)
        return r


def step(n, title):
    say(f"\n{B}[{n}] {title}{X}")


def main():
    say(f"{B}🚗  FlipFinder setup{X}\nThis takes ~5 minutes. You can re-run it any time.\n")
    env = load_env()

    # ---------------------------------------------------------------- 1. GitHub login
    step(1, "Connect your GitHub account")
    token = env.get("GITHUB_TOKEN")
    gh = None
    if token:
        gh = GH(token)
        if gh.req("GET", "/user").status_code != 200:
            token = None
    if not token:
        say("No GitHub account yet? Create one free at https://github.com/signup first.\n")
        say("A page will open to create an access token for FlipFinder:")
        say("  • Note: FlipFinder   • Expiration: 'No expiration' (or 1 year)")
        say("  • Scopes 'repo' and 'workflow' are pre-ticked → scroll down → Generate token → copy it")
        input("Press Enter to open the page… ")
        webbrowser.open("https://github.com/settings/tokens/new?scopes=repo,workflow&description=FlipFinder")
        while True:
            token = getpass.getpass("Paste the token here (it stays hidden): ").strip()
            gh = GH(token)
            r = gh.req("GET", "/user")
            if r.status_code == 200:
                break
            say(f"{R}That token didn't work ({r.status_code}). Try again.{X}")
    user = gh.req("GET", "/user").json()["login"]
    say(f"{G}✓ Signed in as {user}{X}")

    # ---------------------------------------------------------------- 2. repo
    step(2, "Create the repository")
    name = env.get("GITHUB_REPO", "").split("/")[-1] or "flipfinder"
    name = ask("Repository name", name)
    repo = f"{user}/{name}"
    r = gh.req("GET", f"/repos/{repo}")
    remote_config = None
    if r.status_code == 200:
        say(f"Repo {repo} already exists — I'll update the code and keep your config.yaml.")
        c = gh.req("GET", f"/repos/{repo}/contents/config.yaml")
        if c.status_code == 200:
            remote_config = base64.b64decode(c.json()["content"])
    else:
        r = gh.req("POST", "/user/repos", json={"name": name, "private": False, "has_issues": False,
                                                "has_wiki": False, "description": "FlipFinder — car flip & deal finder (ss.lv + EU)"})
        if r.status_code not in (200, 201):
            say(f"{R}Couldn't create the repo: {r.status_code} {r.text[:300]}{X}")
            sys.exit(1)
        say(f"{G}✓ Created https://github.com/{repo} (public — it only holds code and public listing data){X}")
    save_env({"GITHUB_TOKEN": token, "GITHUB_REPO": repo})

    # ---------------------------------------------------------------- 3. upload code
    step(3, "Upload FlipFinder")
    tmp = tempfile.mkdtemp()
    dst = os.path.join(tmp, "repo")
    shutil.copytree(ROOT, dst, ignore=lambda d, names: [n for n in names if n in SKIP or n.endswith(".pyc")])
    if remote_config:
        with open(os.path.join(dst, "config.yaml"), "wb") as f:
            f.write(remote_config)
    # the GitHub Actions schedule lives in deploy/scan.yml locally (macOS tools hide .github folders)
    wf = os.path.join(dst, ".github", "workflows")
    os.makedirs(wf, exist_ok=True)
    if os.path.exists(os.path.join(dst, "deploy", "scan.yml")):
        shutil.copy(os.path.join(dst, "deploy", "scan.yml"), os.path.join(wf, "scan.yml"))
    auth = base64.b64encode(f"x-access-token:{token}".encode()).decode()
    git = ["git", "-C", dst, "-c", "user.name=" + user, "-c", f"user.email={user}@users.noreply.github.com"]
    subprocess.run(["git", "-C", dst, "init", "-q", "-b", "main"], check=True)
    subprocess.run(git + ["add", "-A"], check=True)
    subprocess.run(git + ["commit", "-qm", "FlipFinder"], check=True)
    p = subprocess.run(["git", "-C", dst, "-c", f"http.extraHeader=Authorization: Basic {auth}", "push", "-qf",
                        f"https://github.com/{repo}.git", "main"], capture_output=True, text=True)
    if p.returncode != 0:
        say(f"{R}Upload failed: {p.stderr[-400:]}{X}")
        sys.exit(1)
    shutil.rmtree(tmp, ignore_errors=True)
    say(f"{G}✓ Code uploaded{X}")

    # ---------------------------------------------------------------- 4. pages
    step(4, "Turn on the dashboard (GitHub Pages)")
    r = gh.req("POST", f"/repos/{repo}/pages", json={"build_type": "workflow"})
    if r.status_code == 409:
        r = gh.req("PUT", f"/repos/{repo}/pages", json={"build_type": "workflow"})
    if r.status_code in (200, 201, 204, 409):
        say(f"{G}✓ Dashboard enabled{X}")
    else:
        say(f"{Y}! Couldn't enable Pages automatically ({r.status_code}). In the repo: Settings → Pages → Source: GitHub Actions.{X}")
    dash = f"https://{user.lower()}.github.io/{name}/"

    # ---------------------------------------------------------------- 5. telegram
    step(5, "Telegram alerts")
    tg_token, chat = env.get("TELEGRAM_BOT_TOKEN"), env.get("TELEGRAM_CHAT_ID")
    if yes("Set up Telegram pings now?", True):
        say("In Telegram: open @BotFather → send /newbot → pick any name and a username ending in 'bot'.")
        say("BotFather replies with a token like 123456789:AAH… — copy it.")
        webbrowser.open("https://t.me/BotFather")
        while True:
            tg_token = getpass.getpass("Paste the bot token (hidden): ").strip()
            me = requests.get(f"https://api.telegram.org/bot{tg_token}/getMe", timeout=20).json()
            if me.get("ok"):
                break
            say(f"{R}Telegram didn't accept that token, try again.{X}")
        bot = me["result"]["username"]
        say(f"Now open your bot and press Start (or send it any message): https://t.me/{bot}")
        webbrowser.open(f"https://t.me/{bot}")
        input("Press Enter after you've sent the message… ")
        chat = None
        for _ in range(10):
            ups = requests.get(f"https://api.telegram.org/bot{tg_token}/getUpdates", timeout=20).json().get("result", [])
            for u in reversed(ups):
                m = u.get("message") or u.get("my_chat_member") or {}
                if m.get("chat", {}).get("id"):
                    chat = str(m["chat"]["id"])
                    break
            if chat:
                break
            time.sleep(3)
        if not chat:
            say(f"{R}Didn't see your message. Run setup again later to finish Telegram.{X}")
        else:
            requests.post(f"https://api.telegram.org/bot{tg_token}/sendMessage",
                          json={"chat_id": chat, "text": "👋 FlipFinder connected. Deals will land here."}, timeout=20)
            ok = set_secrets(gh, repo, {"TELEGRAM_BOT_TOKEN": tg_token, "TELEGRAM_CHAT_ID": chat})
            if ok:
                say(f"{G}✓ Telegram connected (check your chat for a test message){X}")
            else:
                say(f"{Y}! Add 2 secrets by hand: repo → Settings → Secrets and variables → Actions → New secret:\n"
                    f"   TELEGRAM_BOT_TOKEN = (your bot token)\n   TELEGRAM_CHAT_ID = {chat}{X}")
            save_env({"TELEGRAM_BOT_TOKEN": tg_token, "TELEGRAM_CHAT_ID": chat})

    # ---------------------------------------------------------------- 6. first run
    step(6, "Start the first scan")
    time.sleep(3)
    r = gh.req("POST", f"/repos/{repo}/actions/workflows/scan.yml/dispatches", json={"ref": "main", "inputs": {}})
    if r.status_code == 204:
        say(f"{G}✓ First scan started. It reads every car ad on ss.lv first, so it takes ~20-30 min.{X}")
    else:
        say(f"{Y}! Start it by hand: https://github.com/{repo}/actions → scan → Run workflow ({r.status_code}){X}")
    say(f"\n{B}Your dashboard:{X} {dash}   (live after the first scan finishes)")
    say(f"{B}Scan progress:{X} https://github.com/{repo}/actions")
    say(f"{B}Settings:{X}      https://github.com/{repo}/blob/main/config.yaml  (pencil icon to edit)")
    save_env({"DASHBOARD_URL": dash})

    # ---------------------------------------------------------------- 7. facebook
    say("")
    if yes("Set up Facebook Marketplace scanning on this Mac too?", True):
        subprocess.run([sys.executable, os.path.join(ROOT, "scripts", "setup_facebook.py")])
    say(f"\n{G}{B}All done.{X} FlipFinder now runs by itself every 2 hours.")


def set_secrets(gh: GH, repo: str, secrets: dict) -> bool:
    try:
        from nacl import encoding, public
    except ImportError:
        return False
    k = gh.req("GET", f"/repos/{repo}/actions/secrets/public-key")
    if k.status_code != 200:
        return False
    key = k.json()
    pk = public.PublicKey(key["key"].encode(), encoding.Base64Encoder())
    box = public.SealedBox(pk)
    for name, value in secrets.items():
        enc = base64.b64encode(box.encrypt(value.encode())).decode()
        r = gh.req("PUT", f"/repos/{repo}/actions/secrets/{name}", json={"encrypted_value": enc, "key_id": key["key_id"]})
        if r.status_code not in (201, 204):
            return False
    return True


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        say("\nCancelled.")
