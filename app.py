import os, re, html, math, requests
from datetime import datetime, timedelta, timezone
from flask import Flask, request, jsonify

app = Flask(__name__)

NEWS_API_KEY = os.environ.get("NEWS_API_KEY")

# -------------------------- NFL-Specific Vocabulary -------------------------- #

GOOD_TERMS_NFL = [
    # On-field results & moments
    "touchdown", "pick-six", "sack", "strip-sack", "fumble", "interception",
    "field goal", "fg", "extra point", "overtime", "walk-off", "comeback", "4th down",
    "two-point", "drive", "clutch", "highlight", "viral", "record", "career high",
    "historic", "franchise record", "milestone", "clinched", "playoff", "seed",
    # Player / transaction buzz
    "mvp", "rookie", "debut", "breakout", "contract", "extension", "trade", "signed",
    "waived", "released", "highlight", "fans", "jersey", "hat", "uniform", "sideline",
    "throwback", "alternate", "helmet", "gear", "apparel", "drop", "merch",
    # Positions
    "quarterback", "qb", "receiver", "rusher", "linebacker", "cornerback", "safety",
    "defense", "offense", "special teams", "kicker", "punter", "tight end"
]

BAD_TERMS_NFL = [
    # Pop culture
    "halftime", "celebrity", "bad bunny", "taylor swift", "jennifer lopez", "concert",
    "fashion", "met gala", "grammy", "oscars", "reality tv", "rumor", "gossip", "dating",
    # College / unrelated sports
    "college", "ncaa", "unc", "recruiting", "high school", "march madness", "basketball",
    "baseball", "mlb", "nba", "nhl", "soccer", "golf", "ufc", "mma", "tennis",
    # Betting / business / misc
    "fantasy", "betting", "odds", "parlay", "sportsbook", "ratings", "sponsorship",
    "endorsement", "broadcast rights", "ticket giveaway", "raffle", "weather", "travel"
]

INJURY_TERMS_NFL = [
    "injury", "hurt", "out for season", "acl", "mcl", "achilles", "hamstring", "groin",
    "concussion", "fracture", "sprain", "placed on ir", "designated to return",
    "day-to-day", "questionable", "doubtful", "out sunday", "ruled out", "status"
]

TIMEFRAME_MAP = {"today":1, "yesterday":1, "week":7, "month":30, "year":365}

# ------------------------------- Helper Functions ------------------------------ #

def parse_command(text: str):
    text = (text or "NFL 7").strip()
    parts = text.split()
    league = parts[0].upper() if parts else "NFL"
    if len(parts) > 1 and not parts[1].startswith("watch="):
        tf = parts[1].lower()
        days = int(tf) if tf.isdigit() else TIMEFRAME_MAP.get(tf, 7)
    else:
        days = 7
    watchlist = set()
    m = re.search(r"watch=([^ ]+)", text, flags=re.IGNORECASE)
    if m:
        watchlist = {w.strip().lower() for w in m.group(1).split(",") if w.strip()}
    return league, days, watchlist

def newsapi_fetch(days: int):
    from_date = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")
    query = "NFL OR football OR quarterback OR playoffs OR touchdown"
    url = (
        f"https://newsapi.org/v2/everything?q={requests.utils.quote(query)}"
        f"&language=en&sortBy=publishedAt&pageSize=50&from={from_date}&apiKey={NEWS_API_KEY}"
    )
    r = requests.get(url, timeout=15)
    r.raise_for_status()
    return r.json().get("articles", [])

def has_any(text: str, terms: list[str]): return any(t in text.lower() for t in terms)
def is_injury_story(text: str): return has_any(text, INJURY_TERMS_NFL)

def classify_category(text: str):
    t = text.lower()
    if any(k in t for k in ["trade", "signed", "extension", "acquire", "waived"]): return "Transaction"
    if is_injury_story(t): return "Injury"
    if any(k in t for k in ["podcast", "mic'd up", "interview", "broadcast", "media"]): return "Media"
    return "Player" if any(k in t for k in ["qb","quarterback","receiver","coach","mvp","rookie"]) else "Team/Story"

def merchandise_reason(text: str):
    t = text.lower()
    if "record" in t or "career high" in t: return "Record-breaking performance boosting jersey sales."
    if "rookie" in t or "debut" in t: return "Rookie buzz driving first-wave merch demand."
    if "comeback" in t or "walk-off" in t: return "Clutch win fueling highlight tee interest."
    if "trade" in t or "extension" in t: return "Roster move triggering jersey/nameplate spikes."
    if "throwback" in t or "uniform" in t: return "Alternate uniform or sideline piece trending with fans."
    return "Performance-driven story increasing fan demand."

