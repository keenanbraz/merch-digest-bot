import os
import requests
from datetime import datetime, timedelta
from flask import Flask, request, jsonify

app = Flask(__name__)

NEWS_API_KEY = os.environ.get("NEWS_API_KEY")

@app.route("/digest", methods=["POST"])
def digest():
    data = request.form
    text = data.get("text", "NFL 7")  # Default command text
    parts = text.split()

    # --- Step 1: Parse league and timeframe ---
    league = parts[0] if len(parts) > 0 else "NFL"
    timeframe = parts[1].lower() if len(parts) > 1 else "7"

    # Convert natural language into days
    timeframe_map = {
        "today": 1,
        "yesterday": 1,
        "week": 7,
        "month": 30,
        "year": 365
    }

    # Determine number of days
    if timeframe.isdigit():
        days = int(timeframe)
    elif timeframe in timeframe_map:
        days = timeframe_map[timeframe]
    else:
        days = 7  # fallback default

    # --- Step 2: Build date-filtered NewsAPI request ---
    from_date = (datetime.utcnow() - timedelta(days=days)).strftime("%Y-%m-%d")
    url = (
        f"https://newsapi.org/v2/everything?"
        f"q={league}&language=en&sortBy=publishedAt&pageSize=20&from={from_date}"
        f"&apiKey={NEWS_API_KEY}"
    )
    response = requests.get(url)
    articles = response.json().get("articles", [])

    # --- Step 3: Filtering rules ---
    good_keywords = [
        "touchdown", "win", "loss", "comeback", "record", "performance",
        "mvp", "rookie", "trade", "highlight", "game", "defense", "offense",
        "qb", "quarterback", "coach", "player", "team", "fans", "score",
        "upset", "victory", "playoff", "interception", "sack", "rush",
        "catch", "field goal", "pass", "drive", "overtime"
    ]

    bad_keywords = [
        # Pop culture & entertainment
        "halftime", "celebrity", "bad bunny", "taylor swift", "jennifer lopez",
        "beyonce", "rihanna", "fashion", "music", "concert", "award", "movie",
        # College / unrelated sports
        "college", "unc", "recruiting", "ncaa", "basketball", "baseball",
        "hockey", "soccer", "ufc", "mma", "tennis", "golf", "mlb", "nba", "nhl",
        # Off-field / gossip / business
        "fantasy", "betting", "wager", "odds", "drama", "rumor", "culture",
        "politics", "lawsuit", "investigation", "arrest", "ownership", "union",
        "sponsorship", "endorsement", "contract extension", "business deal",
        # Misc
        "charity", "foundation", "community", "weather", "raffle", "ticket"
    ]

    def is_relevant(article):
        text = f"{article.get('title', '')} {article.get('description', '')}".lower()
        return any(k in text for k in good_keywords) and not any(k in text for k in bad_keywords)

    # --- Step 4: Apply filters ---
    filtered = [a for a in articles if is_relevant(a)]
    top = filtered[:5]

    # --- Step 5: Handle empty results ---
    if not top:
        return jsonify({"text": f"No trending {league} stories found in the past {days} days."})

    # --- Step 6: Build Slack message ---
    text_block = f"*{league.upper()} — {days}-Day Digest*\n"
    text_block += "Here are the top trending stories across the league:\n\n"

    for a in top:
        title = a.get("title", "Untitled")
        source = a.get("source", {}).get("name", "")
        url = a.get("url", "")
        text_block += f"• <{url}|{title}> — {source}\n"

    return jsonify({"text": text_block})

@app.route("/ping", methods=["GET", "HEAD"])
def ping():
    return "OK", 200
