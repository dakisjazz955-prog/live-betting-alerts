"""API-Sports live match/odds adapter, without simulated events or prices."""
from datetime import datetime
import json
import os
import threading
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

KEY = os.environ.get('API_SPORTS_KEY', '').strip()
CACHE_SECONDS = 90
CACHE = {}
LOCK = threading.RLock()
MAX_BYTES = 6_000_000


class FeedError(Exception):
    pass


def _request(sport, endpoint, query=None):
    if not KEY:
        raise FeedError('Λείπει το API_SPORTS_KEY από τις μεταβλητές του Render.')
    root = {
        'football': 'https://v3.football.api-sports.io',
        'basketball': 'https://v1.basketball.api-sports.io',
    }[sport]
    url = root + endpoint + ('?' + urlencode(query) if query else '')
    req = Request(url, headers={'x-apisports-key': KEY, 'accept': 'application/json'})
    try:
        with urlopen(req, timeout=12) as response:
            payload = response.read(MAX_BYTES + 1)
            if len(payload) > MAX_BYTES:
                raise FeedError('Η απάντηση του παρόχου είναι υπερβολικά μεγάλη.')
    except HTTPError as exc:
        raise FeedError(f'Ο πάροχος επέστρεψε HTTP {exc.code}. Έλεγξε το API key και το πλάνο.') from exc
    except (URLError, TimeoutError) as exc:
        raise FeedError('Δεν ήταν δυνατή η σύνδεση με τον πάροχο.') from exc
    try:
        data = json.loads(payload)
    except ValueError as exc:
        raise FeedError('Ο πάροχος επέστρεψε μη έγκυρα δεδομένα.') from exc
    if not isinstance(data, dict):
        raise FeedError('Μη αναμενόμενη απάντηση από τον πάροχο.')
    errors = data.get('errors')
    if errors and errors != [] and errors != {}:
        raise FeedError('Ο πάροχος δεν επέτρεψε το αίτημα. Έλεγξε το πλάνο/API key.')
    if not isinstance(data.get('response'), list):
        raise FeedError('Δεν υπάρχει λίστα δεδομένων στην απάντηση του παρόχου.')
    return data['response']


def _norm_football(data):
    result = []
    for match in data:
        fixture = match.get('fixture') or {}
        status = fixture.get('status') or {}
        teams = match.get('teams') or {}
        goals = match.get('goals') or {}
        league = match.get('league') or {}
        result.append({
            'id': fixture.get('id'), 'league': league.get('name'),
            'home': (teams.get('home') or {}).get('name'),
            'away': (teams.get('away') or {}).get('name'),
            'home_score': goals.get('home'), 'away_score': goals.get('away'),
            'minute': status.get('elapsed'), 'status': status.get('short'),
        })
    return result


LIVE_BASKETBALL = {'Q1','Q2','Q3','Q4','OT','BT','HT'}


def _norm_basketball(data):
    result = []
    for match in data:
        status = (match.get('status') or {}).get('short')
        if status not in LIVE_BASKETBALL:
            continue
        teams = match.get('teams') or {}
        scores = match.get('scores') or {}
        league = match.get('league') or {}
        result.append({
            'id': match.get('id'), 'league': league.get('name'),
            'home': (teams.get('home') or {}).get('name'),
            'away': (teams.get('away') or {}).get('name'),
            'home_score': (scores.get('home') or {}).get('total'),
            'away_score': (scores.get('away') or {}).get('total'),
            'minute': None, 'status': status,
        })
    return result


def _norm_odds(data):
    selections = []
    for entry in data:
        fixture = entry.get('fixture')
        if isinstance(fixture, dict):
            fixture = fixture.get('id')
        for market in entry.get('bets') or []:
            name = str(market.get('name') or 'Αγορά')
            for item in market.get('values') or []:
                if item.get('suspended') is True or item.get('stopped') is True:
                    continue
                raw = item.get('odd')
                try:
                    price = float(raw)
                except (TypeError, ValueError):
                    continue
                if not 1.01 <= price <= 1000:
                    continue
                selections.append({
                    'fixture_id': fixture,
                    'market': name,
                    'selection': str(item.get('value') or ''),
                    'odd': round(price, 3),
                    'update': entry.get('update'),
                })
                if len(selections) >= 300:
                    return selections
    return selections


def fetch_live(mode):
    if mode not in {'football', 'basketball', 'odds'}:
        raise FeedError('Μη αποδεκτό άθλημα.')
    if not KEY:
        raise FeedError('Χρειάζεται API_SPORTS_KEY στο Render για πραγματικά δεδομένα.')
    now = time.monotonic()
    with LOCK:
        cached = CACHE.get(mode)
        if cached and now - cached[0] < CACHE_SECONDS:
            return {**cached[1], 'cached': True}
        # Lock also guards provider quota against simultaneous requests.
        if mode == 'football':
            items = _norm_football(_request('football', '/fixtures', {'live': 'all'}))
        elif mode == 'basketball':
            athens_date = datetime.now(ZoneInfo('Europe/Athens')).strftime('%Y-%m-%d')
            items = _norm_basketball(_request('basketball', '/games',
                {'date': athens_date, 'timezone': 'Europe/Athens'}))
        else:
            items = _norm_odds(_request('football', '/odds/live'))
        result = {'mode': mode, 'items': items, 'count': len(items),
                  'source': 'API-Sports', 'live_data_connected': True,
                  'retrieved_at': datetime.now(ZoneInfo('UTC')).isoformat(),
                  'cached': False, 'notice': 'Πραγματικά δεδομένα παρόχου, όχι εκτιμήσεις.'}
        CACHE[mode] = (time.monotonic(), result)
        return result
