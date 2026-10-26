"""Live Betting Alerts — a deployable mobile prototype.

This first version does NOT collect real-time scores or bookmaker prices.
Browser notifications can be tested while visiting the site.
Automated background alerts require a licensed data source and web-push setup.
"""
import os
from flask import Flask, jsonify, Response, render_template_string

app = Flask(__name__)

PAGE = r"""<!doctype html>
<html lang="el">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
  <meta name="theme-color" content="#101b20">
  <title>Live Betting Alerts</title>
  <style>
    :root { color-scheme: dark; font-family: system-ui,-apple-system,'Segoe UI',sans-serif; }
    body { margin:0; background:#101b20; color:#f5f7f7; }
    .shell { max-width:580px; margin:0 auto; padding:28px 20px 45px; }
    h1 { font-size:30px; line-height:1.12; letter-spacing:-.7px; margin:24px 0 12px; }
    p { color:#b5c2c5; line-height:1.6; }
    .eyebrow { color:#6ce6b4; font-size:12px; font-weight:800; letter-spacing:2px; }
    .card { background:#1c2a30; border:1px solid #33434b; border-radius:18px; padding:19px; margin-top:16px; }
    .line { display:flex; align-items:center; justify-content:space-between; gap:12px; }
    .tag { color:#ffd796; background:#4a3921; padding:5px 10px; border-radius:20px; font-size:12px; }
    h2 { font-size:17px; margin:0 0 9px; }
    .muted { color:#b5c2c5; font-size:14px; }
    .number { font-size:28px; font-weight:800; margin:7px 0; }
    .buttons { display:grid; gap:10px; margin-top:18px; }
    button { border:0; border-radius:12px; padding:15px 17px; font-size:15px; font-weight:750; cursor:pointer; }
    .primary { background:#69e5b3; color:#10241c; }
    .secondary { color:#f3faf7; background:#2f474e; }
    #feedback { min-height:20px; font-size:14px; color:#b7f5d9; }
    .notice { border-left:3px solid #f3b95c; padding:10px 13px; background:#2d2925; font-size:13px; color:#e7d9c7; }
    .foot { font-size:12px; padding-top:14px; }
  </style>
</head>
<body>
<main class="shell">
  <div class="eyebrow">LIVE BETTING ALERTS · BETA</div>
  <h1>Ειδοποιήσεις αγώνων στο κινητό</h1>
  <p>Η πρώτη έκδοση είναι διαθέσιμη για δοκιμή. Εδώ θα εμφανίζονται ευκαιρίες από live ποδόσφαιρο και μπάσκετ.</p>
  <div class="card">
    <div class="line"><h2>Κατάσταση συστήματος</h2><span class="tag">Δοκιμαστική έκδοση</span></div>
    <div class="number">Έτοιμο για δοκιμή</div>
    <div class="muted">Η σύνδεση με πραγματικές live αποδόσεις δεν έχει ενεργοποιηθεί.</div>
  </div>
  <div class="card">
    <h2>Αρχικές προτιμήσεις</h2>
    <p>⚽ Ποδόσφαιρο &nbsp; 🏀 Μπάσκετ</p>
    <p>Στόχος: συνδυασμοί δύο επιλογών με συνολική απόδοση πάνω από 3,00.</p>
    <p class="muted">Μόνο ειδοποιήσεις — ποτέ αυτόματη τοποθέτηση στοιχήματος.</p>
  </div>
  <div class="card">
    <h2>Δοκιμή ειδοποιήσεων</h2>
    <p class="muted">Άνοιξε την εφαρμογή σε Chrome. Επίτρεψε τις ειδοποιήσεις και μετά στείλε μια δοκιμαστική ειδοποίηση.</p>
    <div class="buttons">
      <button class="primary" id="enable">Ενεργοποίηση ειδοποιήσεων</button>
      <button class="secondary" id="test">Δοκιμαστική ειδοποίηση</button>
    </div>
    <p id="feedback" role="status" aria-live="polite"></p>
  </div>
  <p class="notice">Σημαντικό: η δοκιμαστική ειδοποίηση δεν είναι πραγματική στοιχηματική πρόταση. Ειδοποιήσεις όταν ο ιστότοπος είναι κλειστός θα λειτουργήσουν μόνο μετά την επόμενη αναβάθμιση.</p>
  <p class="foot">Live Betting Alerts · Χωρίς αυτόματα στοιχήματα</p>
</main>
<script>
  const feedback = document.getElementById('feedback');
  let swRegistration = null;
  async function registerWorker() {
    if (!('serviceWorker' in navigator)) throw Error('Το πρόγραμμα περιήγησης δεν υποστηρίζει service workers.');
    if (!swRegistration) swRegistration = await navigator.serviceWorker.register('/sw.js');
    return swRegistration;
  }
  async function requestAccess() {
    if (!('Notification' in window)) throw Error('Οι ειδοποιήσεις δεν υποστηρίζονται εδώ. Δοκίμασε το Chrome.');
    await registerWorker();
    const permission = Notification.permission === 'default'
      ? await Notification.requestPermission()
      : Notification.permission;
    if (permission !== 'granted') throw Error('Δεν δόθηκε άδεια. Άνοιξε τις ρυθμίσεις του Chrome για τις ειδοποιήσεις αυτού του ιστότοπου.');
    return swRegistration;
  }
  document.getElementById('enable').addEventListener('click', async () => {
    try {
      await requestAccess();
      feedback.textContent = '✓ Οι ειδοποιήσεις έχουν επιτραπεί.';
    } catch (err) { feedback.textContent = err.message; }
  });
  document.getElementById('test').addEventListener('click', async () => {
    try {
      const registration = await requestAccess();
      await registration.showNotification('Live Betting Alerts · Δοκιμή', {
        body: 'Οι ειδοποιήσεις λειτουργούν! Δεν είναι πραγματική πρόταση στοιχήματος.',
        tag: 'live-betting-alerts-test',
        data: { url: '/' }
      });
      feedback.textContent = '✓ Εστάλη δοκιμαστική ειδοποίηση στη συσκευή.';
    } catch (err) { feedback.textContent = err.message; }
  });
</script>
</body>
</html>"""

WORKER = """self.addEventListener('notificationclick', (event) => {
  event.notification.close();
  event.waitUntil(clients.matchAll({type: 'window', includeUncontrolled: true}).then((wins) => {
    const current = wins.find(w => w.url.startsWith(self.location.origin));
    if (current) return current.focus();
    return clients.openWindow('/');
  }));
});
"""


@app.get('/')
def index():
    return render_template_string(PAGE)


@app.get('/health')
def health():
    return jsonify(status='ok', service='live-betting-alerts')


@app.get('/api/alerts')
def alerts():
    """No invented betting signals: return empty until an actual data feed exists."""
    return jsonify(alerts=[], live_data_connected=False)


@app.get('/sw.js')
def service_worker():
    return Response(WORKER, mimetype='application/javascript', headers={'Cache-Control': 'no-cache'})


if __name__ == '__main__':
    port = int(os.environ.get('PORT', '10000'))
    app.run(host='0.0.0.0', port=port)
