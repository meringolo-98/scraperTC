# scraperTC

Two-gate chatter pickup for **tissue culture**.

Gate 1 is the wide net: social posts, YouTube, LinkedIn-visible pages, news, papers, labs, GitHub, and anything else a public API or inbox drop can see. Gate 2 is the refinement pass: **competition**, **breakthroughs**, and **saturation**.

```
  sources ──► Gate 1 collect ──► SQLite ──► Gate 2 refine ──► reports
                 (chatter)                    (scores)
```

## Quick start

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env   # optional keys

scrapertc run --demo   # offline, no keys
scrapertc status
```

Open `data/reports/latest.html` after a run.

Live intake (whatever public endpoints allow without keys):

```bash
scrapertc collect --limit 20
scrapertc refine
scrapertc report
```

Or one shot: `scrapertc run --limit 20`.

## Collectors

| Source | What it catches | Keys |
| --- | --- | --- |
| Reddit | Subreddit + search chatter | Optional OAuth if Reddit blocks JSON |
| YouTube | Search + optional channel RSS | `YOUTUBE_API_KEY` for search |
| Google CSE | The "everywhere" net, including `site:linkedin.com`, `.edu` labs, patents, blogs | `GOOGLE_API_KEY` + `GOOGLE_CSE_ID` |
| News / RSS | Google News and feeds in `config/sources.yaml` | None |
| OpenAlex / PubMed / arXiv | Papers and the labs on them | None (`CONTACT_EMAIL` is polite) |
| Bluesky / Hacker News / Stack Exchange | Public posts and Q&A | None |
| GitHub | Repos and issues (protocols, lab tooling) | Optional `GITHUB_TOKEN` |
| Inbox | Manual exports as JSON/JSONL in `data/inbox/` | None |

LinkedIn, Instagram, TikTok, and Facebook are not unofficially scraped. Point Google Programmable Search at those hosts, or drop exported posts into `data/inbox/`.

Inbox JSONL shape:

```json
{"source":"linkedin","url":"https://...","title":"...","body":"...","author":"...","published_at":"2026-09-01T00:00:00Z"}
```

## Gate 2

Each item gets:

- `domain`: plant / mammalian / mixed / unknown
- scores `0–1` for competition, breakthrough, saturation
- entity hits from `config/competitors.yaml`
- `off-domain` when it is clearly mammalian cell culture

Tune phrases and competitor names in `config/` rather than hard-coding them in collectors.

## Config

- `config/keywords.yaml` — search terms and CSE site scopes
- `config/sources.yaml` — enable/disable collectors, subreddits, RSS feeds
- `config/competitors.yaml` — brands, labs, aliases

SQLite lives at `data/chatter.db` (override with `SCRAPERTC_DB`).

## Legal

Use public APIs, respect rate limits, and honor each platform's terms. This tool is for research / competitive monitoring of public chatter, not for bypassing access controls.
