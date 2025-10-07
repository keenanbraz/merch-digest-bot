from flask import Flask, request, jsonify

app = Flask(__name__)

# ---------- Slack Slash Command Route ----------
@app.route("/digest", methods=["POST"])
def digest():
    # Slack sends form-encoded data when you run /digest in Slack
    data = request.form
    text = data.get("text", "").strip()  # e.g. "NFL 7"

    # Parse command input
    if not text:
        return jsonify(
            response_type="ephemeral",
            text="Usage: `/digest [LEAGUE] [DAYS]` (e.g. `/digest NFL 7`)"
        )

    parts = text.split()
    league = parts[0].upper() if len(parts) > 0 else "NFL"
    days = parts[1] if len(parts) > 1 else "7"

    # Mock response for now — you can later replace this with live logic
    summary = f"*{league} merch stories for past {days} days*"
    trending = [
        "⭐ Patrick Mahomes — HOT — Postgame outfit went viral",
        "🔥 C.J. Stroud — HOT — Career-high passing day driving jersey sales",
        "💎 49ers Sideline Hoodie — EVERGREEN — Trending strong since Week 1",
    ]

    message = f"{summary}\n\n" + "\n".join(trending)

    # Slack expects JSON with a 3-second response limit
    return jsonify({
        "response_type": "in_channel",
        "text": message
    })


# ---------- Keep-Alive Route for UptimeRobot ----------
@app.route("/ping")
def ping():
    return "ok", 200


# ---------- Optional: Health Check Route ----------
@app.route("/health")
def health():
    return jsonify(status="ok", service="merch-digest-bot"), 200


# ---------- Run Locally ----------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
