#!/usr/bin/env python3
"""YouTube -> TikTok Gap finder (SHORTS ONLY).

Har region ke liye YouTube trending + last-30-days viral SHORTS uthao
(duration <= 3 min), niche + FORMAT classify karo,
phir TikTok par pehle se saturated formats se compare karke GAP nikalo:
  🟢 Niche gap   — ye niche TikTok par kam/saturated nahi
  🟡 Format gap  — niche TikTok par hai, lekin YE format naya hai
  🔴 Saturated   — niche + format dono TikTok par common hain

Needs: YT_API_KEY env (free YouTube Data API v3 key). Baghair key ke
gracefully empty likhta hai.

"Viral in 1 month": video published <=30 din pehle + high views -> 🔥,
ya channel naya (<120 din) lekin views zyada -> ⚡.
"""
import json, os, re, sys, time, urllib.request, urllib.parse
from datetime import date, datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from detector import classify_niche  # noqa: E402

BASE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(BASE, "data")
os.makedirs(DATA, exist_ok=True)

API = "https://www.googleapis.com/youtube/v3"
REGIONS = ["US", "DE", "GB", "PK"]
REGION_NAMES = {"US": "🇺🇸 USA", "DE": "🇩🇪 Germany", "GB": "🇬🇧 UK", "PK": "🇵🇰 Pakistan"}

# ---------- format detection ----------
FORMAT_KEYWORDS = [
    ("Reddit stories", ["reddit", "aita", "askreddit"]),
    ("True crime deep-dive", ["true crime", "the case of", "unsolved", "serial killer"]),
    ("AI narration", ["ai voice", "ai generated", "ai narration", "narrated by ai"]),
    ("Animated explainer", ["animation", "animated", "motion graphics"]),
    ("POV / skit", ["pov", "skit", "comedy sketch"]),
    ("Challenge / experiment", ["challenge", "i survived", "100 days", "experiment", "i tried", "$1 vs"]),
    ("Tutorial / how-to", ["how to", "tutorial", "step by step", "diy"]),
    ("Review / unboxing", ["review", "unboxing", "first look", "hands on"]),
    ("Gaming playthrough", ["gameplay", "playthrough", "speedrun", "let's play", "no commentary gameplay"]),
    ("Talking head / podcast", ["podcast", "interview", "talks about", "explains"]),
    ("Vlog / day in life", ["vlog", "day in my life", "daily vlog", "come with me"]),
    ("Compilation", ["compilation", "funny moments", "highlights", "best of", "try not to laugh"]),
    ("Faceless documentary", ["documentary", "explained", "the untold", "history of", "what happened"]),
    ("Music / performance", ["official music video", "live performance", "cover", "concert"]),
]

def detect_format(title, desc, duration_s):
    t = ((title or "") + " " + (desc or "")).lower()
    for fmt, kws in FORMAT_KEYWORDS:
        if any(k in t for k in kws):
            return fmt
    if duration_s and duration_s <= 65:
        return "Shorts / vertical clip"
    return "Standard video"

# ---------- TikTok saturation map (heuristic, coded knowledge) ----------
# niche -> formats jo TikTok par ALREADY common/saturated hain
TIKTOK_SATURATED = {
    "Police bodycam compilations": ["Compilation"],
    "AI adventure narration (docu-style series)": ["AI narration", "Faceless documentary"],
    "AI meme/brainrot edited videos": ["Shorts / vertical clip"],
    "History": ["Faceless documentary", "AI narration"],
    "True crime": ["True crime deep-dive", "Faceless documentary"],
    "Reddit stories": ["Reddit stories"],
    "Mindset/motivation": ["Shorts / vertical clip", "Compilation"],
    "Finance/money": ["Talking head / podcast", "Shorts / vertical clip"],
    "Crypto": ["Talking head / podcast", "Shorts / vertical clip"],
    "Sports highlights": ["Compilation", "Shorts / vertical clip"],
    "AI movie/trailer edits": ["Compilation"],
    "Entertainment/Celebrity": ["Compilation", "Shorts / vertical clip"],
    "Gaming": ["Gaming playthrough", "Shorts / vertical clip"],
    "Cooking/food": ["Tutorial / how-to", "Shorts / vertical clip"],
    "News/Current affairs": ["Talking head / podcast", "Shorts / vertical clip"],
    "Ranking/Top 10": ["Shorts / vertical clip", "Compilation"],
    "Scandals/Drama": ["Shorts / vertical clip", "Talking head / podcast"],
    "Cam footage": ["Compilation", "Shorts / vertical clip"],
}

