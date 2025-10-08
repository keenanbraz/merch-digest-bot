import os, re, requests
from datetime import datetime, timedelta, timezone
from flask import Flask, request, jsonify

app = Flask(__name__)
NEWS_API_KEY = os.environ.get("NEWS_API_KEY")

NFL_TEAMS = [
    "49ers","Bears","Bengals","Bills","Broncos","Browns","Buccaneers","Cardinals",
    "Chargers","Chiefs","Colts","Commanders","Cowboys","Dolphins","Eagles","Falcons",
    "Giants","Jaguars","Jets","Lions","Packers","Panthers","Patriots","Raiders",
    "Rams","Ravens","Saints","Seahawks","Steelers","Texans","Titans","Vikings"
]

STAR_PLAYERS = [
    "Patrick Mahomes","Josh Allen","Joe Burrow","Lamar Jackson","Jalen Hurts",
    "Tua Tagovailoa","CeeDee Lamb","Micah Parsons","Justin Jefferson","Tyreek Hill",
    "Aaron Rodgers","Trevor Lawrence","Caleb Williams","Marvin Harrison","Brock Purdy",
    "Christian McCaffrey","Saquon Barkley","Aidan Hutchinson","Garrett Wilson"
]

SPORT_SITES = [
    "espn","nfl.com","sports","yardbarker","bleacherreport","si.com","nbcsports",
    "foxsports","cbssports","usatoday","yahoo","theathletic","sportsillustrated",
    "apnews","newsweek","reuters","guardian","nytimes","washingtonpost","nbcnews","bbc"
]

GOOD_TERMS = [
    "touchdown","record","rookie","contract","extension","trade","signed","win","loss",
    "highlight","jersey","sideline","uniform","throwback","helmet","clutch","playoffs",
    "game","comeback","blowout","thriller","mvp","debut","sack","interception","victory"
]

INJURY_TERMS = [
    "injury","acl","mcl","hamstring","concussion","groin","achilles","ir","out for season",
    "day-to-day","questionable","doubtful","injured reserve"
]

TIMEFRAME_MAP = {"today":1,"yesterday":1,"week":7,"month":30}

# ---------------- Helpers ---------------- #

def parse_cmd(txt):
    parts = txt.strip().split()
    league = "NFL"; days = 7
    if len(parts) > 0:
        league = parts[0].upper()
    if len(parts) > 1:
        tf = parts[1].lower()
        days = int(tf) if tf.isdigit() else TIMEFRAME_MAP.get(tf, 7)
    return league, days

def fetch_news(days):
    """Fetch news and enforce freshness manually."""
    now = datetime.now(timezone.utc)
    from_date = (now - timedelta(days=days))
    to_date = now
    month_year = now.strftime("%B %Y")  # e.g. 'October 2025'

    query = (
        f"(NFL OR National Football League OR football) AND "
        f"(game OR win OR loss OR highlights OR touchdown OR trade OR injury OR rookie OR contract OR coach OR playoffs OR score) "
        f"AND \"{month_year}\""
    )

    url = (
        f"https://newsapi.org/v2/everything?"
        f"q={query}&"
        f"language=en&"
        f"from={from_date.strftime('%Y-%m-%d')}&"
        f"to={to_date.strftime('%Y-%m-%d')}&"
        f"sortBy=publishedAt&"
        f"pageSize=80&"
        f"apiKey={NEWS_API_KEY}"
    )

    r = requests.get(url, timeout=10)
    r.raise_for_status()
    articles = r.json().get("articles", [])

    # manually verify date window
    fresh = []
    for a in articles:
        try:
            pub = datetime.fromisoformat(a["publishedAt"].replace("Z","+00:00"))
            if from_date <= pub <= to_date:
                fresh.append(a)
        except Exception:
            continue
    return fresh

def is_sports_site(url):
    return any(x in url.lower() for x in SPORT_SITES)

def has_team_or_player(text):
    t = text.lower()
    return any(team.lower() in t for team in NFL_TEAMS) or any(p.lower() in t for p in STAR_PLAYERS)

def is_injury(text):
    return any(k in text.lower() for k in INJURY_TERMS)

def score_story(a):
    t = f"{a.get('title','')} {a.get('description','')}".lower()
    score = 0
    if has_team_or_player(t): score += 2
    if any(k in t for k in GOOD_TERMS): score += 1
    if "rookie" in t or "record" in t or "trade" in t: score += 1
    return score

def tag_story(a):
    t = a.get("title","").lower()
    if "trade" in t or "extension" in t or "signed" in t:
        return "WATCH"
    if "record" in t or "highlight" in t or "comeback" in t or "thriller" in t:
        return "HOT"
    if "rookie" in t or "debut" in t:
        return "WATCH"
    return "EVERGREEN"

# ---------------- Slack Command ---------------- #

@app.route("/digest", methods=["POST"])
def digest():
    if not NEWS_API_KEY:
        return jsonify({"text": "Missing NEWS_API_KEY"})

    league, days = parse_cmd(request.form.get("text", "NFL 7"))
    if league != "NFL":
        return jsonify({"text": "Only NFL supported currently."})

    articles = fetch_news(days)
    keep = []
    for a in articles:
        full = f"{a.get('title','')} {a.get('description','')}"
        url = a.get("url", "")
        if not is_sports_site(url):
            continue
        if not has_team_or_player(full):
            continue
        sc = score_story(a)
        if sc >= 2:  # slightly looser threshold
            keep.append((sc, a))

    keep = sorted(keep, key=lambda x: x[0], reverse=True)[:12]
    if not keep:
        return jsonify({"text": f"No recent NFL items found in past {days} days."})

    trending, inj = [], []
    for sc, a in keep:
        if is_injury(a.get("title","") + a.get("description","")):
            inj.append(a)
        else:
            trending.append(a)

    now = datetime.now().strftime("%b %d, %Y")
    start = (datetime.now() - timedelta(days=days)).strftime("%b %d")
    lines = []
    lines.append(f"*🏈 NFL Buzz — Past {days} Days* _(from {start} to {now})_")
    lines.append(f"> _{len(trending)} trending stories found._\n")

    if trending:
        lines.append("*🔥 Trending Stories*")
        for a in trending:
            title = a.get("title", "")
            src = a.get("source", {}).get("name", "")
            url = a.get("url", "")
            desc = a.get("description", "") or "No description available"
            tag = tag_story(a)
            tag_emoji = "🔥" if tag == "HOT" else "👀" if tag == "WATCH" else "🕐"
            lines.append(
                f"• *<{url}|{title}>*  \n"
                f"_{desc}_  \n"
                f"{tag_emoji} `{tag}` — *{src}*\n"
            )

    if inj:
        lines.append("\n*🩹 Injury Watch*")
        for a in inj:
            title = a.get("title", "")
            src = a.get("source", {}).get("name", "")
            url = a.get("url", "")
            lines.append(f"• *<{url}|{title}>* — _{src}_")

    return jsonify({
        "response_type": "in_channel",
        "text": "\n".join(lines)
    })

@app.route("/ping")
def ping():
    return "OK", 200
