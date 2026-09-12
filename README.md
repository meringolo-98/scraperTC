# scraperTC

A **scraper**. Not a research assistant, not ChatGPT, not Fable, not Asta.

Those tools answer a question once from a licensed web snapshot. This one keeps hitting public APIs and a real web index, paginates, retries, dedupes, and writes every hit to a local SQLite store you can dump as JSONL. That store is the product.

```
  APIs + Brave ──► Gate 1 scrape ──► SQLite ──► JSONL export
                      (rows)                      optional Gate 2 rank
```

Gate 2 is a deterministic scorer (competition / breakthrough / saturation). It is optional. It is not an LLM.

Target: cannabis tissue culture / remediation lab + genomic prediction for breeders.

## Quick start

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env   # BRAVE_API_KEY is the one that widens the web net

scrapertc run --demo   # offline fixtures, no keys
scrapertc status
scrapertc export --out data/export.jsonl
```

Live scrape:

```bash
scrapertc collect --limit 20
scrapertc collect --only brave,reddit,openalex --limit 20
scrapertc collect --broad --limit 20
scrapertc export --out data/export.jsonl
```

`collect` prints **new** vs **updated**. Same URL seen again increments `hit_count` and `last_seen`; `first_seen` stays put.

Default Gate 1 searches mention phrases (`cannabis_tc`, genomic breeding, cannabis tech) **and** every company in `config/competitors.yaml`. `--broad` also adds generic plant-TC terms (noisier orchids/bananas). Gate 2 keeps the leads.

## Why this beats an LLM browser

| | scraperTC | ChatGPT / Fable / Asta |
| --- | --- | --- |
| Job | Intake: every public hit, stored | Answer: a few citations in a chat |
| Web index | Brave Search API (your key, your quota) | Licensed snapshot, not a bulk dump |
| History | SQLite: first seen, last seen, hit count | Session, then gone |
| Output | JSONL / SQLite | Prose |
| Collect path | No LLM | The product *is* the model |

Do not add a model to Gate 1. If you want a summary, run it yourself on the JSONL.

## API keys

Nothing is required for PubMed, OpenAlex, Crossref, arXiv, news RSS, HN, Bluesky, Stack Exchange, and inbox. Copy `.env.example` to `.env` for the rest.

| Key | Who | What it unlocks |
| --- | --- | --- |
| `BRAVE_API_KEY` | [Brave Search API](https://api-dashboard.search.brave.com/) | The web-wide net: lab pages, LinkedIn via `site:`, patents, blogs. This is the CSE replacement. |
| `YOUTUBE_API_KEY` | [Google Cloud](https://console.cloud.google.com/) → **YouTube Data API v3** | Live YouTube *search*. Channel RSS in `config/sources.yaml` works without it. |
| `GOOGLE_API_KEY` + `GOOGLE_CSE_ID` | Legacy. CSE is closed to new customers; full-web CSE dies 1 Jan 2027. | Same job as Brave. Prefer Brave. |
| `SEMANTIC_SCHOLAR_API_KEY` | [Semantic Scholar](https://www.semanticscholar.org/product/api) | Higher paper-search rate limits. Optional. |
| `REDDIT_CLIENT_ID` + `REDDIT_CLIENT_SECRET` | [Reddit apps](https://www.reddit.com/prefs/apps) (script type) | Use if public Reddit JSON returns 403. Optional. |
| `GITHUB_TOKEN` | GitHub → Settings → Developer settings → PAT | Higher search rate limits. Optional. |
| `CONTACT_EMAIL` | Your email | Not a secret. User-Agent for NCBI / OpenAlex / Crossref. |

`scrapertc status` shows which collectors are waiting on keys.

## Collectors

| Source | What it catches | Keys |
| --- | --- | --- |
| Brave | Independent web index, `site:` scopes, two result pages on unscoped queries | `BRAVE_API_KEY` |
| Reddit | Cannabis + TC subreddit search, two listing pages | Optional OAuth |
| YouTube | Search + optional channel RSS | `YOUTUBE_API_KEY` for search |
| News / RSS | Google News feeds in `config/sources.yaml` | None |
| OpenAlex / PubMed / arXiv / Semantic Scholar / Crossref | Papers and the labs on them; OpenAlex, S2, and Crossref paginate | Optional S2 key |
| Bluesky / Hacker News / Stack Exchange | Public posts and Q&A; HN and Bluesky paginate | None |
| GitHub | Repos and issues | Optional `GITHUB_TOKEN` |
| Google CSE | Legacy web net | `GOOGLE_API_KEY` + `GOOGLE_CSE_ID` |
| Inbox | Manual exports as JSON/JSONL in `data/inbox/` | None |

LinkedIn and other closed networks are not unofficially scraped. Use Brave `site:linkedin.com` or drop exports into `data/inbox/`. Do not scrape google.com HTML.

HTTP: 0.4s pacing, three retries on 429/5xx/transport errors.

## Optional Gate 2

| Segment | Examples |
| --- | --- |
| `cannabis_tc` | meristem, micropropagation, flasking, mother stock |
| `remediation` | HLVd / hop latent viroid, virus-free, clean stock |
| `tc_company` | any plant TC lab, media house, or automation vendor |
| `genomic_prediction` | genomic selection, GBLUP, GWAS, SNP panels, chemotype prediction |
| `cannabis_tech` | CRISPR, sequencing, phenotyping, pathogen diagnostics, automation |
| `adjacent` | related breeding / lab chatter that is not a clean hit |

Each item also gets scores for **competition**, **breakthrough**, and **saturation**, plus **relevance** so orchid-hobby noise does not rank with cannabis meristem.

```bash
scrapertc refine
scrapertc report
scrapertc export --labeled --out data/labeled.jsonl
```

## Config

- `config/keywords.yaml` — live search budget (`priority`) and scholarly queries
- `config/sources.yaml` — collectors, cannabis subreddits, RSS
- `config/competitors.yaml` — TC labs, genomics platforms, media vendors

SQLite lives at `data/chatter.db` (override with `SCRAPERTC_DB`).

## Legal

Use public APIs, respect rate limits, and honor each platform's terms. Research / competitive monitoring of public chatter only — no access-control bypass.
