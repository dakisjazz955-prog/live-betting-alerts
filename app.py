"""Live Betting Alerts: Android Chrome Web Push demonstration.

This app does not provide real-time bookmaker odds or automatic betting.
Subscriptions and generated keys are temporarily stored in SQLite on Render Free.
"""
import base64
import hashlib
import json
import logging
import os
import re
import secrets
import sqlite3
import threading
import time
from urllib.parse import urlsplit

from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from flask import Flask, Response, jsonify, render_template_string, request
from live_feed import fetch_live, FeedError
from py_vapid import Vapid
from pywebpush import WebPushException, webpush

app = Flask(__name__)
DB_PATH = os.environ.get('PUSH_DB_PATH', '/tmp/live_betting_alerts_push.sqlite3')
VAPID_SUBJECT = os.environ.get('VAPID_SUBJECT', 'https://live-betting-alerts.onrender.com')
ALLOWED_PUSH_HOSTS = {
    'fcm.googleapis.com', 'fcm-xm.googleapis.com',
    'updates.push.services.mozilla.com', 'web.push.apple.com',
}
B64 = re.compile(r'^[A-Za-z0-9_-]+={0,2}$')


def database():
    os.makedirs(os.path.dirname(os.path.abspath(DB_PATH)), exist_ok=True)
    db = sqlite3.connect(DB_PATH, timeout=10)
    db.row_factory = sqlite3.Row
    db.execute('CREATE TABLE IF NOT EXISTS settings (name TEXT PRIMARY KEY, value TEXT NOT NULL)')
    db.execute('''CREATE TABLE IF NOT EXISTS subscriptions (
        endpoint TEXT PRIMARY KEY, p256dh TEXT NOT NULL, auth TEXT NOT NULL,
        token_hash TEXT NOT NULL UNIQUE, last_test REAL NOT NULL DEFAULT 0,
        last_result TEXT NOT NULL DEFAULT 'never')''')
    db.commit()
    return db


def b64url_encode(value):
    return base64.urlsafe_b64encode(value).rstrip(b'=').decode('ascii')


def b64url_decode(value):
    return base64.urlsafe_b64decode(value + '=' * (-len(value) % 4))


def vapid_private():
    configured = os.environ.get('VAPID_PRIVATE_KEY', '').strip()
    if configured:
        if not B64.fullmatch(configured) or len(b64url_decode(configured)) != 32:
            raise ValueError('VAPID_PRIVATE_KEY must be a base64url-encoded 32-byte P-256 private key')
        return configured
    db = database()
    try:
        row = db.execute("SELECT value FROM settings WHERE name='vapid'").fetchone()
        if row:
            return row['value']
        private = ec.generate_private_key(ec.SECP256R1())
        raw = private.private_numbers().private_value.to_bytes(32, 'big')
        db.execute("INSERT OR IGNORE INTO settings(name,value) VALUES ('vapid',?)", (b64url_encode(raw),))
        db.commit()
        return db.execute("SELECT value FROM settings WHERE name='vapid'").fetchone()['value']
    finally:
        db.close()


def vapid_public():
    private = ec.derive_private_key(int.from_bytes(b64url_decode(vapid_private()), 'big'), ec.SECP256R1())
    raw = private.public_key().public_bytes(Encoding.X962, PublicFormat.UncompressedPoint)
    return b64url_encode(raw)


def checked_subscription(raw):
    if not isinstance(raw, dict):
        raise ValueError('Missing subscription')
    endpoint, keys = raw.get('endpoint'), raw.get('keys')
    if not isinstance(endpoint, str) or len(endpoint) > 2048 or not isinstance(keys, dict):
        raise ValueError('Invalid subscription')
    url = urlsplit(endpoint)
    if (url.scheme != 'https' or (url.hostname or '').lower() not in ALLOWED_PUSH_HOSTS
            or url.username or url.password or url.port not in (None, 443)):
        raise ValueError('Unsupported push endpoint')
    p256dh, auth = keys.get('p256dh'), keys.get('auth')
    if not all(isinstance(v, str) and B64.fullmatch(v) for v in (p256dh, auth)):
        raise ValueError('Invalid push keys')
    if len(b64url_decode(p256dh)) != 65 or len(b64url_decode(auth)) != 16:
        raise ValueError('Invalid push keys')
    return endpoint, p256dh, auth


