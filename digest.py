#!/usr/bin/env python3
"""Nightly web digest: scrape articles, summarize with a local Qwen3.5-4B
served by llama-server, and send the best items to Telegram.

Requires: pip install feedparser httpx trafilatura openai
Env vars: TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
"""

import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import feedparser
import httpx
import trafilatura
from openai import OpenAI

# ---------------- config ----------------
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "http://localhost:8080/v1")
TG_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")      # from @BotFather
TG_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")      # your user/chat id

FEEDS = [
    "https://hnrss.org/frontpage",
    "https://www.reddit.com/r/LocalLLaMA/.rss",
]
INTERESTS = (
    "local LLM inference, quantization, llama.cpp, RAG, LLM agents, "
    "small language models, AI engineering tooling"
)
MAX_ARTICLES = int(os.getenv("MAX_ARTICLES", "8"))
MAX_CHARS = 6000          # cap article text sent to the model
MIN_RELEVANCE = 6         # 1-10; items scoring below this are dropped
SEEN_FILE = Path(__file__).with_name("seen.json")
REQ_TIMEOUT = httpx.Timeout(900.0, connect=15.0)  # CPU inference is slow

SUMMARY_SCHEMA = {
    "type": "json_schema",
    "json_schema": {
        "name": "article_summary",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "summary": {"type": "string", "description": "Max 3 sentences, plain text"},
                "relevance": {"type": "integer", "description": "1-10 relevance to user interests"},
                "tags": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["summary", "relevance", "tags"],
            "additionalProperties": False,
        },
    },
}

THINK_RE = re.compile(r"<think>.*?</think>", re.S)


def log(msg: str) -> None:
    print(f"[{datetime.now():%H:%M:%S}] {msg}", flush=True)


def load_seen() -> set:
    if SEEN_FILE.exists():
        return set(json.loads(SEEN_FILE.read_text()))
    return set()


def save_seen(seen: set) -> None:
    SEEN_FILE.write_text(json.dumps(sorted(seen)[-1000:]))


def fetch_candidates(seen: set) -> list:
    items = []
    for feed in FEEDS:
        parsed = feedparser.parse(feed)
        if parsed.bozo and not parsed.entries:
            log(f"feed failed: {feed}")
            continue
        for entry in parsed.entries[:20]:
            url = entry.get("link")
            title = entry.get("title", "").strip()
            if url and title and url not in seen:
                items.append({"title": title, "url": url})
    return items[:MAX_ARTICLES]


def extract_text(url: str):
    try:
        html = trafilatura.fetch_url(url)
        if not html:
            return None
        text = trafilatura.extract(html)
        return text[:MAX_CHARS] if text else None
    except Exception:
        return None


def summarize(client: OpenAI, model: str, title: str, text: str):
    prompt = (
        "Summarize the article below for a software engineer.\n"
        f"Score its relevance (1-10) to these interests: {INTERESTS}.\n\n"
        f"TITLE: {title}\n\nARTICLE:\n{text}"
    )
    resp = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3,
        max_tokens=512,
        response_format=SUMMARY_SCHEMA,
    )
    raw = THINK_RE.sub("", resp.choices[0].message.content or "").strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {"summary": raw[:500], "relevance": 0, "tags": []}


def send_telegram(text: str) -> None:
    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
    for i in range(0, len(text), 4000):  # Telegram limit is 4096 chars
        r = httpx.post(url, json={"chat_id": TG_CHAT_ID, "text": text[i:i + 4000]}, timeout=30)
        r.raise_for_status()


def main() -> int:
    if not TG_TOKEN or not TG_CHAT_ID:
        sys.exit("Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID first (see README notes).")

    client = OpenAI(base_url=LLM_BASE_URL, api_key="not-needed", timeout=REQ_TIMEOUT)
    model = client.models.list().data[0].id  # whatever llama-server has loaded

    seen = load_seen()
    digest_lines = []

    for item in fetch_candidates(seen):
        log(f"processing: {item['title'][:80]}")
        text = extract_text(item["url"])
        if not text:
            log("  skipped: no extractable text")
            continue
        try:
            result = summarize(client, model, item["title"], text)
        except Exception as e:
            log(f"  summarize failed: {e}")
            continue
        seen.add(item["url"])
        if not result or result.get("relevance", 0) < MIN_RELEVANCE:
            log(f"  dropped: relevance {result.get('relevance') if result else '?'}")
            continue
        tags = ", ".join(result.get("tags", []))
        digest_lines.append(
            f"* {item['title']}  ({result['relevance']}/10)\n"
            f"{result['summary']}\n"
            f"{item['url']}\n"
            f"[{tags}]\n"
        )

    save_seen(seen)
    if not digest_lines:
        log("nothing worth sending today")
        return 0

    header = f"Daily digest - {datetime.now(timezone.utc):%Y-%m-%d} ({len(digest_lines)} items)\n\n"
    send_telegram(header + "\n".join(digest_lines))
    log(f"sent {len(digest_lines)} items to Telegram")
    return 0


if __name__ == "__main__":
    sys.exit(main())
