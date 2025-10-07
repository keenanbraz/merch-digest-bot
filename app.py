import os
import requests
from flask import Flask, request, jsonify
from openai import OpenAI

app = Flask(__name__)
client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
NEWS_API_KEY = os.environ.get("NEWS_API_KEY")

@app.route("/digest", methods=["POST"])
def digest():
    data = request.form
    league = data.get("text", "NFL")

    # --- Step 1: Fetch articles ---
    url = f"https://newsapi.org/v2/everything?q={league}&language=en&sortBy=popularity&pageSize=15&apiKey={NEWS_API_KEY}"
    response = requests.get(url)
    articles = response.json().get("articles", [])

    # --- Step 2: Filtering ---
    good_keywords = [
        "touchdown","win","loss","comeback","record","performance",
        "injury","mvp","rookie","trade","extension","contract",
        "highlight","game","defense","offense","qb","coach",
        "player","team","fans","score","upset","victory","clinched","playoff"
    ]
    bad_keywords = [
        "halftime","celebrity","bad bunny","taylor swift","jennifer lopez",
        "beyonce","rihanna","college","unc","recruiting","fantasy","betting",
        "gossip","drama","rumor","culture","politics","business","lawsuit"
    ]

    def is_relevant(article):
        text = f"{article.get('title','')} {article.get('description','')}".lower()
        return any(k in text for k in good_keywords) and not any(k in text for k in bad_keywords)

    filtered = [a for a in articles if is_relevant(a)]
    top = filtered[:5]

    if not top:
        return jsonify({"text": f"No relevant {league} stories found this week."})

    # --- Step 3: Summarize with AI ---
    headlines = "\n".join([f"- {a.get('title', '')}" for a in top])
    prompt = f"""
    You're an NFL merch and culture analyst writing a weekly digest for Fanatics' NFL Shop team.
    Summarize these headlines into 3-5 lively sentences that capture the storylines and energy
    of the week, using a fun, professional tone (like ChatGPT or a sports editor).
    Headlines:
    {headlines}
    """

    ai_summary = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=250
    ).choices[0].message.content.strip()

    # --- Step 4: Format Slack message ---
    text_block = f"*{league.upper()} — Weekly AI Digest*\n{ai_summary}"
    for a in top:
        title = a.get("title", "Untitled")
        source = a.get("source", {}).get("name", "")
        url = a.get("url", "")
        text_block += f"\n• <{url}|{title}> — {source}"

    return jsonify({"text": text_block})
