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

4D draws are on Wednesday, Saturday and Sunday at 6.30pm Singapore time. The second feed usually
has the result 20 to 30 minutes later; the archive has it the next morning.

- **On draw evenings**, the `Watch for tonight's results` workflow (`watch.yml`) waits for the
  result in the second feed and, the minute it appears, starts `Update draw results and deploy`
  (`deploy.yml`), which publishes it as **provisional**, marked so in the app. GitHub starts
  scheduled runs late and sometimes not at all, especially in the evening, so the watcher has
  several starters through the afternoon and hands over to a fresh run before GitHub's 6-hour job
  limit. `deploy.yml` also has three draw-evening runs of its own, as a fallback.
- **The day after**, at 11.20am and 3.20pm on Thursday, Sunday and Monday, `deploy.yml` checks the
  confirmed archive. A confirmed draw replaces the provisional one.

Scheduled and watcher runs redeploy the site when it differs from what they would build: new
results, or an earlier run whose deploy failed (its alert is then sent too). Both feeds are read at
their latest commit, because raw.githubusercontent.com can serve a file up to 5 minutes old. GitHub
disables scheduled workflows in a public repository after 60 days without activity; it is not
documented whether the automatic result commits count, so if the Actions tab shows a workflow as
disabled, enable it there.

The app fetches `latest.json` when it opens and every 2 minutes during draw evenings, so new results
appear without reinstalling. It tells you if a number in your journal came up.

`scripts/update_data.py` accepts a new archive file only if:

- every number is four digits, the draw numbers run without gaps, and the dates never go backwards
- every draw since 6 April 1991 has 23 numbers
- it keeps every stored draw unchanged and adds to the end

Otherwise it keeps the stored results and the run fails (see below); if the archive simply cannot
be reached, it only logs a warning. Draws before 6 April 1991 were tied to horse
races, so 210 of them have 17 to 27 winning numbers, and their records do not separate Starter from
Consolation.

**When the two sources disagree.** The archive is the confirmed source. If its 1st, 2nd or 3rd
prize or the date of a new draw differs from the fast feed's (or, if the feed cannot be read, from
the provisional result published that evening), the archive's result is published, the app and a
correction alert put right the provisional result, and the workflow run is marked failed so the
repository owner is emailed. Check the draw on Singapore Pools' site. If the archive is wrong, add
the right result to `data/corrections.json`, for example
`{"5555": {"top": ["1234", "5678", "9012"], "note": "1st and 2nd were swapped"}}` (a `"date"`,
written `"2026/10/04"`, can be corrected too). Every published result then uses it, and a
correction alert goes out. If the fast feed corrects a provisional draw itself, the app shows the
new result and a correction alert goes out.

The archive may later put right a draw it already published: that is accepted when the new version
agrees with the fast feed, or when its top three are the ones in `data/corrections.json` (the entry
can then be removed). Any other change to a stored draw, or a new file that fails the checks above,
is not accepted: confirmed results stop, and every run fails until it is looked into, so it cannot
go unnoticed. Same-evening results keep coming meanwhile.

`scripts/update_live.py` takes a same-evening draw only if it follows on from the archive with no gap,
is not dated in the future, has 23 four-digit numbers, and lists its Starter and Consolation prizes
in order (the feed sorts them, so a number out of order means it was misread).

## Result alerts (optional)