def token_hash(raw):
    token = raw.get('test_token') if isinstance(raw, dict) else None
    if not isinstance(token, str) or not 1 <= len(token) <= 200:
        return None
    return hashlib.sha256(token.encode('utf-8')).hexdigest()


def send_delayed_push(hash_value):
    db = database()
    try:
        row = db.execute('SELECT endpoint,p256dh,auth FROM subscriptions WHERE token_hash=?',
                         (hash_value,)).fetchone()
    finally:
        db.close()
    if row is None:
        return
    try:
        webpush(
            subscription_info={
                'endpoint': row['endpoint'],
                'keys': {'p256dh': row['p256dh'], 'auth': row['auth']}
            },
            data=json.dumps({
                'title': 'Live Betting Alerts · Δοκιμή',
                'body': 'Η ειδοποίηση ήρθε από τον διακομιστή!',
                'tag': 'lba-server-test'
            }, ensure_ascii=False),
            vapid_private_key=Vapid.from_raw(vapid_private().encode('ascii')),
            vapid_claims={'sub': VAPID_SUBJECT},
            ttl=120, timeout=10
        )
        result = 'accepted'
    except WebPushException as exc:
        code = getattr(getattr(exc, 'response', None), 'status_code', None)
        result = 'expired' if code in (404, 410) else 'failed'
        app.logger.warning('Push provider error: HTTP %s', code)
    except Exception:
        result = 'failed'
        app.logger.exception('Web Push test failed')
    db = database()
    try:
        if result == 'expired':
            db.execute('DELETE FROM subscriptions WHERE token_hash=?', (hash_value,))
        else:
            db.execute('UPDATE subscriptions SET last_result=? WHERE token_hash=?',
                       (result, hash_value))
        db.commit()
    finally:
        db.close()


