"""
Daily + weekly education newsletter.

Usage:
    python newsletter.py daily
    python newsletter.py weekly

Environment variables required:
    ANTHROPIC_API_KEY
    SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS, TO_EMAIL
    FROM_EMAIL (optional, defaults to SMTP_USER)
"""

import argparse
import json
import os
import re
import smtplib
import time
from datetime import datetime, timedelta, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

import anthropic
import feedparser
from google import genai

from sources import FEEDS, THEMES, PRIORITIZE, DEPRIORITIZE

DATA_DIR = Path("data")
SEEN_FILE = DATA_DIR / "seen.json"
ARCHIVE_FILE = DATA_DIR / "daily_archive.json"

RANKER_MODEL = "gemini-2.5-flash"        # Google free tier: 10 RPM, 250 RPD
WRITER_MODEL = "claude-sonnet-4-6"       # Anthropic paid; voice matters here

DAILY_TARGET = 6        # max stories in the daily
DAILY_MIN_SCORE = 11    # min (relevance + importance) to be picked, out of 20
BONUS_TARGET = 8        # max bonus stories in the weekly
MAX_RANK_CANDIDATES = 80  # cap candidates sent to ranker per call

anthropic_client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY
gemini_client = genai.Client()            # reads GEMINI_API_KEY or GOOGLE_API_KEY


# ---------- storage ----------

def load_json(path, default):
    if path.exists():
        try:
            return json.loads(path.read_text())
        except json.JSONDecodeError:
            return default
    return default


def save_json(path, data):
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(data, indent=2, default=str))


def prune_seen(seen, days=45):
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    return {
        url: meta for url, meta in seen.items()
        if datetime.fromisoformat(meta["date"]).replace(tzinfo=timezone.utc) > cutoff
    }


# ---------- fetch ----------

def fetch_articles(hours=26):
    """Pull articles from all feeds published in the last `hours`."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    seen_urls = set()
    articles = []
    for theme, feeds in FEEDS.items():
        for feed_url in feeds:
            try:
                parsed = feedparser.parse(feed_url)
            except Exception as e:
                print(f"  [skip] {feed_url}: {e}")
                continue
            for entry in parsed.entries:
                pub_struct = entry.get("published_parsed") or entry.get("updated_parsed")
                if not pub_struct:
                    continue
                pub_dt = datetime(*pub_struct[:6], tzinfo=timezone.utc)
                if pub_dt < cutoff:
                    continue
                url = entry.get("link", "")
                if not url or url in seen_urls:
                    continue
                seen_urls.add(url)
                summary = re.sub(r"<[^>]+>", "", entry.get("summary", ""))[:1200]
                articles.append({
                    "title": entry.get("title", "").strip(),
                    "url": url,
                    "summary": summary,
                    "published": pub_dt.isoformat(),
                    "source_theme": theme,
                    "source_feed": parsed.feed.get("title", feed_url),
                })
    return articles


# ---------- claude calls ----------

def _extract_json(text):
    """Robust JSON extraction from Claude responses."""
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    # If there's leading prose, find first { and last }
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        text = text[start:end + 1]
    return json.loads(text)


def rank_articles(articles, top_n):
    """Score articles with Haiku; return top picks."""
    if not articles:
        return []

    # Cap candidates per call to keep context manageable
    articles = articles[:MAX_RANK_CANDIDATES]

    candidates = "\n\n".join(
        f"[{i}] {a['title']}\n  Source: {a['source_feed']}\n  Snippet: {a['summary'][:280]}"
        for i, a in enumerate(articles)
    )

    prompt = f"""You curate a daily newsletter for an educator and engineer designing curriculum at the intersection of AI, arts, and human flourishing.

Themes the newsletter covers:
{THEMES}

Actively prioritize:
{PRIORITIZE}

Deprioritize:
{DEPRIORITIZE}

Score each candidate article on two 0-10 scales:
- relevance: how directly it speaks to the themes, weighted by the prioritize/deprioritize signals above
- importance: significance, originality, signal vs. noise

