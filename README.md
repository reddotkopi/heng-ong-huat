# Heng Ong Huat 兴旺发

A phone web app for the altar ritual of asking your ancestors or a deity for a Singapore 4D number,
with every Singapore Pools 4D result since 1986 built in.

1. **Write the slips.** Ten slips of paper, 0 to 9, are written by brush and folded twice.
2. **Pray (拜).** Hold the phone flat between your palms and bow, or tap Bow, until a slip falls from your cupped hands.
3. **Unfold it** to read the digit.
4. **Throw the moon blocks (博杯).** 圣杯 (one flat face up, one round face up) keeps the digit.
   笑杯 (both flat faces up) means throw again. 阴杯 (both round faces up) folds the slip back into the pool.
5. Repeat for four digits. Slips always go back into the pool, so digits can repeat and every number
   from 0000 to 9999 is equally likely.

The History tab looks up any number (wins by prize, first and last win, its iBet arrangements),
finds the draws on dates that matter to you, checks altar numbers from the news against the record,
and shows that the digits drawn are even. Every count is shown next to what chance alone predicts.

## Install it on your phone

- **iPhone:** open the site in Safari, tap Share, then **Add to Home Screen**.
- **Android:** open the site in Chrome, open the menu, then **Install app**.

Then open it from the home screen, tap **Begin**, and allow motion access when asked.

- Motion works only when the app is opened from its https address: in Safari, in Chrome, or from the
  home screen. It does not work inside the Claude artifact viewer, which blocks phone sensors.
- If you tap Don't Allow on iPhone, Safari may not ask again until it restarts or the site's data is
  cleared. Every motion also has a button, so the whole ritual works by touch.
- The journal of received numbers is kept on the phone. The home-screen app keeps its own copy,
  separate from Safari's.
- After the first visit the app works offline.

## Draw results

The results come from a community archive of Singapore Pools 4D results
([playingmeow/SingaporePools](https://github.com/playingmeow/SingaporePools), draws from 31 May 1986).
The 1st, 2nd and 3rd prizes are cross-checked against a second, independent feed
([darrentan90/hobeh-draws](https://github.com/darrentan90/hobeh-draws)). The terms for reusing the
results have not been confirmed; check them before promoting the app.

4D draws are on Wednesday, Saturday and Sunday at 6.30pm Singapore time. The GitHub Action
`Update draw results and deploy` runs at 1.20pm and 7.20pm Singapore time on Thursday, Sunday and
Monday. `scripts/update_data.py` accepts a new file only if:

- every number is four digits, the draw numbers run without gaps, and the dates never go backwards
- every draw since 6 April 1991 has 23 numbers
- it keeps every stored draw unchanged and adds to the end
- its top three prizes agree with the second feed

Otherwise it keeps the stored results and logs a warning. Draws before 6 April 1991 were tied to horse
races, so 210 of them have 17 to 27 winning numbers, and their records do not separate Starter from
Consolation.

## Publish with GitHub Pages

1. In **Settings → Pages**, set **Source** to **GitHub Actions**.
2. On a free GitHub plan, Pages needs the repository to be public. A private repository needs GitHub Pro or Team.
3. Push to `main`, or run the workflow from the **Actions** tab.

The site is then at `https://reddotkopi.github.io/heng-ong-huat/`.

## Develop

```sh
python3 scripts/build.py            # site/ (the app) and dist/artifact.html (Claude artifact body)
python3 -m http.server -d site 8000 # preview at http://localhost:8000
python3 scripts/update_data.py      # fetch new results now
```

Tests use Playwright with Chromium (`npm i playwright`, then `npx playwright install chromium`):

```sh
node tests/run.js site/index.html tests/shots   # ritual, history accuracy, layout, motion
node tests/pwa.js                               # installable, offline, service worker
```

| Path | What it is |
|---|---|
| `src/heng-ong-huat.html` | The whole app: markup, styles and script. `__HISTORY_DATA__` is replaced at build time. |
| `data/sp_4d_prizes.csv` | Every winning number: `draw_number,number,date`, in prize order. |
| `scripts/` | Build, data encoding and the data updater. |
| `pwa/sw.js` | Offline cache. |
| `assets/icons/` | App icons. |

## Play responsibly

Heng Ong Huat is for tradition and fun. It does not sell or place bets and is not affiliated with
Singapore Pools. Every 4D number has the same 1 in 10,000 chance at each prize. You must be 18 to buy
4D at an outlet and 21 to bet online. National Problem Gambling Helpline: **1800-6-668-668**
(8am to 11pm daily).