The app can send a phone notification when each draw's results are in, through
[OneSignal](https://onesignal.com) (free for web push). Until it is set up, the alerts card stays
hidden and the Action sends nothing.

1. Sign up at onesignal.com and create an app. Choose **Web** as the platform and **Custom Code** as
   the integration. (Not "Typical Site": that ignores the app's settings and looks for OneSignal's
   files at the root of reddotkopi.github.io, where they are not.)
2. Set **Site Name** to `Heng Ong Huat` and **Site URL** to `https://reddotkopi.github.io` (the origin
   only, no path). Add the icon `https://reddotkopi.github.io/heng-ong-huat/icons/icon-512.png`.
   Leave the prompts off: the app asks for permission itself, only when someone taps
   **Turn on alerts**.
3. Turn on the **Safari** platform in the same app's web settings. No certificate is needed. Without
   it, alerts cannot be turned on on iPhone, iPad or Mac Safari.
4. Copy the **App ID**. In this repository open **Settings → Secrets and variables → Actions →
   Variables**, and add a variable named `ONESIGNAL_APP_ID` with the App ID. It is not secret: it
   ends up in the page.
5. In OneSignal open **Settings → Keys & IDs** and create an **API key** (it is shown only once).
   In GitHub, on the **Secrets** tab of the same page, add a secret named `ONESIGNAL_REST_API_KEY`
   with the key. Never put this key anywhere else.
6. Run `Update draw results and deploy` from the **Actions** tab, so the app is rebuilt with alerts.

Use this OneSignal app for this site only. All of reddotkopi's GitHub Pages sites share the origin
`https://reddotkopi.github.io`, and OneSignal allows one app per origin. Alerts go to the `All`
audience (everyone subscribed); set a repository variable `ONESIGNAL_SEGMENT` to use another segment.
OneSignal's free plan covers web push to up to 10,000 subscribers per send.

How it behaves:

- Alerts are opt-in, from the **Result alerts** card on the History tab. OneSignal's code is loaded only
  after someone turns alerts on. It runs in its own service worker under `push/`, apart from the
  app's offline cache. When alerts are turned on or off (and on the next visit after that), about
  once a week while they are on, and when the phone's push address changes, OneSignal receives the
  phone's push address, IP address, device and browser version, language and time zone, and for
  the rest of that visit, when the app is in use. It also learns whether alerts arrive and are
  opened, and when one arrives the phone may download OneSignal's alert code from its servers. It
  gets nothing from the journal. Turning alerts off also drops the phone's push subscription, so it
  works offline too.
- On iPhone and iPad, alerts need iOS 16.4 or later and the app added to the home screen. In a
  Safari tab the card explains this.
- One alert per new draw: `4D Draw 5555 results (provisional)` with the top three prizes. If the
  confirmed results differ, a correction follows. Re-running a job does not send an alert twice.
  Tapping an alert opens the app, which shows any results that came in since it was last opened.

## Publish with GitHub Pages

1. In **Settings → Pages**, set **Source** to **GitHub Actions**.
2. On a free GitHub plan, Pages needs the repository to be public. A private repository needs GitHub Pro or Team.
3. Push to `main`, or run the workflow from the **Actions** tab.

The site is then at `https://reddotkopi.github.io/heng-ong-huat/`.

## Develop

```sh
python3 scripts/build.py            # site/ (the app) and dist/artifact.html (Claude artifact body)
python3 -m http.server -d site 8000 # preview at http://localhost:8000
python3 scripts/update_data.py      # fetch new archive results now
python3 scripts/update_live.py      # fetch same-evening (provisional) results now
python3 scripts/watch_live.py       # wait for tonight's result (what watch.yml runs)
```

Tests use Playwright with Chromium (`npm i playwright`, then `npx playwright install chromium`):

```sh
node tests/run.js site/index.html tests/shots   # ritual, history accuracy, layout, motion
node tests/pwa.js                               # installable, offline, service worker
node tests/live_check.js                        # same-evening results appear and get confirmed
ONESIGNAL_APP_ID=12345678-abcd-4ef0-9abc-1234567890ab python3 scripts/build.py && node tests/alerts_check.js
```

| Path | What it is |
|---|---|
| `src/heng-ong-huat.html` | The whole app: markup, styles and script. `__HISTORY_DATA__`, `__LIVE_DATA__` and `__ONESIGNAL_APP_ID__` are filled in at build time. |
| `data/sp_4d_prizes.csv` | Every winning number: `draw_number,number,date`, in prize order. |
| `data/live.json` | Same-evening draws not yet in the archive (provisional). |
| `data/corrections.json` | Optional: the owner's fixes for a draw the archive has wrong. |
| `data/updated.txt`, `data/corrections.sha` | When the published results last changed (the app ignores older copies), and which corrections that includes. |
| `scripts/` | Build, data encoding, the two result updaters, the evening watcher and `notify.py` (result alerts). |
| `pwa/sw.js` | Offline cache. |
| `assets/icons/` | App icons. |

## Play responsibly

Heng Ong Huat is for tradition and fun. It does not sell or place bets and is not affiliated with
Singapore Pools. Every 4D number has the same 1 in 10,000 chance at each prize. You must be 18 to buy
4D at an outlet and 21 to bet online. National Problem Gambling Helpline: **1800-6-668-668**
(8am to 11pm daily).
