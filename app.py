import math
from datetime import datetime, timezone
import pandas as pd
import requests
import streamlit as st

st.set_page_config(page_title='Independent Odds Model', layout='wide')
st.title('Independent Odds Model — NFL Pilot')
st.caption('Research and paper trading only. No bets are placed.')
ODDS_URL='https://api.the-odds-api.com/v4/sports/americanfootball_nfl/odds'
GAMES_URL='https://github.com/nflverse/nflverse-data/releases/download/schedules/games.csv'

ALIASES={'ARZ':'ARI','JAC':'JAX','KAN':'KC','SD':'LAC','STL':'LAR','OAK':'LV','TAM':'TB','WSH':'WAS','SFO':'SF','GNB':'GB'}
NAMES={'Arizona Cardinals':'ARI','Atlanta Falcons':'ATL','Baltimore Ravens':'BAL','Buffalo Bills':'BUF','Carolina Panthers':'CAR','Chicago Bears':'CHI','Cincinnati Bengals':'CIN','Cleveland Browns':'CLE','Dallas Cowboys':'DAL','Denver Broncos':'DEN','Detroit Lions':'DET','Green Bay Packers':'GB','Houston Texans':'HOU','Indianapolis Colts':'IND','Jacksonville Jaguars':'JAX','Kansas City Chiefs':'KC','Los Angeles Chargers':'LAC','Los Angeles Rams':'LAR','Las Vegas Raiders':'LV','Miami Dolphins':'MIA','Minnesota Vikings':'MIN','New England Patriots':'NE','New Orleans Saints':'NO','New York Giants':'NYG','New York Jets':'NYJ','Philadelphia Eagles':'PHI','Pittsburgh Steelers':'PIT','Seattle Seahawks':'SEA','San Francisco 49ers':'SF','Tampa Bay Buccaneers':'TB','Tennessee Titans':'TEN','Washington Commanders':'WAS'}
def code(x):
    if pd.isna(x): return None
    x=str(x).strip()
    if x in NAMES: return NAMES[x]
    x=x.upper()
    return ALIASES.get(x,x if x in set(NAMES.values()) else None)

@st.cache_data(ttl=3600)
def get_games():
    r=requests.get(GAMES_URL,timeout=30); r.raise_for_status()
    d=pd.read_csv(pd.io.common.BytesIO(r.content)); d.columns=[str(c).lower().strip() for c in d.columns]
    def col(*names):
        return next((n for n in names if n in d.columns),None)
    h,a,hs,as_,season=col('home_team','home'),col('away_team','away'),col('home_score','home_points'),col('away_score','away_points'),col('season')
    typ,date=col('game_type'),col('gameday','date','game_date')
    if not all([h,a,hs,as_,season]): raise ValueError('Historical results columns did not match expected format.')
    out=pd.DataFrame({'home':d[h].map(code),'away':d[a].map(code),'hs':pd.to_numeric(d[hs],errors='coerce'),'as':pd.to_numeric(d[as_],errors='coerce'),'season':pd.to_numeric(d[season],errors='coerce')})
    out['type']=d[typ] if typ else 'REG'; out['date']=pd.to_datetime(d[date],errors='coerce') if date else pd.NaT
    out=out.dropna(subset=['home','away','hs','as','season'])
    out=out[out['type'].fillna('REG').astype(str).str.upper().isin(['REG','WC','DIV','CON','SB'])]
    return out.sort_values('date')

def train_elo(games, seasons=5, home_adv=55, k=20):
    if games.empty:return {},0
    latest=int(games.season.max()); g=games[games.season>=latest-seasons+1]; ratings={}
    for _, r in g.iterrows():
        home, away = r['home'], r['away']
        home_score, away_score = float(r['hs']), float(r['as'])
        rh,ra=ratings.get(home,1500.),ratings.get(away,1500.)
        expected=1/(1+10**(-((rh+home_adv-ra)/400)))
        actual=1. if home_score>away_score else 0. if home_score<away_score else .5
        margin=abs(home_score-away_score); mult=math.log1p(margin)*2.2/(2.2+.001*abs(rh-ra))
        change=k*mult*(actual-expected); ratings[home]=rh+change; ratings[away]=ra-change
    return ratings,latest

