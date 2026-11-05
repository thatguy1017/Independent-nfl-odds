# Multi-Sport Odds Scanner

Streamlit app for odds research across up to 16 soccer competitions and NBA.

## Current features
- Soccer match outcome (1X2 / h2h) odds.
- NBA moneyline (`h2h`), point spread (`spreads`) and over/under (`totals`) when available on your plan.
- Shows best listed price by outcome, average de-vigged bookmaker probability, implied probability, market edge and market-based estimated EV.
- CSV export.
- Checks the sports catalogue returned by the API key and reports competitions that are not available.

## Important limitation
This version is an **odds comparison and market-screening tool**, not yet an independent prediction model. Market-based estimated EV is only a screening signal; it is not proof of a true edge or profit. Separately trained soccer and NBA models need reliable historical results and out-of-sample validation before their predictions should be trusted.

## Deploy on Streamlit Community Cloud
1. Extract the ZIP.
2. In your GitHub repository, replace the old `app.py` and `requirements.txt` with these two files. Keep the repository's `README.md` if you prefer, or upload this README too.
3. Commit the changes.
4. Open your existing Streamlit Community Cloud app. It normally rebuilds automatically after a GitHub commit. If not, open app settings and reboot/redeploy.
5. Enter your Odds API key privately in the app sidebar. Never commit your API key to GitHub.

## API usage
The app makes one odds request per selected competition, plus a sports-catalogue request. Start with two or three competitions and inspect the remaining request quota before scanning all 15 soccer competitions plus NBA. API sport/market coverage depends on the current provider catalogue, region, and subscription.

## Current competition keys
The app checks the live sports catalogue before requesting odds, so unsupported keys are skipped and reported. Catalogues can change.


## Soccer market additions
The sidebar lets you select soccer markets including match result (1X2), draw no bet, Asian handicap/spread, full-match totals, team total goals, first/second-half totals and team totals, first/second-half results and handicaps, both teams to score, and double chance.

Availability varies by competition, bookmaker region, and API plan. If a requested market is unsupported, reduce the selected markets and retry. "Team total goals" means a betting line for how many goals a specific team scores; it is not a statistical expected-goals (xG) forecast. Displayed probabilities are market-derived estimates, not independently trained predictions.


### Additional soccer markets
Featured soccer markets (1X2, handicap, full-match totals) use the standard odds endpoint. Additional markets use the event-specific endpoint and may consume more API credits. If a batch of extra markets is rejected, the app retries each selected market individually.