PAGE = r'''<!doctype html>
<html lang="el">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
  <meta name="theme-color" content="#101b20">
  <title>Live Betting Alerts</title>
  <style>
    :root { color-scheme:dark; font-family:system-ui,-apple-system,"Segoe UI",sans-serif; }
    * { box-sizing:border-box; }
    body { margin:0; background:#101b20; color:#f5f7f7; }
    main { max-width:560px; margin:0 auto; padding:24px 20px 48px; }
    .eyebrow { color:#6ce6b4; font-size:12px; font-weight:800; letter-spacing:2px; }
    h1 { font-size:30px; line-height:1.13; margin:22px 0 12px; }
    h2 { font-size:18px; margin:0 0 10px; }
    p { color:#b5c2c5; line-height:1.56; }
    .card { background:#1c2a30; border:1px solid #33434b; border-radius:18px; padding:18px; margin-top:16px; }
    .tag { display:inline-block; color:#ffdea1; background:#473b27; padding:6px 11px; border-radius:30px; font-size:12px; }
    .buttons { display:grid; gap:10px; margin:17px 0; }
    button { border:0; border-radius:12px; padding:15px; font-size:15px; font-weight:750; cursor:pointer; }
    button:disabled { opacity:.6; }
    .primary { background:#69e5b3; color:#10241c; }
    .secondary { background:#304b53; color:#f3faf7; }
    .dim { background:#273b42; color:#f3faf7; }
    .notice { border-left:3px solid #f3b95c; background:#2d2925; color:#e7d9c7; padding:12px; border-radius:4px; font-size:13px; }
    .small { font-size:13px; }
    #feedback { min-height:40px; color:#b7f5d9; font-size:14px; }
  </style>
</head>
<body>
<main>
  <div class="eyebrow">LIVE BETTING ALERTS · BETA</div>
  <h1>Ειδοποιήσεις αγώνων στο κινητό</h1>
  <p>Δοκιμή ειδοποιήσεων Android ακόμη και με κλειστή τη σελίδα.</p>
  <section class="card">
    <span class="tag">Δοκιμαστική έκδοση</span>
    <h2 style="margin-top:14px">⚽ Ποδόσφαιρο · 🏀 Μπάσκετ</h2>
    <p>Μελλοντικός στόχος: δύο επιλογές με συνολική απόδοση πάνω από 3,00.</p>
    <p class="small">Για πραγματικά live δεδομένα απαιτείται API_SPORTS_KEY στο Render. Δεν τοποθετούνται αυτόματα στοιχήματα.</p>
  </section>
  <section class="card">
    <h2>Push ειδοποιήσεις</h2>
    <p class="small">Άνοιξε τη σελίδα στον Chrome του Android και ενεργοποίησε τις ειδοποιήσεις.</p>
    <div class="buttons">
      <button id="enable" class="primary">1. Ενεργοποίηση push</button>
      <button id="local" class="dim">Δοκιμαστική ειδοποίηση τώρα</button>
      <button id="remote" class="secondary">2. Δοκιμή με κλειστό Chrome</button>
      <button id="status" class="dim">Έλεγχος τελευταίας δοκιμής</button>
    </div>
    <p id="feedback" role="status" aria-live="polite"></p>
  </section>
  <p class="notice">Πάτησε «Δοκιμή με κλειστό Chrome», κλείσε την καρτέλα και περίμενε περίπου 15 δευτερόλεπτα. Το μήνυμα θα αποσταλεί από τον διακομιστή. Μπορεί να μην εμφανιστεί αν το Android περιορίζει τον Chrome.</p>
  <p class="small">Στη δωρεάν φιλοξενία, μετά από επανεκκίνηση ίσως χρειαστεί να ενεργοποιήσεις ξανά το push.</p>

  <section class="card">
    <h2>Πραγματικοί αγώνες · LIVE</h2>
    <p class="small">Τα στοιχεία προέρχονται μόνο από τον πάροχο API-Sports. Χωρίς σύνδεση API δεν εμφανίζονται υποθετικά σκορ ή αποδόσεις.</p>
    <div class="buttons">
      <button id="live-football" class="secondary">⚽ Ζωντανό ποδόσφαιρο</button>
      <button id="live-basketball" class="secondary">🏀 Ζωντανό μπάσκετ</button>
      <button id="live-odds" class="secondary">📈 Live αποδόσεις ποδοσφαίρου</button>
      <button id="live-watch" class="dim">Παρακολούθηση για 15 λεπτά</button>
    </div>
    <p class="small" id="live-meta" aria-live="polite">Δεν έχει γίνει ακόμη έλεγχος πηγής.</p>
    <div id="live-results" class="small"></div>
    <p class="small">Η παρακολούθηση ανανεώνεται ανά 2 λεπτά μόνο όσο η σελίδα είναι ανοικτή. Δεν είναι συνεχής υπηρεσία στο παρασκήνιο.</p>
  </section>
</main>
<script>
  const feedback = document.getElementById('feedback');
  const buttons = ['enable','local','remote','status'].map(id => document.getElementById(id));
  const tokenStore = 'lba-push-demo-token';
  function show(msg) { feedback.textContent = msg; }
  function getToken() { try { return localStorage.getItem(tokenStore); } catch { return null; } }
  function saveToken(value) { try { localStorage.setItem(tokenStore,value); } catch {} }
  function decodeKey(value) {
    const v = value.replace(/-/g,'+').replace(/_/g,'/');
    const binary = atob(v.padEnd(Math.ceil(v.length/4)*4,'='));
    return Uint8Array.from(binary, x => x.charCodeAt(0));
  }
  async function api(path,data) {
    const opts = data ? {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)} : {};
    const response = await fetch(path,opts);
    const value = await response.json();
    if (!response.ok) throw new Error(value.error || 'Σφάλμα διακομιστή');
    return value;
  }
  async function allow() {
    if (!('Notification' in window)) throw new Error('Άνοιξε την εφαρμογή στον Chrome.');
    const permission = Notification.permission === 'default' ? await Notification.requestPermission() : Notification.permission;
    if (permission !== 'granted') throw new Error('Οι ειδοποιήσεις δεν έχουν επιτραπεί.');
  }
  async function worker() {
    if (!('serviceWorker' in navigator)) throw new Error('Δεν υποστηρίζονται service workers.');
    return navigator.serviceWorker.register('/sw.js',{updateViaCache:'none'});
  }
  async function enablePush() {
    await allow();
    const reg = await worker();
    if (!('pushManager' in reg)) throw new Error('Το Web Push δεν υποστηρίζεται.');
    const config = await api('/api/push/config');
    const newKey = decodeKey(config.public_key);
    let sub = await reg.pushManager.getSubscription();
    if (sub) {
      const bytes = sub.options.applicationServerKey ? new Uint8Array(sub.options.applicationServerKey) : new Uint8Array();
      if (bytes.length !== newKey.length || bytes.some((n,i) => n !== newKey[i])) {
        await sub.unsubscribe();
        sub = null;
      }
    }
    if (!sub) sub = await reg.pushManager.subscribe({userVisibleOnly:true,applicationServerKey:newKey});
    const saved = await api('/api/push/subscribe',{subscription:sub.toJSON()});
    saveToken(saved.test_token);
    return reg;
  }
  async function action(callback) {
    buttons.forEach(b => b.disabled=true);
    try { await callback(); } catch (err) { show('Πρόβλημα: ' + err.message); }
    finally { buttons.forEach(b => b.disabled=false); }
  }
  document.getElementById('enable').onclick = () => action(async () => {
    await enablePush(); show('✓ Το κινητό είναι εγγεγραμμένο για push ειδοποιήσεις.');
  });
  document.getElementById('local').onclick = () => action(async () => {
    await allow(); const reg = await worker();
    await reg.showNotification('Live Betting Alerts · Δοκιμή',{
      body:'Αυτή είναι μια τοπική δοκιμή.',tag:'lba-local-test',data:{url:'/'}
    });
    show('✓ Δημιουργήθηκε η τοπική δοκιμαστική ειδοποίηση.');
  });
  document.getElementById('remote').onclick = () => action(async () => {
    await enablePush();
    const result = await api('/api/push/test',{test_token:getToken()});
    show('✓ Η δοκιμή προγραμματίστηκε. Κλείσε τώρα την καρτέλα: αποστολή σε ' + result.delay_seconds + ' δευτερόλεπτα.');
  });
  document.getElementById('status').onclick = () => action(async () => {
    if (!getToken()) throw new Error('Ενεργοποίησε πρώτα το push.');
    const value = await api('/api/push/status',{test_token:getToken()});
    const states = {
      never:'Δεν έγινε ακόμη δοκιμή διακομιστή.',
      queued:'Η δοκιμή περιμένει να σταλεί.',
      accepted:'Ο πάροχος push δέχτηκε το μήνυμα. Έλεγξε το Android.',
      failed:'Η αποστολή απέτυχε. Δοκίμασε ξανά.'
    };
    show(states[value.last_result] || 'Η εγγραφή έληξε. Ενεργοποίησε ξανά το push.');
  });

  // Real live observation (not demo signals). Calls occur only with user interaction.
  let liveMode = 'football';
  let watching = false;
  let watchInterval = null;
  let watchTimeout = null;
  let lastQuotes = new Map();
  const liveResults = document.getElementById('live-results');
  const liveMeta = document.getElementById('live-meta');
  function liveLine(item, odds) {
    const box = document.createElement('p');
    box.style.padding = '9px 0';
    box.style.borderBottom = '1px solid #33434b';
    if (odds) {
      const key = [item.fixture_id,item.market,item.selection].join(' / ');
      const previous = lastQuotes.get(key);
      const moved = previous && Math.abs(item.odd/previous - 1) >= 0.10;
      box.textContent = `Αγώνας #${item.fixture_id} · ${item.market} / ${item.selection}: ${item.odd}` +
        (moved ? ` · μεταβολή ${((item.odd/previous-1)*100).toFixed(1)}%` : '');
      return [box, key, item.odd, moved];
    }
    box.textContent = `${item.league || 'Διοργάνωση'} · ${item.home || '?'} ${item.home_score ?? '-'} : ${item.away_score ?? '-'} ${item.away || '?'} · ${item.minute ?? item.status ?? ''}`;
    return [box];
  }
  async function loadLive(mode=liveMode) {
    liveMode=mode;
    liveMeta.textContent='Έλεγχος πραγματικών δεδομένων…';
    try {
      const resp = await fetch('/api/live?mode='+encodeURIComponent(mode), {cache:'no-store'});
      const data = await resp.json();
      if (!resp.ok) throw new Error(data.error || 'Μη διαθέσιμη πηγή');
      const arr = Array.isArray(data.items) ? data.items : [];
      const fragment = document.createDocumentFragment();
      const current = new Map();
      const changed = [];
      for (const item of arr) {
        const [el, key, price, moved] = liveLine(item, mode==='odds');
        fragment.appendChild(el);
        if (key) current.set(key, price);
        if (moved) changed.push(el.textContent);
      }
      liveResults.replaceChildren(fragment);
      if (!arr.length) liveResults.textContent = 'Ο πάροχος δεν επέστρεψε ενεργούς αγώνες/αποδόσεις για αυτή τη στιγμή.';
      liveMeta.textContent = `API-Sports · ${arr.length} εγγραφές · έλεγχος ${new Date(data.retrieved_at).toLocaleTimeString('el-GR')} · ${data.cached ? 'προσωρινά αποθηκευμένα' : 'νέα λήψη'}`;
      if (mode === 'odds') {
        lastQuotes = current;
        if (changed.length && Notification.permission === 'granted') {
          const reg = await worker();
          await reg.showNotification('Live Betting Alerts · Μεταβολή απόδοσης', {
            body:changed[0].slice(0,180),tag:'lba-live-odds',data:{url:'/'}
          });
        }
      }
    } catch (error) {
      liveResults.replaceChildren();
      liveMeta.textContent = 'Δεν έγινε live σύνδεση: ' + error.message;
    }
  }
  for (const [id, mode] of [['live-football','football'],['live-basketball','basketball'],['live-odds','odds']]) {
    document.getElementById(id).addEventListener('click', () => {
      lastQuotes = new Map();
      loadLive(mode);
    });
  }
  const watchButton = document.getElementById('live-watch');
  function stopWatch() {
    watching=false;
    clearInterval(watchInterval);
    clearTimeout(watchTimeout);
    watchInterval=watchTimeout=null;
    watchButton.textContent='Παρακολούθηση για 15 λεπτά';
  }
  watchButton.addEventListener('click', () => {
    if (watching) { stopWatch(); return; }
    watching=true;
    watchButton.textContent='Διακοπή παρακολούθησης';
    loadLive();
    watchInterval=setInterval(() => {
      if (document.visibilityState === 'visible') loadLive();
    },120000);
    watchTimeout=setTimeout(stopWatch,15*60*1000);
  });
</script>
</body>
</html>'''