A well-reported concrete classroom story should generally score higher than another piece of generic AI-in-education commentary.

Return ONLY a JSON object, no prose, no markdown fences, in this exact shape:
{{"rankings": [{{"index": <int>, "relevance": <0-10>, "importance": <0-10>, "primary_theme": "ai_education|innovation_education|arts_education|human_flourishing|futures_philosophy", "reason": "<10 words max>"}}]}}

Include every article with relevance >= 4. Skip the rest.

Candidates:
{candidates}
"""

    try:
        resp = gemini_client.models.generate_content(
            model=RANKER_MODEL,
            contents=prompt,
            config={
                "temperature": 0.1,
                "max_output_tokens": 4000,
                "response_mime_type": "application/json",
            },
        )
        raw_text = resp.text or ""
    except Exception as e:
        print(f"  [warn] ranker API call failed: {e}")
        return []

    try:
        data = _extract_json(raw_text)
    except (json.JSONDecodeError, ValueError) as e:
        print(f"  [warn] ranker JSON parse failed: {e}")
        print(f"  raw: {raw_text[:500]}")
        return []

    rankings = data.get("rankings", [])
    rankings.sort(key=lambda r: r.get("relevance", 0) + r.get("importance", 0), reverse=True)

    picked = []
    for r in rankings:
        if r.get("relevance", 0) + r.get("importance", 0) < DAILY_MIN_SCORE:
            continue
        idx = r.get("index")
        if idx is None or idx >= len(articles):
            continue
        a = articles[idx].copy()
        a["primary_theme"] = r.get("primary_theme", a["source_theme"])
        a["reason"] = r.get("reason", "")
        a["relevance"] = r.get("relevance", 0)
        a["importance"] = r.get("importance", 0)
        picked.append(a)
        if len(picked) >= top_n:
            break

    return picked


def summarize_articles(articles):
    """Write a 2-3 sentence summary for each picked article using Sonnet."""
    for a in articles:
        prompt = f"""Summarize this article in 2-3 tight sentences for a daily newsletter for an educator who values directness and dislikes hedging or filler.

Rules:
- Lead with the concrete development, finding, or central claim. No "this article discusses..."
- For news/research pieces: lead with what happened or was found.
- For essays and big-idea pieces (Nautilus, Aeon, Noema, SFI, etc.): lead with the author's core argument, framework, or insight — not just the topic. Treat the reader as intellectually serious; preserve the actual idea rather than flattening it.
- No hype, no marketing language, no rhetorical questions.
- If the title and snippet don't make the substance clear, say "Full read needed —" and offer the best framing you can.

Title: {a['title']}
Source: {a['source_feed']}
Snippet: {a['summary']}
"""
        try:
            resp = anthropic_client.messages.create(
                model=WRITER_MODEL,
                max_tokens=300,
                messages=[{"role": "user", "content": prompt}],
            )
            a["claude_summary"] = resp.content[0].text.strip()
        except Exception as e:
            print(f"  [warn] summary failed for {a['url']}: {e}")
            a["claude_summary"] = a["summary"][:300]
        time.sleep(0.3)  # be polite
    return articles


# ---------- rendering ----------

THEME_LABELS = {
    "ai_education": "AI × Education",
    "innovation_education": "Innovation",
    "arts_education": "Arts in Education",
    "human_flourishing": "Human Flourishing",
    "futures_philosophy": "Futures & Philosophy",
}


def render_daily_html(articles):
    today = datetime.now().strftime("%A, %B %d, %Y").replace(" 0", " ")
    items = ""
    for a in articles:
        label = THEME_LABELS.get(a["primary_theme"], a["primary_theme"])
        items += f"""
        <div style="margin-bottom:32px;padding-bottom:28px;border-bottom:1px solid #e5e5e5;">
          <div style="font-size:11px;text-transform:uppercase;letter-spacing:0.1em;color:#6b7280;margin-bottom:8px;">{label}</div>
          <a href="{a['url']}" style="color:#111;text-decoration:none;"><h2 style="margin:0 0 6px 0;font-size:19px;line-height:1.35;font-weight:600;">{a['title']}</h2></a>
          <div style="font-size:12px;color:#9ca3af;margin-bottom:12px;">{a['source_feed']}</div>
          <p style="margin:0 0 10px 0;font-size:15px;line-height:1.6;color:#1f2937;">{a['claude_summary']}</p>
          <a href="{a['url']}" style="font-size:13px;color:#2563eb;text-decoration:none;">Read →</a>
        </div>"""

    return f"""<!DOCTYPE html><html><body style="margin:0;background:#fafafa;">
