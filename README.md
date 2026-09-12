# scraperTC

Two-gate chatter pickup for a **cannabis tissue culture lab** and a **genomic prediction company for breeders**.

Gate 1 is the wide net. Gate 2 keeps what matters: **cannabis TC / remediation**, **tissue culture companies**, **genomic predictive breeding**, **high-level cannabis tech**, plus adjacent chatter that could still move the business.

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

Live intake:

```bash
scrapertc collect --limit 20
scrapertc collect --broad --limit 20   # every keyword group, Gate 2 still filters
scrapertc refine
scrapertc report
```

Or one shot: `scrapertc run --limit 20` / `scrapertc run --broad --limit 20`.

Default Gate 1 only fires the six `priority` queries in `config/keywords.yaml` (cannabis TC, meristem, HLVd, genomic selection, microprop, predictive breeding). `--broad` also searches the `cannabis_tc`, `genomic_breeding`, `cannabis_tech`, and `tc_companies` lists — more hits, more noise, Gate 2 sorts it.

## API keys

Nothing is required to run. PubMed, OpenAlex, arXiv, news RSS, HN, Bluesky, Stack Exchange, and inbox work with no keys. Copy `.env.example` to `.env` only for the sources below.

| Key | Who | What it unlocks |
| --- | --- | --- |
| `YOUTUBE_API_KEY` | [Google Cloud](https://console.cloud.google.com/) → enable **YouTube Data API v3** | Live YouTube *search*. Channel RSS in `config/sources.yaml` works without it. |
| `GOOGLE_API_KEY` + `GOOGLE_CSE_ID` | Cloud: **Custom Search API**. CSE id: [Programmable Search](https://programmablesearchengine.google.com/) (search the whole web, not just one site) | The “everywhere” net: LinkedIn posts, lab pages, patents, blogs via `site:` scopes. This is the one that actually widens Gate 1 across the open web. Free quota is tight (~100 queries/day). |
| `REDDIT_CLIENT_ID` + `REDDIT_CLIENT_SECRET` | [Reddit apps](https://www.reddit.com/prefs/apps) (script type) | Use if public Reddit JSON starts returning 403. Optional. |
| `GITHUB_TOKEN` | GitHub → Settings → Developer settings → PAT | Higher search rate limits. Optional. |
| `CONTACT_EMAIL` | Your email | Not a secret. Shown in User-Agent for NCBI / OpenAlex politeness. |

`scrapertc status` shows which collectors are waiting on keys.

## What Gate 2 is looking for

| Segment | Examples |
| --- | --- |
| `cannabis_tc` | meristem, micropropagation, flasking, mother stock |
| `remediation` | HLVd / hop latent viroid, virus-free, clean stock |
| `tc_company` | any plant TC lab, media house, or automation vendor |
| `genomic_prediction` | genomic selection, GBLUP, GWAS, SNP panels, chemotype prediction |
| `cannabis_tech` | CRISPR, sequencing, phenotyping, pathogen diagnostics, automation |
| `adjacent` | related breeding / lab chatter that is not a clean hit |

Each item also gets scores for **competition**, **breakthrough**, and **saturation**, plus a **relevance** score so orchid-hobby noise does not rank with cannabis meristem or breeder genomics.

## Collectors

| Source | What it catches | Keys |
| --- | --- | --- |
| Reddit | Cannabis + TC subreddit search | Optional OAuth if Reddit blocks JSON |
| YouTube | Search + optional channel RSS | `YOUTUBE_API_KEY` for search |
| Google CSE | The "everywhere" net, including `site:linkedin.com` | `GOOGLE_API_KEY` + `GOOGLE_CSE_ID` |
| News / RSS | Google News feeds in `config/sources.yaml` | None |
| OpenAlex / PubMed / arXiv | Papers and the labs on them | None (`CONTACT_EMAIL` is polite) |
| Bluesky / Hacker News / Stack Exchange | Public posts and Q&A | None |
| GitHub | Repos and issues | Optional `GITHUB_TOKEN` |
| Inbox | Manual exports as JSON/JSONL in `data/inbox/` | None |

LinkedIn and other closed networks are not unofficially scraped. Use Google CSE `site:` queries or drop exports into `data/inbox/`.

## Config

- `config/keywords.yaml` — live search budget (`priority`) and scholarly queries
- `config/sources.yaml` — collectors, cannabis subreddits, RSS
- `config/competitors.yaml` — TC labs, genomics platforms, media vendors

SQLite lives at `data/chatter.db` (override with `SCRAPERTC_DB`).

## Legal

Use public APIs, respect rate limits, and honor each platform's terms. Research / competitive monitoring of public chatter only — no access-control bypass.