def score_item(title: str, desc: str, watchlist_lower: set[str]):
    text = f"{title} {desc}".lower()
    score = 0
    if has_any(text, GOOD_TERMS_NFL): score += 2
    if any(w in text for w in watchlist_lower): score += 1
    return score

def action_tag(published_at: str, title_desc: str):
    try:
        dt = datetime.fromisoformat(published_at.replace("Z","+00:00"))
    except Exception:
        dt = datetime.now(timezone.utc)
    age_hours = (datetime.now(timezone.utc) - dt).total_seconds() / 3600
    t = title_desc.lower()
    if age_hours <= 24 and has_any(t, ["record","walk-off","comeback","viral","hat trick"]): return "HOT"
    if age_hours <= 7*24 and has_any(t, ["rookie","injury","trade","signed","extension"]): return "WATCH"
    return "EVERGREEN"

def dedupe(arts):
    seen=set();out=[]
    for a in arts:
        key=re.sub(r"[^a-z0-9]+","",(a.get("title","")+a.get("description","")).lower())
        if key and key not in seen: seen.add(key);out.append(a)
    return out

def filter_merch_relevant(arts):
    filtered=[]
    for a in arts:
        t=f"{a.get('title','')} {a.get('description','')}"
        if has_any(t,BAD_TERMS_NFL): continue
        if has_any(t,GOOD_TERMS_NFL) or classify_category(t)!="": filtered.append(a)
    return filtered

# -------------------------------- Slack Endpoint ------------------------------- #

@app.route("/digest", methods=["POST"])
def digest():
    if not NEWS_API_KEY:
        return jsonify({"response_type":"ephemeral","text":"Missing NEWS_API_KEY."})

    league, days, watchlist = parse_command(request.form.get("text", ""))
    if league != "NFL":
        return jsonify({"text": "Only NFL supported in this version."})

    try:
        raw = newsapi_fetch(days)
    except Exception as e:
        return jsonify({"text": f"Fetch error: {e}"})

    cleaned = filter_merch_relevant(raw)
    deduped = dedupe(cleaned)

    trending=[];injuries=[]
    for a in deduped:
        title=a.get("title","");desc=a.get("description","");text=f"{title} {desc}"
        cat=classify_category(text)
        if cat=="Injury": injuries.append(a); continue
        sc=score_item(title,desc,watchlist)
        if sc>=2: trending.append(a)

    if not trending and not injuries:
        return jsonify({"text":"No NFL-related items in this time frame."})

    trending=sorted(trending,key=lambda a:a.get("publishedAt",""),reverse=True)[:10]
    injuries=[a for a in injuries if any(k in (a.get("title","")+a.get("description","")).lower() for k in ["qb","starter","mvp","star"])]

    def build_summary():
        hot=sum(1 for a in trending if action_tag(a.get("publishedAt",""),a.get("title",""))=="HOT")
        rook=sum(1 for a in trending if "rookie" in (a.get("title","")+a.get("description","")).lower())
        dev=sum(1 for a in trending if action_tag(a.get("publishedAt",""),a.get("title",""))=="WATCH")
        parts=[]
        if hot:parts.append(f"{hot} HOT storylines")
        if dev:parts.append(f"{dev} developing stories")
        if rook:parts.append(f"{rook} rookie buzz")
        return f"NFL buzz in the past {days} days: " + (", ".join(parts) if parts else "on-field and roster movement driving fan interest.")

    def format_story(a):
        title=a.get("title","");src=a.get("source",{}).get("name","");url=a.get("url","")
        desc=a.get("description","");cat=classify_category(f"{title} {desc}")
        reason=merchandise_reason(f"{title} {desc}")
        tag=action_tag(a.get("publishedAt",""),f"{title} {desc}")
        wl=" (watchlist hit)" if any(w in (title+desc).lower() for w in watchlist) else ""
        return f"{title} — {cat}. {reason}{wl} [{tag}] — {src} — <{url}|source>"

    lines=[f"*Summary:* {build_summary()}"]
    if trending:
        lines.append("*Trending List*")
        for a in trending: lines.append(format_story(a))
    if injuries:
        lines.append("*Injuries (Important Players)*")
        for a in injuries:
            title=a.get("title","");url=a.get("url","");src=a.get("source",{}).get("name","")
            lines.append(f"{title} — injury update — {src} — <{url}|source>")
    return jsonify({"response_type":"in_channel","text":"\n".join(lines)})

@app.route("/ping", methods=["GET","HEAD"])
def ping(): return "OK",200
