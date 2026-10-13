# CardHunt (phone-first)

Standalone Pokemon card hunter. **No tissue-culture scrape setup required.**

Find cards on eBay / TCG / PriceCharting / etc, skim grade defects from photos, and flag steals (e.g. 1st-edition Charizard listed as plain base).

## On your phone (easiest)

### Option A — UI on phone, engine on any computer

1. On a computer (or Termux box) with this repo:

```bash
pip install -e .
cardhunt serve
```

2. Note the machine’s LAN IP (`ipconfig` / `ifconfig` / router list).
3. On your phone (same Wi‑Fi), open:

`http://THAT_IP:8787/`

4. Tap **Try demo** (works with zero API keys) or type a card and **Hunt**.

Add to home screen from the browser for an app-like icon.

### Option B — everything on the phone (Termux)

```bash
pkg install python git
git clone <this-repo>
cd scraperTC
pip install -e .
cardhunt demo          # offline proof
cardhunt serve --host 127.0.0.1 --port 8787
```

Then open `http://127.0.0.1:8787/` in the Termux browser / Chrome.

## Live marketplace hunt

Copy `.env.example` → `.env` and set at least:

```bash
BRAVE_API_KEY=...          # marketplace site: search (shared-friendly)
# optional:
EBAY_APP_ID=...
POKEMONTCG_API_KEY=...
CARDHUNT_DB=data/cardhunt.db
```

```bash
cardhunt hunt "Charizard Base 4/102 1st edition"
cardhunt serve
```

Tune watchlist / floors / sites in `config/cards.yaml`.

## What the buttons do

| Control | Action |
| --- | --- |
| **Hunt** | Live search (Brave market scopes + Pokemon TCG API when keys exist) |
| **Try demo** | Offline fixtures including a steal example |
| **Steals** | Mislisted / underpriced valuable variants |
| Grade cues | Centering / whitening heuristics when listing images are available |

This is a from-scratch phone product (`cardhunt`). The older `scrapertc cards …` CLI remains if you also use the TC pipeline on a main PC.