WORKER = r'''self.addEventListener('push', event => {
  let message = {};
  try { if (event.data) message = event.data.json(); } catch {}
  event.waitUntil(self.registration.showNotification(
    typeof message.title === 'string' ? message.title : 'Live Betting Alerts',
    {body:typeof message.body === 'string' ? message.body : 'Νέα ειδοποίηση.',
     tag:'lba-server-test',data:{url:'/'}}
  ));
});
self.addEventListener('notificationclick', event => {
  event.notification.close();
  event.waitUntil(clients.matchAll({type:'window',includeUncontrolled:true}).then(wins => {
    const current = wins.find(w => w.url.startsWith(self.location.origin));
    return current ? current.focus() : clients.openWindow('/');
  }));
});'''


@app.get('/')
def index():
    return render_template_string(PAGE)


@app.get('/health')
def health():
    return jsonify(status='ok', service='live-betting-alerts')


@app.get('/api/alerts')
def alerts():
    # No algorithmic betting signals are configured yet.
    return jsonify(alerts=[], live_data_connected=False)


@app.get('/api/live')
def live_data():
    mode = request.args.get('mode', 'football')
    try:
        return jsonify(fetch_live(mode))
    except FeedError as exc:
        return jsonify(error=str(exc), live_data_connected=False, mode=mode), 503


