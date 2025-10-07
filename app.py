from flask import Flask, request, jsonify

app = Flask(__name__)

# --- Mock digest generator ---
def generate_digest(league: str, days: int) -> str:
    return f"""
📊 {league.upper()} Digest (Past {days} Days)

Summary: Rookie breakouts and big injuries driving merch buzz.

🔥 Trending
- Patrick Mahomes — 4 TDs (HOT)
- Bo Nix — Rookie MNF breakout (HOT)

❌ Injuries
- Tyreek Hill (MIA) — Season-ending knee (HOT)

👀 Players to Feature
Mahomes (HOT), Bo Nix (HOT)
    """.strip()

@app.route("/digest", methods=["POST"])
def digest():
    text = request.form.get("text", "").strip()
    if not text:
        return jsonify({
            "response_type": "ephemeral",
            "text": "Usage: /digest [league] [days] (e.g., /digest NFL 7)"
        })

    parts = text.split()
    if len(parts) < 2:
        return jsonify({
            "response_type": "ephemeral",
            "text": "Please provide league and days. Example: /digest NFL 7"
        })

    league, days = parts[0], int(parts[1])
    digest_text = generate_digest(league, days)

    return jsonify({
        "response_type": "in_channel",
        "text": digest_text
    })

if __name__ == "__main__":
    app.run(port=5000, debug=True)
