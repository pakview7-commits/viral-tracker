#!/usr/bin/env python3
"""Auto-detect viral TikTok niches/accounts from trending data.

Pipeline: fetch trending hashtags/videos -> classify niche by keywords ->
score by engagement -> write data/candidates.json for review in the dashboard.

Run: python3 detector.py   (or press 🤖 in the dashboard)
Last line of stdout is always a JSON status object.
"""
import json, os, re, sys, time, urllib.request, urllib.parse
from datetime import date

BASE = os.path.dirname(os.path.abspath(__file__))
CANDS = os.path.join(BASE, "data", "candidates.json")
ACCOUNTS = os.path.join(BASE, "data", "accounts.json")

# ---------- niche keyword classifier ----------
# Order matters: first match wins. Specific content niches first, news buckets last.
NICHE_KEYWORDS = [
    ("Police bodycam compilations", ["bodycam", "body cam", "police footage", "cop cam", "officer", "arrest", "patrol", "police chase", "police pov"]),
    ("AI adventure narration (docu-style series)", ["ai adventure", "ai narrat", "ai documentary", "docu series", "ai story", "narrated adventure"]),
    ("AI meme/brainrot edited videos", ["brainrot", "ai meme", "meme edit", "skibidi", "sigma"]),
    ("History", ["history", "historical", "ancient", "world war"]),
    ("True crime", ["true crime", "murder", "killer", "missing", "dead", "death", "died", "shooting", "stabbing", "kidnap"]),
    ("Reddit stories", ["reddit", "aita", "askreddit"]),
    ("Mindset/motivation", ["mindset", "motivation", "discipline", "stoic", "self improvement"]),
    ("Crypto", ["crypto", "bitcoin", "ethereum", "blockchain", "defi", "nft"]),
    ("Finance/money", ["finance", "investing", "stocks", "shares", "gdp", "recession", "interest rate", "budget", "inflation", "economy", "stock market"]),
    ("AI movie/trailer edits", ["ai movie", "ai trailer", "movie ai", "film ai"]),
    ("Gaming", ["gaming", "gamer", "video game", "esports", "playstation", "xbox", "nintendo", "fortnite", "minecraft"]),
    ("Cam footage", ["dashcam", "cctv", "caught on camera", "doorbell camera", "police cam"]),
    ("Ranking/Top 10", ["top 10", "top 5", "top 20", "top 100", "ranking the", "ranked all"]),
    ("Scandals/Drama", ["scandal", "exposed", "controversy", "allegations", "drama explained", "the downfall of"]),
    ("Automation/Faceless", ["faceless", "cash cow", "no face reveal"]),
    ("Islamic", ["islamic", "quran", "naat", "ramadan", "prophet", "muslim"]),
    ("Lifestyle", ["lifestyle", "morning routine", "night routine", "grwm", "get ready with me", "day in my life", "daily routine"]),
    ("Nature/wildlife", ["wildlife", "animals", "ocean", "kayak", "hurricane", "storm", "earthquake", "flood", "wildfire"]),
    ("Sports highlights", ["sports", "football", "soccer", "nba", "highlights", "bundesliga", "premier league", "champions league", "world cup", "tournament", "olympics", "transfer window", "championship", "grand prix", "match"]),
    ("DIY/crafts", ["diy", "craft", "woodworking"]),
    ("Cooking/food", ["cooking", "food", "recipe", "chef"]),
    ("Tech/AI news", ["artificial intelligence", "ai ", "ai-powered", "openai", "iphone", "microsoft", "robot", "chip", "software", "gadget", "app launch", "startup"]),
    ("Space", ["space", "nasa", "rocket", "satellite", "mars", "astronaut", "spacex", "moon mission"]),
    ("Science", ["scientists", "study finds", "research", "discovery", "experiment", "physics", "vaccine trial"]),
    ("Health/Fitness", ["health", "disease", "virus", "vaccine", "hospital", "doctor", "fitness", "workout", "mental health"]),
    ("Environment/Climate", ["climate", "pollution", "emissions", "renewable", "solar power", "wind farm", "deforestation", "carbon"]),
    ("Entertainment/Celebrity", ["actor", "actress", "singer", "concert", "album", "movie", "film", "netflix", "hollywood", "bollywood", "box office", "celebrity"]),
    ("Travel/Tourism", ["travel", "tourism", "tourist", "vacation", "airline", "hotel", "destination"]),
    ("Education", ["education", "school", "university", "students", "exam", "degree", "scholarship"]),
    ("Real Estate", ["real estate", "housing", "property prices", "rent", "mortgage", "apartment"]),
    ("Automotive", ["electric vehicle", "tesla", "driverless", "auto industry", "car launch"]),
    ("Jobs/Career", ["unemployment", "layoffs", "hiring", "career", "salary", "job cuts"]),
    ("Energy", ["oil prices", "gas prices", "nuclear power", "electricity", "energy crisis", "opec"]),
    ("News/Current affairs", ["election", "minister", "government", "president", "parliament", "senate", "ukraine", "gaza", "iran", "summit", "court", "lawyer", "protest", "accident", "verdict", "police", "tax", "immigration", "democrat", "republican", "sanctions", "tariff", "prime minister", "war", "military", "army", "border", "ceasefire"]),
]

