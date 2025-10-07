import os
import requests
from flask import Flask, request, jsonify

app = Flask(__name__)

NEWS_API_KEY = os.getenv("NEWS_API_KEY")

@app.route("/digest", methods=["POST"])
def digest():
    data = request.form
    text = data.get("text", "").strip() or "NFL 7"

    # Parse league and timeframe
    parts = text.split()
    league = parts[0].upper() if len(parts) > 0 else "NFL"
    days = parts[1] if len(parts) > 1 else "7"

    # Map league to keywords for the API
    league_keywords = {
        "NFL": ["NFL", "football", "quarterback", "Super Bowl"],
        "NBA": ["NBA", "basketball", "LeBron", "Steph Curry"],
        "MLB": ["MLB", "baseball", "World Series"],
        "NHL": ["NHL", "hockey", "Stanley Cup"]
    }
    keywords = league_keywords.get(league, ["sports"])

    # Build query
    query = " OR ".join(keywords)
    url = (
        f"https://newsapi.org/v2/everything?"
        f"q={query}&pageSize=5&sortBy=publishedAt&language=en&apiKey={NEWS_API_KEY}"
    )
    response = requests.get(url)
    articles = response.json().get("articles", [])

    if not articles:
        return jsonify({
            "response_type": "ephemeral",
            "text": f"No recent {league} merch stories found in the past {days} days."
        })

    # Format results
    summary = f"*{league} — Top {len(articles)} Stories (last {days} days)*"
    formatted = []
    for art in articles:
        title = art["title"]
        source = art["source"]["name"]
        url = art["url"]
        formatted.append(f"• <{url}|{title}> — {source}")

    message = f"{summary}\n\n" + "\n".join(formatted)

    return jsonify({
        "response_type": "in_channel",
        "text": message
    })


@app.route("/ping")
def ping():
    return "ok", 200

@app.route("/health")
def health():
    return jsonify(status="ok", service="merch-digest-bot"), 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
