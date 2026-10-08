#!/usr/bin/env python3
"""Daily refresh (GitHub Actions): har country ke liye Google News se
top stories + niche searches fetch karo, classify karo, diversify karo
-> data/trends_<CC>.json

Target: har country me ~20 DIFFERENT niches roz.
"""
import json, os, re, sys, time, urllib.request, urllib.parse
import xml.etree.ElementTree as ET
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from detector import classify_niche, copyright_rating  # noqa: E402

BASE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(BASE, "data")
os.makedirs(DATA, exist_ok=True)

COUNTRIES = {"DE": ("DE", "en"), "US": ("US", "en"),
             "GB": ("GB", "en"), "PK": ("PK", "en")}

# Har ek search ek niche-domain ko target karta hai -> roz ~20 different niches
NICHE_SEARCHES = [
    "artificial intelligence", "bitcoin", "football", "health",
    "NASA space", "movie", "real estate", "unemployment",
    "travel tourism", "stock market", "climate change", "gaming",
    "motivation mindset", "cooking recipe", "electric vehicles", "history",
    "online learning", "solar energy",
]

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126.0 Safari/537.36"}
MAX_PER_NICHE = 2
MAX_OTHER = 2
MAX_TOPICS = 44
TOP_STORIES_TAKE = 10
PER_SEARCH_TAKE = 3


def fetch_items(url):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=25) as r:
        xml = r.read().decode("utf-8", "ignore")
    root = ET.fromstring(xml)
    items = []
    for it in root.iter("item"):
        title = (it.findtext("title") or "").strip()
        link = (it.findtext("link") or "").strip()
        if not title or title == "Google News":
            continue
        if " - " in title:
            title, source = title.rsplit(" - ", 1)
        else:
            source = ""
        items.append({"raw": title.strip(), "source": source.strip(), "link": link})
    return items


def build_country(cc):
    gl, hl = COUNTRIES[cc]
    pool = []
    try:
        pool += fetch_items(
            f"https://news.google.com/rss?gl={gl}&hl={hl}&ceid={gl}%3A{hl}")[:TOP_STORIES_TAKE]
    except Exception as e:
        print(f"[{cc}] top stories fail: {e}", flush=True)
    for q in NICHE_SEARCHES:
        try:
            u = ("https://news.google.com/rss/search?q=" + urllib.parse.quote(q)
                 + f"&hl={hl}&gl={gl}&ceid={gl}%3A{hl}")
            pool += fetch_items(u)[:PER_SEARCH_TAKE]
        except Exception as e:
            print(f"[{cc}] search '{q}' fail: {e}", flush=True)
        time.sleep(0.4)

    seen, topics = set(), []
    for it in pool:
        key = re.sub(r"\W+", "", it["raw"].lower())
        if key in seen:
            continue
        seen.add(key)
        niche = classify_niche(it["raw"])
        level, reason = copyright_rating(niche)
        topics.append({"title": it["raw"], "source": it["source"],
                       "link": it["link"], "niche": niche,
                       "copyright": level, "copyright_note": reason,
                       "country": cc})

    # diversify: har niche se MAX 2 (strict) -> ~20 DIFFERENT niches ka target
    counts, result = {}, []
    for tp in topics:
        n = tp["niche"]
        cap = MAX_OTHER if n == "Other" else MAX_PER_NICHE
        if counts.get(n, 0) >= cap:
            continue
        result.append(tp)
        counts[n] = counts.get(n, 0) + 1
        if len(result) >= MAX_TOPICS:
            break

    niches = sorted({t["niche"] for t in result if t["niche"] != "Other"})
    return result, niches


def main():
    today = date.today().isoformat()
    for cc in COUNTRIES:
        topics, niches = build_country(cc)
        with open(os.path.join(DATA, f"trends_{cc}.json"), "w", encoding="utf-8") as f:
            json.dump({"date": today, "topics": topics, "niches": niches},
                      f, ensure_ascii=False, indent=2)
        print(f"[{cc}] {len(topics)} topics, {len(niches)} different niches", flush=True)


if __name__ == "__main__":
    main()