# ---------- copyright safety rating per niche ----------
# level: low = original content safe | medium = careful, transform/add own voice | high = strike risk
COPYRIGHT_RISK = {
    "AI adventure narration (docu-style series)": ("low", "AI visuals + apni narration — original content"),
    "AI meme/brainrot edited videos": ("low", "AI-generated — original content"),
    "Mindset/motivation": ("low", "Stock footage + apni voiceover safe hai"),
    "Finance/money": ("low", "Apni commentary / screen recording safe hai"),
    "Cooking/food": ("low", "Khud ki video banao — 100% safe"),
    "DIY/crafts": ("low", "Khud ki video banao — 100% safe"),
    "History": ("medium", "Apni narration + public-domain footage use karo"),
    "Reddit stories": ("medium", "Gameplay footage ka license check karo"),
    "Police bodycam compilations": ("medium", "Public footage hai, lekin transformative editing zaroori"),
    "True crime": ("medium", "News clips par apni commentary add karo"),
    "Nature/wildlife": ("medium", "Stock footage ya apni filming use karo"),
    "Tech/AI news": ("medium", "Clips reuse mat karo — apni voiceover banao"),
    "Entertainment/Celebrity": ("medium", "Celebrity clips par apni commentary add karo"),
    "Crypto": ("low", "Apni analysis / screen recording safe hai"),
    "Cam footage": ("medium", "Public footage hai, transformative editing zaroori"),
    "Ranking/Top 10": ("medium", "Clips par apni voiceover banao"),
    "Scandals/Drama": ("medium", "Clips reuse mat karo — apni commentary banao"),
    "Automation/Faceless": ("low", "AI/stock visuals + apni voiceover — original"),
    "Islamic": ("low", "Apni voiceover + visuals safe hain"),
    "Lifestyle": ("low", "Apna khud ka content — original"),
    "Gaming": ("medium", "Game footage par transformative commentary zaroori"),
    "Science": ("low", "Apni voiceover + visuals safe hain"),
    "Space": ("low", "NASA/public-domain footage + apni voiceover"),
    "Environment/Climate": ("low", "Apni voiceover + stock visuals safe hain"),
    "Travel/Tourism": ("low", "Khud ki footage sab se best"),
    "Education": ("low", "Original explainers 100% safe"),
    "Real Estate": ("low", "Apni commentary / khud ki footage"),
    "Automotive": ("low", "Apna review / khud ki footage"),
    "Jobs/Career": ("low", "Apni advice videos safe hain"),
    "Energy": ("low", "Apni voiceover + charts safe hain"),
    "Health/Fitness": ("low", "Apni voiceover + stock visuals safe hain"),
    "News/Current affairs": ("medium", "Footage reuse nahi — apni reporting/voiceover banao"),
    "Sports highlights": ("high", "Leagues/teams copyright strike deti hain"),
    "AI movie/trailer edits": ("high", "Studio films ka content — strike ka khatra"),
    "Other": ("medium", "Source material ka license check karo"),
}

def copyright_rating(niche):
    return COPYRIGHT_RISK.get(niche, COPYRIGHT_RISK["Other"])

def classify_niche(text):
    t = (text or "").lower()
    for niche, kws in NICHE_KEYWORDS:
        if any(k in t for k in kws):
            return niche
    return "Other"

def score_video(v):
    """Engagement score 0-100 from likes/views."""
    likes = v.get("likes") or 0
    views = v.get("views") or 0
    s = 0
    if likes >= 1_000_000: s += 50
    elif likes >= 500_000: s += 40
    elif likes >= 100_000: s += 30
    elif likes >= 20_000: s += 18
    elif likes >= 5_000: s += 8
    if views >= 10_000_000: s += 50
    elif views >= 5_000_000: s += 40
    elif views >= 1_000_000: s += 30
    elif views >= 200_000: s += 15
    return min(s, 100)

