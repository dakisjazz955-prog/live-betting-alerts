
import os
from flask import Flask, jsonify
from live_feed import fetch_live, FeedError

app = Flask(__name__)

@app.route("/")
def home():
    return "Live Betting Alerts is running!"

@app.route("/health")
def health():
    return jsonify(status="ok")

@app.route("/live/<mode>")
def live(mode):
    if mode not in ("football", "basketball", "odds"):
        return jsonify(error="Invalid mode"), 400

    try:
        return jsonify(fetch_live(mode))
    except FeedError as exc:
        return jsonify(error=str(exc)), 502

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