<div style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;max-width:640px;margin:0 auto;padding:40px 24px;background:#fff;">
  <div style="margin-bottom:36px;">
    <div style="font-size:11px;text-transform:uppercase;letter-spacing:0.12em;color:#6b7280;">Daily Brief · {today}</div>
    <h1 style="margin:6px 0 0 0;font-size:26px;font-weight:600;color:#111;">Education / AI / Arts / Flourishing</h1>
  </div>
  {items}
  <div style="margin-top:40px;padding-top:20px;border-top:1px solid #e5e5e5;font-size:11px;color:#9ca3af;text-align:center;">
    {len(articles)} stories · curated by Claude · weekly roundup Sunday
  </div>
</div></body></html>"""


def render_weekly_html(daily_articles, bonus_articles):
    today = datetime.now().strftime("%B %d, %Y").replace(" 0", " ")
    by_theme = {}
    for a in daily_articles:
        by_theme.setdefault(a.get("primary_theme", "other"), {"daily": [], "bonus": []})["daily"].append(a)
    for a in bonus_articles:
        by_theme.setdefault(a.get("primary_theme", "other"), {"daily": [], "bonus": []})["bonus"].append(a)

    sections = ""
    for theme in ["ai_education", "innovation_education", "arts_education", "human_flourishing", "futures_philosophy"]:
        if theme not in by_theme:
            continue
        label = THEME_LABELS.get(theme, theme)
        items_html = ""
        for a in by_theme[theme]["daily"]:
            items_html += f"""
            <div style="margin-bottom:18px;">
              <a href="{a['url']}" style="color:#111;text-decoration:none;"><strong style="font-size:15px;">• {a['title']}</strong></a>
              <div style="font-size:12px;color:#9ca3af;margin:2px 0 6px 0;">{a['source_feed']}</div>
              <p style="margin:0;font-size:14px;line-height:1.55;color:#1f2937;">{a.get('claude_summary', '')[:400]}</p>
            </div>"""
        for a in by_theme[theme]["bonus"]:
            items_html += f"""
            <div style="margin-bottom:18px;">
              <a href="{a['url']}" style="color:#111;text-decoration:none;"><strong style="font-size:15px;color:#7c3aed;">✦ {a['title']}</strong></a>
              <div style="font-size:12px;color:#9ca3af;margin:2px 0 6px 0;">{a['source_feed']}</div>
              <p style="margin:0;font-size:14px;line-height:1.55;color:#1f2937;">{a.get('claude_summary', '')[:400]}</p>
            </div>"""
        sections += f"""
        <div style="margin-bottom:36px;">
          <h2 style="font-size:13px;text-transform:uppercase;letter-spacing:0.1em;color:#374151;border-bottom:2px solid #111;padding-bottom:8px;margin:0 0 16px 0;">{label}</h2>
          {items_html}
        </div>"""

    return f"""<!DOCTYPE html><html><body style="margin:0;background:#fafafa;">
<div style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;max-width:720px;margin:0 auto;padding:40px 24px;background:#fff;">
  <div style="margin-bottom:32px;">
    <div style="font-size:11px;text-transform:uppercase;letter-spacing:0.12em;color:#6b7280;">Weekly Roundup · week of {today}</div>
    <h1 style="margin:6px 0 8px 0;font-size:28px;font-weight:600;color:#111;">The week in education</h1>
    <div style="font-size:12px;color:#6b7280;">• daily picks &nbsp;·&nbsp; <span style="color:#7c3aed;">✦ bonus stories</span></div>
  </div>
  {sections}
