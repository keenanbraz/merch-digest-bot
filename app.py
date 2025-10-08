import os, re, requests
from datetime import datetime, timedelta, timezone
from flask import Flask, request, jsonify

app = Flask(__name__)

NEWS_API_KEY = os.environ.get("NEWS_API_KEY")

# ---------------------- NFL keywords and team/player lists ---------------------- #

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
    "foxsports","cbssports","usatoday","yahoo","theathletic","sportsillustrated"
]

GOOD_TERMS = [
    "touchdown","record","rookie","contract","extension","trade","signed","win","loss",
    "highlight","jersey","sideline","uniform","throwback","helmet","clutch","playoffs",
    "game","comeback","blowout","thriller","mvp","debut","sack","interception"
]

INJURY_TERMS = [
    "injury","acl","mcl","hamstring","concussion","groin","achilles","ir","out for season",
    "day-to-day","questionable","doubtful"
]

TIMEFRAME_MAP = {"today":1,"yesterday":1,"week":7,"month":30}

# --------------------------- Helper functions --------------------------- #

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
    from_date = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")
    url = (
        f"https://newsapi.org/v2/everything?"
        f"q=NFL%20football&language=en&sortBy=publishedAt&pageSize=50&from={from_date}"
        f"&apiKey={NEWS_API_KEY}"
    )
    r = requests.get(url, timeout=10)
    r.raise_for_status()
    return r.json().get("articles", [])

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
    if "rookie" in t: score += 1
    if "trade" in t or "signed" in t: score += 1
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

# --------------------------- Slack endpoint --------------------------- #

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
        if sc >= 3:
            keep.append((sc, a))

    keep = sorted(keep, key=lambda x: x[0], reverse=True)[:10]
    if not keep:
        return jsonify({"text": "No NFL-related items found."})

    trending = []
    inj = []
    for sc, a in keep:
        if is_injury(a.get("title","") + a.get("description","")):
            inj.append(a)
        else:
            trending.append(a)

    # ------------------- CLEANER SLACK OUTPUT ------------------- #
    lines = []
    lines.append(f"*🏈 NFL Buzz — Past {days} Days*")
    lines.append(f"> _{len(trending)} trending stories found._\n")

    if trending:
        lines.append("*🔥 Trending Stories*")
        for a in trending:
            title = a.get("title", "")
            src = a.get("source", {}).get("name", "")
            url = a.get("url", "")
            desc = a.get("description", "") or "No description"
            tag = tag_story(a)
            tag_emoji = "🔥" if tag == "HOT" else "👀" if tag == "WATCH" else "🕐"
            lines.append(
                f"• *<{url}|{title}>*  \n"
                f"_{desc}_  \n"
                f"{tag_emoji} `{tag}` — *{src}*\n"
            )

    if inj:
        lines.append("\n*🚑 Injury Updates*")
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
