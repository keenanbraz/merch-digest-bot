import os
import requests
from flask import Flask, request, jsonify

app = Flask(__name__)

NEWS_API_KEY = os.environ.get("NEWS_API_KEY")

@app.route("/digest", methods=["POST"])
def digest():
    data = request.form
    league = data.get("text", "NFL")

    # --- Step 1: Fetch recent news ---
    url = f"https://newsapi.org/v2/everything?q={league}&language=en&sortBy=popularity&pageSize=20&apiKey={NEWS_API_KEY}"
    response = requests.get(url)
    articles = response.json().get("articles", [])

    # --- Step 2: Filtering rules ---
    good_keywords = [
        "touchdown","win","loss","comeback","record","performance",
        "mvp","rookie","trade","highlight","game","defense","offense",
        "qb","quarterback","coach","player","team","fans","score",
        "upset","victory","playoff","interception","sack","rush",
        "catch","field goal","pass","drive","overtime"
    ]
    bad_keywords = [
        "halftime","celebrity","bad bunny","taylor swift","jennifer lopez",
        "college","unc","recruiting","fantasy","betting","gossip",
        "drama","rumor","culture","politics","lawsuit","business",
        "concert","fashion","movie","tv","broadway","award","celebration",
        "charity","foundation","community","weather","ticket","raffle"
    ]

    def is_relevant(article):
        text = f"{article.get('title','')} {article.get('description','')}".lower()
        return any(k in text for k in good_keywords) and not any(k in text for k in bad_keywords)

    filtered = [a for a in articles if is_relevant(a)]
    top = filtered[:5]

    # --- Step 3: Handle no results ---
    if not top:
        return jsonify({"text": f"No trending {league} stories found this week."})

    # --- Step 4: Build Slack message ---
    text_block = f"*{league.upper()} — Weekly Digest*\n"
    text_block += "Here are this week's top trending stories across the league:\n\n"

    for a in top:
        title = a.get("title", "Untitled")
        source = a.get("source", {}).get("name", "")
        url = a.get("url", "")
        text_block += f"• <{url}|{title}> — {source}\n"

    return jsonify({"text": text_block})