</div></body></html>"""


# ---------- email ----------

def send_email(subject, html_body):
    smtp_host = os.environ["SMTP_HOST"]
    smtp_port = int(os.environ.get("SMTP_PORT", "587"))
    smtp_user = os.environ["SMTP_USER"]
    smtp_pass = os.environ["SMTP_PASS"]
    to_addr = os.environ["TO_EMAIL"]
    from_addr = os.environ.get("FROM_EMAIL", smtp_user)

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = from_addr
    msg["To"] = to_addr
    msg.attach(MIMEText(html_body, "html"))

    with smtplib.SMTP(smtp_host, smtp_port, timeout=30) as server:
        server.starttls()
        server.login(smtp_user, smtp_pass)
        server.send_message(msg)


# ---------- orchestration ----------

def run_daily():
    print("Fetching articles (last 26h)...")
    articles = fetch_articles(hours=26)
    print(f"  {len(articles)} fetched")

    seen = load_json(SEEN_FILE, {})
    fresh = [a for a in articles if a["url"] not in seen]
    print(f"  {len(fresh)} unseen")

    if not fresh:
        print("Nothing new. Skipping email.")
        return

    print("Ranking with Gemini Flash...")
    picked = rank_articles(fresh, top_n=DAILY_TARGET)
    print(f"  {len(picked)} picked above threshold")

    if not picked:
        # Mark fetched as seen anyway so we don't re-evaluate tomorrow
        for a in fresh:
            seen[a["url"]] = {"date": datetime.now(timezone.utc).isoformat(), "title": a["title"], "skipped": True}
        save_json(SEEN_FILE, prune_seen(seen))
        print("Nothing scored above threshold. Skipping email.")
        return

    print("Summarizing with Sonnet...")
    picked = summarize_articles(picked)

    print("Sending...")
    html = render_daily_html(picked)
    today_label = datetime.now().strftime("%a %b %d").replace(" 0", " ")
    send_email(f"Daily Brief · {today_label}", html)

    # Update storage
    now_iso = datetime.now(timezone.utc).isoformat()
    for a in fresh:
        seen[a["url"]] = {"date": now_iso, "title": a["title"], "picked": a in picked}
    save_json(SEEN_FILE, prune_seen(seen))

    archive = load_json(ARCHIVE_FILE, [])
    archive.append({"date": now_iso, "articles": picked})
    archive = [d for d in archive if (datetime.now(timezone.utc) - datetime.fromisoformat(d["date"])).days < 14]
    save_json(ARCHIVE_FILE, archive)

    print("Done.")


def run_weekly():
    print("Building weekly roundup...")
    archive = load_json(ARCHIVE_FILE, [])
    cutoff = datetime.now(timezone.utc) - timedelta(days=7)
    recent_days = [d for d in archive if datetime.fromisoformat(d["date"]) > cutoff]

    daily_articles = []
    seen_urls = set()
    for day in recent_days:
        for a in day["articles"]:
            if a["url"] not in seen_urls:
                daily_articles.append(a)
                seen_urls.add(a["url"])
    print(f"  {len(daily_articles)} daily picks from the week")

    print("Casting wider net for bonus stories (last 7 days)...")
    week_articles = fetch_articles(hours=168)
    week_fresh = [a for a in week_articles if a["url"] not in seen_urls]
    print(f"  {len(week_fresh)} candidates for bonus")

    bonus = []
    if week_fresh:
        bonus = rank_articles(week_fresh, top_n=BONUS_TARGET)
        if bonus:
            bonus = summarize_articles(bonus)
            print(f"  {len(bonus)} bonus picks")

    if not daily_articles and not bonus:
        print("Nothing to send.")
        return

    html = render_weekly_html(daily_articles, bonus)
    today_label = datetime.now().strftime("%b %d").replace(" 0", " ")
    send_email(f"Weekly Roundup · week of {today_label}", html)
    print("Done.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=["daily", "weekly"])
    args = parser.parse_args()
    if args.mode == "daily":
        run_daily()
    else:
        run_weekly()
