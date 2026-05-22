# Education Newsletter

Automated daily + weekly newsletter on four themes:

1. AI's impact on education
2. Innovation in education
3. Visual and performing arts in education
4. Human flourishing in education

Pipeline: GitHub Actions cron → fetch RSS feeds → **Gemini 2.5 Flash** scores stories (free tier) → top 3-6 get **Claude Sonnet 4.6**-written summaries → SMTP delivers to your inbox. Sunday weekly job adds the week's daily picks plus bonus stories from a wider net.

Cost: ~$0.50-1/month (Sonnet only writes 6-14 short summaries/day; Gemini ranking is free). Free everywhere else (GitHub Actions free tier, Gmail SMTP).

## Setup (~15 minutes)

### 1. Push this to a new GitHub repo
```bash
cd ai-education-news
git init && git add . && git commit -m "init"
gh repo create ai-education-news --private --source=. --push
```
(Or use the web UI to create a private repo and push.)

### 2. Get a Gemini API key (free, no card)
aistudio.google.com → "Get API key" → Create. Save it.

### 3. Get an Anthropic API key
console.anthropic.com → API Keys → Create. Save it.

### 4. Set up Gmail SMTP (easiest option)
- Google Account → Security → make sure 2-Step Verification is on
- Then → Search "App passwords" → create one named "Newsletter"
- You'll get a 16-character password. Save it.

### 5. Add secrets to the repo
Repo → Settings → Secrets and variables → Actions → New repository secret. Add:

| Secret | Value |
|---|---|
| `GEMINI_API_KEY` | from step 2 |
| `ANTHROPIC_API_KEY` | from step 3 |
| `SMTP_HOST` | `smtp.gmail.com` |
| `SMTP_PORT` | `587` |
| `SMTP_USER` | your Gmail address |
| `SMTP_PASS` | app password from step 4 |
| `TO_EMAIL` | where to receive (probably same as SMTP_USER) |
| `FROM_EMAIL` | optional; defaults to SMTP_USER |

### 6. Enable workflow write permissions
Repo → Settings → Actions → General → Workflow permissions → "Read and write permissions" → Save. (Needed so the daily job can commit `data/seen.json` back.)

### 7. First run
Repo → Actions → Daily Newsletter → "Run workflow". Check your inbox in ~30 seconds.

## Tweaking it

| What | Where |
|---|---|
| Add/remove RSS feeds | `sources.py` → `FEEDS` |
| Adjust theme definitions | `sources.py` → `THEMES` |
| Change number of stories | `newsletter.py` → `DAILY_TARGET`, `BONUS_TARGET` |
| Raise/lower the relevance bar | `newsletter.py` → `DAILY_MIN_SCORE` (out of 20) |
| Change tone of summaries | `newsletter.py` → `summarize_articles` prompt |
| Change schedule | `.github/workflows/*.yml` → cron line |

## Local testing
```bash
pip install -r requirements.txt
export GEMINI_API_KEY=...
export ANTHROPIC_API_KEY=...
export SMTP_HOST=smtp.gmail.com SMTP_PORT=587
export SMTP_USER=... SMTP_PASS=... TO_EMAIL=...
python newsletter.py daily
```

## Architecture notes
- **Hybrid LLM setup**: Gemini 2.5 Flash ranks (free tier, generous limits), Claude Sonnet 4.6 writes summaries (paid, voice matters here). To go fully free: swap WRITER_MODEL to `gemini-2.5-flash` and route summaries through `gemini_client` too. To go fully paid: swap RANKER_MODEL back to `claude-haiku-4-5-20251001`.
- **Deduplication**: `data/seen.json` tracks URLs Claude has already evaluated; pruned to 45 days.
- **Daily archive**: `data/daily_archive.json` stores the past 14 days of picks so the weekly job has source material.
- **Empty days**: if nothing crosses the relevance threshold, no email goes out (rather than sending filler).
- **Cost control**: Gemini does the bulk scoring (free); Sonnet only writes summaries for the 6-14 stories per day that pass the bar (~$0.50-1/month).
- **Privacy note**: Gemini free tier may use API inputs for model training. Article titles + snippets from public RSS feeds flow through the ranker — no sensitive data, but worth knowing.