def phome(rh,ra,adv): return 1/(1+10**(-((rh+adv-ra)/400)))

@st.cache_data(ttl=90)
def get_odds(key,regions):
    r=requests.get(ODDS_URL,params={'apiKey':key,'regions':regions,'markets':'h2h','oddsFormat':'decimal','dateFormat':'iso'},timeout=30)
    r.raise_for_status(); return r.json(),r.headers.get('x-requests-remaining','unknown')

with st.sidebar:
    key=st.text_input('The Odds API key',type='password')
    regions=st.multiselect('Bookmaker regions',['us','uk','eu','au'],default=['us'])
    seasons=st.slider('Historical seasons used',3,10,5)
    adv=st.slider('Home advantage (Elo points)',0,100,55)
    min_edge=st.number_input('Minimum model edge (percentage points)',0.,30.,3.,.5)
    run=st.button('Train model and scan',type='primary')

st.write('**Model:** historical NFL results update team Elo ratings. The model estimates win probabilities without using current bookmaker odds to set those probabilities, then compares them with available moneyline prices.')
st.warning('This is a baseline model. It omits injuries, quarterback status, weather and other factors. An apparent edge is a hypothesis, not proof of profit.')
if run:
    if not key or not regions: st.error('Enter your API key and choose a region.')
    else:
        try:
            with st.spinner('Loading historical results and training model...'):
                games=get_games(); ratings,latest=train_elo(games,seasons,adv)
            with st.spinner('Loading current odds...'):
                events,remaining=get_odds(key,','.join(regions))
            st.success(f'Model trained on completed seasons through {latest}. Odds-feed requests remaining: {remaining}.')
            rows=[]
            for ev in events:
                hn,an=ev.get('home_team',''),ev.get('away_team',''); h,a=code(hn),code(an)
                if not h or not a: continue
                p_h=phome(ratings.get(h,1500),ratings.get(a,1500),adv); probs=[]; best={h:None,a:None}
                for book in ev.get('bookmakers',[]):
                    for market in book.get('markets',[]):
                        if market.get('key')!='h2h': continue
                        vals=[]
                        for o in market.get('outcomes',[]):
                            c=code(o.get('name'))
                            try: price=float(o['price'])
                            except (ValueError,TypeError,KeyError): continue
                            if c and price>1: vals.append((c,price,1/price))
                        total=sum(v[2] for v in vals)
                        if not total: continue
                        normalized={c:p/total for c,price,p in vals}
                        if h in normalized: probs.append(normalized[h])
                        for c,price,_ in vals:
                            if c in best and (best[c] is None or price>best[c]['odds']): best[c]={'odds':price,'book':book.get('title',book.get('key','?'))}
                if not probs: continue
                market_h=sum(probs)/len(probs)
                for c,name,p in [(h,hn,p_h),(a,an,1-p_h)]:
                    b=best[c]
                    if not b: continue
                    rows.append({'event':f'{an} @ {hn}','start_time':ev.get('commence_time',''),'selection':name,'odds':b['odds'],'bookmaker':b['book'],'model_probability_%':round(100*p,2),'market_consensus_%':round(100*(market_h if c==h else 1-market_h),2),'implied_probability_%':round(100/b['odds'],2),'edge_pp':round(100*(p-1/b['odds']),2),'estimated_EV_%':round(100*(p*b['odds']-1),2),'retrieved_utc':datetime.now(timezone.utc).isoformat(timespec='seconds')})
            if not rows: st.info('No comparable NFL odds returned. Check your API plan, region and current market coverage.')
            else:
                df=pd.DataFrame(rows).sort_values('estimated_EV_%',ascending=False)
                st.subheader('All estimates'); st.dataframe(df,use_container_width=True,hide_index=True)
                st.subheader('Candidates above edge threshold'); shortlist=df[df.edge_pp>=min_edge]
                if shortlist.empty: st.write('No candidates passed. Do not force a bet.')
                else: st.dataframe(shortlist,use_container_width=True,hide_index=True)
                st.download_button('Export CSV',df.to_csv(index=False).encode(),file_name='nfl_model_scan.csv',mime='text/csv')
        except Exception as e: st.error(f'Data error: {e}')
else:
    st.info('Enter your odds API key and tap **Train model and scan**. Start with one region to conserve free requests.')