def fmt(n):
    if not n: return "0"
    if n >= 1e6: return f"{n/1e6:.1f}M"
    if n >= 1e3: return f"{n/1e3:.1f}K"
    return str(n)

# ---------- trending sources (adapter) ----------
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"}

def http_json(url, timeout=20):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8", "ignore"))

def fetch_trending():
    """Return list of dicts: {hashtag, views, videos:[{author, likes, views, url, desc}]}.

    Tries TikTok Creative Center public endpoints first, falls back to [].
    NOTE: TikTok aggressively rate-limits/bot-blocks; empty result is normal
    and the dashboard still works fully with manual entries.
    """
    out = []
    # Source 1: TikTok Creative Center trending hashtags (public, no key)
    try:
        url = ("https://ads.tiktok.com/creative_radar_api/v1/popular_trend/hashtag/list"
               "?period=7&limit=30&country_code=US")
        data = http_json(url)
        items = data.get("data", {}).get("hashtag_list", []) or data.get("data", {}).get("list", [])
        for h in items:
            name = h.get("hashtag_name") or h.get("name") or ""
            views = h.get("video_views") or h.get("publish_cnt") or 0
            if name:
                out.append({"hashtag": name, "views": views, "videos": []})
    except Exception as e:
        sys.stderr.write(f"creative-center hashtags failed: {e}\n")
    time.sleep(1)
    # Source 2: per-hashtag top videos via Creative Center detail endpoint
    for h in out[:10]:
        try:
            q = urllib.parse.quote(h["hashtag"])
            url = (f"https://ads.tiktok.com/creative_radar_api/v1/popular_trend/hashtag/detail"
                   f"?hashtag_name={q}&period=7&limit=5&country_code=US")
            data = http_json(url)
            vids = data.get("data", {}).get("video_list", []) or []
            for v in vids:
                author = v.get("author") or v.get("username") or ""
                if author and not author.startswith("@"):
                    author = "@" + author
                h["videos"].append({
                    "author": author,
                    "likes": v.get("like_cnt") or v.get("likes") or 0,
                    "views": v.get("play_cnt") or v.get("views") or 0,
                    "url": v.get("video_url") or v.get("share_url") or "",
                    "desc": v.get("desc") or v.get("title") or "",
                })
        except Exception as e:
            sys.stderr.write(f"hashtag detail {h['hashtag']} failed: {e}\n")
        time.sleep(1)
    return out

# ---------- main ----------
def main():
    existing = set()
    for p in (ACCOUNTS, CANDS):
        if os.path.exists(p):
            try:
                for a in json.load(open(p, encoding="utf-8")):
                    existing.add(a.get("handle", "").lower())
            except Exception:
                pass

    trending = fetch_trending()
    cands = []
    seen = set()
    for h in trending:
        tag = h["hashtag"]
        for v in h.get("videos", []):
            handle = (v.get("author") or "").strip()
            if not handle or handle.lower() in existing or handle.lower() in seen:
                continue
            niche = classify_niche(tag + " " + v.get("desc", ""))
            s = score_video(v)
            if s < 15:
                continue
            seen.add(handle.lower())
            cands.append({
                "handle": handle,
                "niche": niche,
                "followers": None,
                "rewards_eligible": True,
                "notes": f"#{tag}: {fmt(v.get('views'))} views, {fmt(v.get('likes'))} likes",
                "video1_url": v.get("url") or None,
                "video2_url": None,
                "date_added": date.today().isoformat(),
                "source": "auto",
                "score": s,
                "evidence": [f"#{tag}", f"{fmt(v.get('views'))} views",
                             f"{fmt(v.get('likes'))} likes"],
            })
    cands.sort(key=lambda c: -c["score"])
    cands = cands[:40]
    with open(CANDS, "w", encoding="utf-8") as f:
        json.dump(cands, f, ensure_ascii=False, indent=2)

    status = {"ok": True, "candidates": len(cands),
              "hashtags_scanned": len(trending),
              "message": f"{len(trending)} trending hashtags scan hue, {len(cands)} candidates mile" if trending
                         else "Trending source se data nahi mila (rate-limit/block). Manual add ab bhi available hai."}
    print(json.dumps(status, ensure_ascii=False))

if __name__ == "__main__":
    main()
