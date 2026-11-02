from datetime import datetime, timezone
import math
import pandas as pd
import requests
import streamlit as st

BASE = 'https://api.the-odds-api.com/v4'
SOCCER = {
    'English Premier League': 'soccer_epl',
    'Spanish La Liga': 'soccer_spain_la_liga',
    'Italian Serie A': 'soccer_italy_serie_a',
    'German Bundesliga': 'soccer_germany_bundesliga',
    'French Ligue 1': 'soccer_france_ligue_one',
    'UEFA Champions League': 'soccer_uefa_champs_league',
    'UEFA Europa League': 'soccer_uefa_europa_league',
    'Dutch Eredivisie': 'soccer_netherlands_eredivisie',
    'Portuguese Primeira Liga': 'soccer_portugal_primeira_liga',
    'English Championship': 'soccer_efl_champ',
    'Major League Soccer': 'soccer_usa_mls',
    'Mexican Liga MX': 'soccer_mexico_ligamx',
    'Saudi Pro League': 'soccer_saudi_arabia_pro_league',
    'Brazilian Série A': 'soccer_brazil_campeonato',
    'Argentine Primera División': 'soccer_argentina_primera_division',
}
NBA = {'NBA': 'basketball_nba'}

st.set_page_config(page_title='Multi-Sport Odds Scanner', layout='wide')
st.title('Multi-Sport Odds Scanner')
st.caption('Soccer 1X2 + NBA moneyline, spread and totals | Research and paper trading only')

@st.cache_data(ttl=300, show_spinner=False)
def get_sports(api_key):
    r = requests.get(f'{BASE}/sports/', params={'apiKey': api_key}, timeout=25)
    if r.status_code >= 400:
        raise RuntimeError(f'Sports catalogue request failed (HTTP {r.status_code}). Check the API key and plan.')
    return r.json(), r.headers.get('x-requests-remaining', 'unknown')

@st.cache_data(ttl=90, show_spinner=False)
def get_odds(api_key, sport_key, regions, markets):
    r = requests.get(f'{BASE}/sports/{sport_key}/odds/', params={
        'apiKey': api_key, 'regions': regions, 'markets': markets,
        'oddsFormat': 'decimal', 'dateFormat': 'iso'
    }, timeout=30)
    if r.status_code >= 400:
        # Do not expose the request URL, which contains the API key.
        if r.status_code == 401:
            raise RuntimeError('API key rejected (HTTP 401). Check the key.')
        if r.status_code == 403:
            raise RuntimeError('This sport/market may not be included in your API plan (HTTP 403).')
        if r.status_code == 429:
            raise RuntimeError('API rate/credit limit reached (HTTP 429).')
        raise RuntimeError(f'Odds request failed (HTTP {r.status_code}) for {sport_key}.')
    return r.json(), r.headers.get('x-requests-remaining', 'unknown')

def no_vig_probs(outcomes):
    valid = []
    for o in outcomes:
        try:
            price = float(o.get('price'))
            if price > 1:
                valid.append((o, price, 1.0 / price))
        except (TypeError, ValueError):
            pass
    total = sum(x[2] for x in valid)
    if not total:
        return []
    return [(o, price, inv / total) for o, price, inv in valid]

def scan_event(event, sport_title, markets):
    # Aggregate fair (de-vigged) probabilities across bookmaker prices.
    # This is a market benchmark, NOT an independent prediction model.
    market_book_probs = {}
    best_prices = {}
    best_lines = {}
    for book in event.get('bookmakers', []):
        for market in book.get('markets', []):
            mk = market.get('key')
            if mk not in markets:
                continue
            outcomes = market.get('outcomes', [])
            # For spreads/totals, only compare identical points/lines.
            grouped = {}
            for o in outcomes:
                name = str(o.get('name', ''))
                point = o.get('point')
                line = None if point is None else round(float(point), 3)
                group_key = (mk, line)
                grouped.setdefault(group_key, []).append(o)
                try:
                    price = float(o.get('price'))
                    if price <= 1: continue
                except (TypeError, ValueError):
                    continue
                selection = str(o.get('description') or name)
                # Include team/outcome, line and market in key.
                outcome_key = (mk, selection, line, name if mk == 'totals' else '')
                current = best_prices.get(outcome_key)
                if current is None or price > current['odds']:
                    best_prices[outcome_key] = {
                        'odds': price,
                        'bookmaker': book.get('title', book.get('key', 'Unknown')),
                        'point': point,
                        'name': name,
                        'selection': selection,
                        'market': mk,
                    }
            for group_key, group in grouped.items():
                probs = no_vig_probs(group)
                for o, price, p in probs:
                    name = str(o.get('name', ''))
                    point = o.get('point')
                    line = None if point is None else round(float(point), 3)
                    selection = str(o.get('description') or name)
                    outcome_key = (mk, selection, line, name if mk == 'totals' else '')
                    market_book_probs.setdefault(outcome_key, []).append(p)
    rows = []
    for outcome_key, best in best_prices.items():
        probs = market_book_probs.get(outcome_key, [])
        if not probs:
            continue
        fair_p = sum(probs) / len(probs)
        odds = best['odds']
        ev = fair_p * odds - 1
        market_label = {'h2h': 'Moneyline / 1X2', 'spreads': 'Point spread', 'totals': 'Over/Under'}.get(best['market'], best['market'])
        line_text = '' if best['point'] is None else f" {best['point']:+g}" if best['market'] == 'spreads' else f" {best['point']:g}"
        if best['market'] == 'totals':
            selection_label = f"{best['name']} {best['point']}"
        else:
            selection_label = f"{best['selection']}{line_text}"
        rows.append({
            'sport': sport_title,
            'event': f"{event.get('away_team', '')} @ {event.get('home_team', '')}",
            'start_time_utc': event.get('commence_time', ''),
            'market': market_label,
            'selection': selection_label,
            'best_odds': round(odds, 3),
            'best_bookmaker': best['bookmaker'],
            'market_fair_probability_%': round(100 * fair_p, 2),
            'implied_probability_%': round(100 / odds, 2),
            'market_edge_pp': round(100 * (fair_p - 1 / odds), 2),
            'market_based_estimated_EV_%': round(100 * ev, 2),
            'books_pricing_outcome': len(probs),
        })
    return rows

