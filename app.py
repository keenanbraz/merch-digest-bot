import os, requests
from datetime import datetime, timedelta, timezone
from flask import Flask, request, jsonify

app = Flask(__name__)
NEWS_API_KEY = os.environ.get("NEWS_API_KEY")

# ---------------- NFL Reference Data ---------------- #
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
    "apnews","newsweek","reuters","guardian","nytimes","washingtonpost","bbc"
]

GOOD_TERMS = [
    "touchdown","record","rookie","contract","extension","trade","signed","win","loss",
    "highlight","jersey","sideline","uniform","throwback","helmet","clutch","playoffs",
    "game","comeback","blowout","thriller","mvp","debut","sack","interception","victory",
    "fantasy","ranking","power ranking","offense","defense","quarterback","score"
]

INJURY_TERMS = [
    "injury","acl","mcl","hamstring","concussion","groin","achilles","ir","out for season",
    "day-to-day","questionable","doubtful","injured reserve"
]

TIMEFRAME_MAP = {"today":1,"yesterday":1,"week":7,"month":30}

# ---------------- Helper Functions ---------------- #
def parse_cmd(txt):
    """Extract league and timeframe from the Slack command"""
    parts = txt.strip().split()
    league = "NFL"
    days = 7
    if len(parts) > 0:
        league = parts[0].upper()
    if len(parts) > 1:
        tf = parts[1].lower()
        days = int(tf) if tf.isdigit() else TIMEFRAME_MAP.get(tf, 7)
    return league, days

def fetch_news(days):
    """Fetch news articles from the last X days related to NFL"""
    now = datetime.now(timezone.utc)
    from_date = now - timedelta(days=days)

    query = (
        "(NFL OR \"National Football League\" OR \"pro football\" "
        "OR quarterback OR wide receiver OR touchdown OR trade OR injury OR game OR highlights)"
    )

    url = (
        f"https://newsapi.org/v2/everything?"
        f"q={query}&language=en&from={from_date.strftime('%Y-%m-%d')}&"
        f"sortBy=publishedAt&pageSize=100&apiKey={NEWS_API_KEY}"
    )

    r = requests.get(url, timeout=5)
    r.raise_for_status()
    articles = r.json().get("articles", [])

    fresh = []
    for a in articles:
        title = a.get("title", "").lower()
        desc = a.get("description", "").lower()
        pub = a.get("publishedAt", "")
        try:
            pub_dt = datetime.fromisoformat(pub.replace("Z", "+00:00"))
            if pub_dt < from_date:
                continue
        except Exception:
            continue

        # Must be NFL-related or contain a team/player name
        nfl_context = (
            "nfl" in title or "nfl" in desc or "fantasy football" in title
            or any(team.lower() in title for team in NFL_TEAMS)
            or any(player.lower() in title for player in STAR_PLAYERS)
        )

        # Exclude college / non-NFL sports
        bad_signals = any(k in title for k in [
            "college", "ncaa", "recruit", "high school", "draft prospect", "UNC", "Penn State", "Alabama"
        ])

        if nfl_context and not bad_signals:
            fresh.append(a)

    return fresh

def is_sports_site(url): return any(x in url.lower() for x in SPORT_SITES)
def is_injury(text): return any(k in text.lower() for k in INJURY_TERMS)

def score_story(a):
    """Assign a simple relevancy score to a story"""
    t = f"{a.get('title','')} {a.get('description','')}".lower()
    score = 0
    if any(team.lower() in t for team in NFL_TEAMS): score += 2
    if any(k in t for k in GOOD_TERMS): score += 1
    if "nfl" in t or "fantasy" in t: score += 1
    return score

def tag_story(a):
    """Classify stories into merch-action categories"""
    t = a.get("title","").lower()
    if "trade" in t or "extension" in t or "signed" in t:
        return "WATCH"
    if "record" in t or "highlight" in t or "comeback" in t or "win" in t:
        return "HOT"
    if "rookie" in t or "debut" in t:
        return "WATCH"
    return "EVERGREEN"

# ---------------- Slack Digest Endpoint ---------------- #
@app.route("/digest", methods=["POST"])
def digest():
    try:
        if not NEWS_API_KEY:
            return jsonify({"response_type": "ephemeral", "text": "⚠️ Missing NEWS_API_KEY"})

        text = request.form.get("text", "").strip()
        league, days = parse_cmd(text if text else "NFL 7")
        debug_mode = "debug" in text.lower()

        if league != "NFL":
            return jsonify({"response_type": "ephemeral", "text": "Only NFL supported currently."})

        try:
            articles = fetch_news(days)
        except Exception as e:
            return jsonify({"response_type": "ephemeral", "text": f"❌ Error fetching news: {str(e)}"})

        total_fetched = len(articles)
        keep = []
        for a in articles:
            url = a.get("url", "")
            if not is_sports_site(url):
                continue
            sc = score_story(a)
            if sc >= 2:
                keep.append((sc, a))

        total_kept = len(keep)
        if not keep:
            return jsonify({"response_type": "in_channel", "text": f"No NFL items found in past {days} days."})

        keep = sorted(keep, key=lambda x: x[0], reverse=True)[:15]
        trending, inj = [], []
        for sc, a in keep:
            if is_injury(a.get("title","") + a.get("description","")):
                inj.append(a)
            else:
                trending.append(a)

        now = datetime.now().strftime("%b %d, %Y")
        start = (datetime.now() - timedelta(days=days)).strftime("%b %d")

        lines = [f"*🏈 NFL Buzz — Past {days} Days* _(from {start} to {now})_"]
        lines.append(f"> _{len(trending)} trending stories found._\n")

        if debug_mode:
            lines.append(f"🧩 *Debug Info:* fetched={total_fetched}, kept={total_kept}, injuries={len(inj)}\n")

        if trending:
            lines.append("*🔥 Trending Stories*")
            for a in trending:
                title = a.get("title", "")
                src = a.get("source", {}).get("name", "")
                url = a.get("url", "")
                desc = a.get("description", "") or "No description available"
                pub = a.get("publishedAt", "")
                try:
                    pub_dt = datetime.fromisoformat(pub.replace("Z", "+00:00"))
                    pub_str = pub_dt.strftime("%b %d")
                except:
                    pub_str = "Recent"
                tag = tag_story(a)
                tag_emoji = "🔥" if tag == "HOT" else "👀" if tag == "WATCH" else "🕐"
                lines.append(
                    f"• *<{url}|{title}>*  \n"
                    f"_{desc}_  \n"
                    f"🗓️ {pub_str} | {tag_emoji} `{tag}` — *{src}*\n"
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

    except Exception as e:
        return jsonify({"response_type": "ephemeral", "text": f"⚠️ Error: {e}"})

# ---------------- Health Check ---------------- #
@app.route("/ping")
def ping():
    return "OK", 200