def gap_assess(niche, fmt):
    sat = TIKTOK_SATURATED.get(niche)
    if sat is None:
        return ("niche_gap", "🟢 Niche gap",
                f"'{niche}' TikTok par kam saturated hai — pehla mover advantage")
    if fmt in sat:
        return ("saturated", "🔴 Saturated",
                f"'{niche}' + '{fmt}' TikTok par already common hai")
    return ("format_gap", "🟡 Format gap",
            f"Niche TikTok par hai, lekin '{fmt}' format wahan naya lagta hai")

# ---------- content filters (amir's rules) ----------
# Dance / adult content kabhi nahi; purane mega channels nahi (sirf rising stars)
EXCLUDE_TITLE = ["dance", "dancing", "twerk", "nude", "naked", "porn",
                 "onlyfans", "xxx", "brazzers"]
MEGA_SUBS = 5_000_000      # is se zyada subs...
MEGA_AGE_DAYS = 730        # ...aur 2 saal se purana channel = exclude

def title_excluded(title):
    t = (title or "").lower()
    return any(k in t for k in EXCLUDE_TITLE)

# region -> search language (US/UK/DE English majority, PK local mix)
SEARCH_LANG = {"US": "en", "DE": "en", "GB": "en", "PK": None}
def yt_get(key, path, params):
    params = dict(params); params["key"] = key
    url = API + path + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=25) as r:
        return json.loads(r.read().decode())

def parse_duration(iso):
    m = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", iso or "")
    if not m: return 0
    h, mnt, s = (int(x) if x else 0 for x in m.groups())
    return h * 3600 + mnt * 60 + s

def fmt_views(n):
    try: n = int(n)
    except: return "—"
    if n >= 1e6: return f"{n/1e6:.1f}M"
    if n >= 1e3: return f"{n/1e3:.1f}K"
    return str(n)

def channel_age_days(published_at):
    try:
        dt = datetime.fromisoformat(published_at.replace("Z", "+00:00"))
        return (datetime.now(timezone.utc) - dt).days
    except Exception:
        return None