with st.sidebar:
    api_key = st.text_input('The Odds API key', type='password', help='Entered here only; do not add it to GitHub.')
    regions = st.multiselect('Bookmaker regions', ['uk', 'eu', 'us', 'au'], default=['uk', 'eu'])
    selected_soccer = st.multiselect('Soccer competitions (1X2)', list(SOCCER.keys()), default=list(SOCCER.keys()))
    include_nba = st.checkbox('Include NBA', value=True)
    nba_markets = st.multiselect('NBA markets', ['h2h', 'spreads', 'totals'], default=['h2h', 'spreads', 'totals'], help='Moneyline, point spread, and over/under.')
    min_edge = st.number_input('Minimum market edge (percentage points)', min_value=-20.0, max_value=30.0, value=2.0, step=0.5)
    scan = st.button('Scan selected competitions', type='primary')

st.info('This version compares the best available price with a de-vigged average of bookmaker prices. That is useful for odds screening, but it is **not yet an independent probability model** and cannot prove a bet is profitable. We will add separately trained soccer and NBA models after the odds feed is verified.')
st.warning('A full scan can use many API credits: one request per selected competition. Start with 2–3 leagues to check your plan and remaining quota. Bet365 may not be included in every region/competition feed.')

if scan:
    if not api_key:
        st.error('Enter your API key first.')
    elif not regions:
        st.error('Select at least one bookmaker region.')
    elif not selected_soccer and not include_nba:
        st.error('Select at least one competition.')
    else:
        try:
            with st.spinner('Checking supported competitions...'):
                sports, catalogue_remaining = get_sports(api_key)
            supported = {s.get('key'): s for s in sports if s.get('active', True)}
            wanted = [(name, key, 'h2h') for name, key in SOCCER.items() if name in selected_soccer]
            if include_nba and nba_markets:
                wanted.append(('NBA', NBA['NBA'], ','.join(nba_markets)))
            tasks = [(name, key, mk) for name, key, mk in wanted if key in supported]
            unavailable = [(name, key) for name, key, _ in wanted if key not in supported]
            if unavailable:
                st.warning('Not listed as available by your API key/plan: ' + ', '.join(name for name, _ in unavailable))
            if not tasks:
                st.error('None of the selected competitions are available to this API key/plan.')
            all_rows = []
            progress = st.progress(0, text='Loading odds...')
            errors = []
            last_remaining = 'unknown'
            for i, (name, key, markets) in enumerate(tasks, start=1):
                try:
                    events, last_remaining = get_odds(api_key, key, ','.join(regions), markets)
                    for ev in events:
                        all_rows.extend(scan_event(ev, name, markets.split(',')))
                except Exception as exc:
                    errors.append(f'{name}: {str(exc)}')
                progress.progress(i / len(tasks), text=f'Scanned {i} of {len(tasks)} competitions')
            st.caption(f'Catalogue requests remaining: {catalogue_remaining} | Last odds response remaining: {last_remaining}')
            if errors:
                st.warning('Some competitions could not be scanned: ' + ' | '.join(errors))
            if not all_rows:
                st.info('No odds rows were returned. Try fewer leagues, check regions, and confirm plan coverage.')
            else:
                df = pd.DataFrame(all_rows).sort_values('market_based_estimated_EV_%', ascending=False)
                st.subheader('All available odds comparisons')
                st.dataframe(df, use_container_width=True, hide_index=True)
                candidates = df[df['market_edge_pp'] >= min_edge]
                st.subheader('Market-screening candidates')
                if candidates.empty:
                    st.write('No outcomes passed your threshold. Do not force a bet.')
                else:
                    st.dataframe(candidates, use_container_width=True, hide_index=True)
                st.download_button('Export scan to CSV', df.to_csv(index=False).encode('utf-8'), file_name='multisport_odds_scan.csv', mime='text/csv')
                st.caption('Scan generated UTC: ' + datetime.now(timezone.utc).isoformat(timespec='seconds'))
        except Exception as exc:
            st.error(str(exc))
else:
    st.write('Choose a few competitions in the sidebar and click **Scan selected competitions**. You can expand to all supported leagues once you confirm your API quota.')
