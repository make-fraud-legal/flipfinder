# FlipFinder 🚗💰

Finds cars that are cheaper abroad than in Latvia, underpriced ads on ss.lv, good matches
for your own next car, and cheap items from your ss.lv watchlists — then pings you on Telegram.
Runs by itself on GitHub's free servers every 2 hours. No Claude credits, no computer needed.

**What it scans**

| Where | What for |
|---|---|
| **ss.lv** — every car ad, once a day + new ads every run | Latvian market price for every model/year/km/fuel |
| sauto.cz, bazos.cz 🇨🇿 · otomoto.pl 🇵🇱 · autoplius.lt 🇱🇹 · auto24 🇪🇪🇱🇻 · autoscout24 🇩🇪 | Newest listings, compared with LV prices |
| Facebook Marketplace (Riga, Vilnius, Kaunas, Tallinn, Warsaw, Prague, Berlin) | Runs on your Mac because Marketplace needs your login |
| ss.lv item categories you choose (phones, laptops, consoles…) | Ads well under the usual price |

**For every car it shows**
- Estimated LV value (statistical model built from all ss.lv ads of that model)
- Real profit after transport, CSDD registration (~€210), history report, recon buffer and a realistic sale discount
- Reliability: known problems for that model/engine/gearbox and whether they're **due at this mileage** (e.g. "N47 timing chain from ~120k km, €1,200–2,500"), plus red-flag words in the ad in 8 languages ("Motorschaden", "po wypadku", "uz detaļām", "на запчасти"…)

---

## Setup (about 5 minutes)

1. Make a free GitHub account at <https://github.com/signup> if you don't have one.
2. In this folder, **right-click `Setup FlipFinder.command` → Open** (first time macOS asks; after that double-click works).
3. Follow the prompts. It will:
   - open GitHub so you can create an access token (just click *Generate token* and paste it back),
   - create a **public** repo called `flipfinder` and upload the bot,
   - turn on your dashboard at `https://<your-github-name>.github.io/flipfinder/`,
   - connect Telegram: you create a bot with @BotFather (30 seconds), paste its token, press *Start* on it,
   - start the first scan (≈20–30 min, because it reads every car ad on ss.lv first),
   - optionally set up the Facebook scanner on this Mac.

Tokens are typed by you into the Terminal window; the Telegram token is stored as an encrypted GitHub secret.

> Why public? Public repos get unlimited free GitHub Actions minutes and a free website.
> The repo only contains code and public listing data — your tokens are hidden secrets.

## Everyday use

- **Telegram** pings you for: 🔥 import flips · 💎 underpriced LV ads · 🚗 matches for your own car · 🛍 watchlist items · 📉 price drops.
- **Dashboard** (bookmark it on your phone): *Import flips*, *Local steals*, *My car*, *Items*, *LV market* (median prices, price-by-year curves, how fast models sell), *Car research* (problems by model and engine).
- **Change settings**: open `config.yaml` in your GitHub repo → pencil ✏️ → edit → *Commit changes*. Budget, costs per country, alert thresholds, your car criteria, Facebook cities and item watchlists are all there.
- **Run a scan now**: repo → *Actions* → *scan* → *Run workflow*.

## Facebook Marketplace

Marketplace only shows listings to logged-in users, and logging in from GitHub's servers would get
your account flagged. So FlipFinder scans it from your Mac:

- `Setup Facebook Scanner.command` installs a private browser, you log in once, and a background job
  scans every 3 hours while the Mac is awake. Results go to the dashboard and Telegram like everything else.
- It only *reads* Marketplace pages at a human pace (no messages, no clicks on listings). Automated use is
  against Facebook's terms, so there's a small risk to the account — use it at your own discretion.
- Logged out? Run `Setup Facebook Scanner.command` again.
- Turn it off: `launchctl bootout gui/$(id -u)/com.flipfinder.fb`

## If a site stops working

Click the **sources** pill (top right of the dashboard). A red dot = that site failed last run.
- Some sites block cloud servers. Add them to `mac_sources:` in `config.yaml` (e.g. `[autoplius_lt]`)
  and they'll be scanned from your Mac together with Facebook.
- Sites change their layout sometimes. Double-click `Test scrapers on this Mac.command` to see which
  parser broke, and ask Claude to fix it.

## How the numbers work

- **LV value**: for each model family (e.g. *VW Golf*) a robust regression on all ss.lv ads:
  `log(price) ~ age + age² + km + fuel`, outliers and damaged/for-parts ads removed. Confidence is
  *high* with 40+ ads and a tight fit, *low* when extrapolating (unusual year/km).
- **Profit** = LV value × (1 − sale discount) − price − transport − registration − history check − recon.
  Defaults: transport LT €200, EE €250, PL €450, CZ €650, DE €700. Edit them in `config.yaml`.
- Asking prices aren't selling prices, and every estimate is rough. Always do a history report
  (carVertical/autoDNA) and a pre-purchase inspection before paying.

## Files

```
config.yaml                  ← your settings
flipfinder/sources/          ← one scraper per site
flipfinder/pricing.py        ← LV market value model
flipfinder/reliability.py    ← known-issues engine; data in flipfinder/data/reliability.json
flipfinder/deals.py          ← profit / risk / scoring
flipfinder/scan.py           ← one full run
flipfinder/fb_runner.py      ← Facebook scanner (Mac)
web/index.html               ← the dashboard
deploy/scan.yml              ← the 2-hour schedule (setup puts it in .github/workflows/)
tests/                       ← parser tests (python tests/test_parsers.py)
```