@app.get('/api/push/config')
def push_config():
    return jsonify(public_key=vapid_public(), live_data_connected=False,
                   storage_is_temporary=not bool(os.environ.get('PUSH_DB_PATH')))


@app.post('/api/push/subscribe')
def push_subscribe():
    data = request.get_json(silent=True)
    try:
        endpoint, p256dh, auth = checked_subscription(
            data.get('subscription') if isinstance(data, dict) else None)
    except (ValueError, TypeError) as exc:
        return jsonify(error=str(exc)), 400
    token = secrets.token_urlsafe(32)
    db = database()
    try:
        db.execute('''INSERT INTO subscriptions(endpoint,p256dh,auth,token_hash) VALUES (?,?,?,?)
        ON CONFLICT(endpoint) DO UPDATE SET p256dh=excluded.p256dh, auth=excluded.auth,
        token_hash=excluded.token_hash,last_test=0,last_result='never' ''',
                   (endpoint, p256dh, auth, token_hash({'test_token': token})))
        db.commit()
    finally:
        db.close()
    return jsonify(registered=True, test_token=token)


@app.post('/api/push/test')
def push_test():
    hash_value = token_hash(request.get_json(silent=True))
    if not hash_value:
        return jsonify(error='Missing test token'), 400
    db = database()
    now = time.time()
    try:
        row = db.execute('SELECT last_test FROM subscriptions WHERE token_hash=?',
                         (hash_value,)).fetchone()
        if row is None:
            return jsonify(error='Ενεργοποίησε ξανά το push.'), 404
        if now - row['last_test'] < 40:
            return jsonify(error='Δοκίμασε ξανά λίγο αργότερα.'), 429
        db.execute("UPDATE subscriptions SET last_test=?,last_result='queued' WHERE token_hash=?",
                   (now, hash_value))
        db.commit()
    finally:
        db.close()
    timer = threading.Timer(15, send_delayed_push, args=(hash_value,))
    timer.daemon = True
    timer.start()
    return jsonify(queued=True, delay_seconds=15), 202


@app.post('/api/push/status')
def push_status():
    hash_value = token_hash(request.get_json(silent=True))
    if not hash_value:
        return jsonify(error='Missing test token'), 400
    db = database()
    try:
        row = db.execute('SELECT last_result FROM subscriptions WHERE token_hash=?',
                         (hash_value,)).fetchone()
    finally:
        db.close()
    if row is None:
        return jsonify(error='Η εγγραφή έληξε. Ενεργοποίησε ξανά το push.'), 404
    return jsonify(last_result=row['last_result'])


@app.get('/sw.js')
def service_worker():
    return Response(WORKER, mimetype='application/javascript',
                    headers={'Cache-Control':'no-cache', 'Service-Worker-Allowed':'/'})


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', '10000')))