def build_region(key, region):
    """SHORTS ONLY: trending + last-30-days viral shorts search, duration <= 3 min."""
    items_by_id = {}
    # 1. trending videos
    pop = yt_get(key, "/videos", {
        "part": "snippet,statistics,contentDetails",
        "chart": "mostPopular", "regionCode": region, "maxResults": 25,
    }).get("items", [])
    for v in pop:
        items_by_id[v["id"]] = v
    time.sleep(0.3)
    # 2. last 30 days ke viral SHORTS (search API)
    since = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
    sparams = {
        "part": "snippet", "q": "shorts", "type": "video",
        "videoDuration": "short", "order": "viewCount",
        "publishedAfter": since, "regionCode": region, "maxResults": 25,
    }
    if SEARCH_LANG.get(region):
        sparams["relevanceLanguage"] = SEARCH_LANG[region]
    sres = yt_get(key, "/search", sparams).get("items", [])
    new_ids = [it["id"]["videoId"] for it in sres
               if it.get("id", {}).get("videoId") not in items_by_id]
    for i in range(0, len(new_ids), 50):
        det = yt_get(key, "/videos", {
            "part": "snippet,statistics,contentDetails",
            "id": ",".join(new_ids[i:i + 50]), "maxResults": 50,
        }).get("items", [])
        for v in det:
            items_by_id[v["id"]] = v
        time.sleep(0.3)
    # 3. SHORTS ONLY filter (YouTube Shorts <= 3 min)
    vids = [v for v in items_by_id.values()
            if parse_duration(v.get("contentDetails", {}).get("duration")) <= 185]
    # channel details (batch)
    ch_ids = list({v["snippet"]["channelId"] for v in vids})
    ch_info = {}
    for i in range(0, len(ch_ids), 50):
        batch = ch_ids[i:i + 50]
        res = yt_get(key, "/channels", {
            "part": "snippet,statistics", "id": ",".join(batch), "maxResults": 50})
        for c in res.get("items", []):
            ch_info[c["id"]] = c
        time.sleep(0.3)

    now = datetime.now(timezone.utc)
    out = []
    for v in vids:
        vid = v["id"]; sn = v["snippet"]; st = v.get("statistics", {})
        cd = v.get("contentDetails", {})
        title = sn.get("title", "")
        if title_excluded(title):
            continue  # dance / adult content nahi
        ch = ch_info.get(sn.get("channelId"), {})
        ch_sn = ch.get("snippet", {})
        ch_st = ch.get("statistics", {})
        try:
            subs = int(ch_st.get("subscriberCount") or 0)
        except Exception:
            subs = 0
        ch_age = channel_age_days(ch_sn.get("publishedAt", ""))
        if subs >= MEGA_SUBS and ch_age is not None and ch_age >= MEGA_AGE_DAYS:
            continue  # purane mega channels nahi — sirf rising stars
        dur = parse_duration(cd.get("duration"))
        desc = sn.get("description", "")[:500]
        niche = classify_niche(title + " " + desc)
        fmt = detect_format(title, desc, dur)
        gap, gap_label, gap_note = gap_assess(niche, fmt)
        try:
            pub = datetime.fromisoformat(sn.get("publishedAt", "").replace("Z", "+00:00"))
            age_d = (now - pub).days
        except Exception:
            age_d = None
        views = int(st.get("viewCount") or 0)
        viral_30d = age_d is not None and age_d <= 30 and views >= 500_000
        new_channel = ch_age is not None and ch_age <= 120 and views >= 200_000
        out.append({
            "video_id": vid, "title": title,
            "channel": sn.get("channelTitle", ""),
            "channel_id": sn.get("channelId", ""),
            "views": views, "views_fmt": fmt_views(views),
            "likes": int(st.get("likeCount") or 0),
            "published_days_ago": age_d,
            "duration_s": dur,
            "niche": niche, "format": fmt,
            "gap": gap, "gap_label": gap_label, "gap_note": gap_note,
            "viral_30d": viral_30d, "new_channel": new_channel,
            "subs": subs, "subs_fmt": fmt_views(subs), "channel_age_days": ch_age,
            "video_url": f"https://www.youtube.com/watch?v={vid}",
            "channel_url": f"https://www.youtube.com/channel/{sn.get('channelId','')}",
            "region": region,
        })
    # gaps first, phir 30-din viral, phir views
    order = {"niche_gap": 0, "format_gap": 1, "saturated": 2}
    out.sort(key=lambda x: (order[x["gap"]], not x["viral_30d"], -x["views"]))
    return out[:25]

def main():
    key = os.environ.get("YT_API_KEY", "").strip()
    today = date.today().isoformat()
    if not key:
        msg = "YT_API_KEY nahi mila — YouTube gap refresh skip (key lagao taake chale)"
        print(json.dumps({"ok": False, "message": msg}))
        return
    for region in REGIONS:
        try:
            items = build_region(key, region)
        except Exception as e:
            print(f"[{region}] fail: {e}", flush=True)
            items = []
        gaps = sum(1 for i in items if i["gap"] != "saturated")
        with open(os.path.join(DATA, f"yt_gap_{region}.json"), "w", encoding="utf-8") as f:
            json.dump({"date": today, "region": region, "items": items}, f, ensure_ascii=False, indent=2)
        print(f"[{region}] {len(items)} videos, {gaps} gap opportunities", flush=True)

if __name__ == "__main__":
    main()
