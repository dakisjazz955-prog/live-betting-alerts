# Live Betting Alerts — first mobile prototype

A mobile-friendly Flask page for initial Render deployment and Android Chrome notification testing.

## What works
- Web app with a Greek mobile interface.
- Health check at `/health`.
- Test notification through a service worker when the page is opened in a compatible browser over HTTPS, after permission is granted.
- Honest empty response at `/api/alerts` (no live data is connected).

## Not implemented yet
- Live football / basketball feeds, bookmaker odds or filtering models.
- Background automated alerts when the site is closed.
- Automated bets (not part of the product).

## Render setup
1. Upload `app.py`, `requirements.txt`, and `render.yaml` to the repository root, along with this README.
2. In Render choose **New > Web Service** and connect this GitHub repository.
3. Use Python, build command `pip install -r requirements.txt`, and start command `gunicorn --bind 0.0.0.0:$PORT app:app` if Render does not read `render.yaml` automatically.
4. Open the assigned HTTPS URL using Chrome on Android, allow notifications, and tap **Δοκιμαστική ειδοποίηση**.

## Next stage
Integrate a legitimate sports data / odds provider and implement server-side Web Push subscriptions to send real notifications without keeping the site open. Do not store provider credentials in the public repository.
