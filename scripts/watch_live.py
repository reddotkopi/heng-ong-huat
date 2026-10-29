"""Wait for tonight's 4D result in the fast feed, for the evening watcher workflow.

GitHub starts scheduled runs late or not at all, most of all in the evening, so the workflow
starts early in the afternoon and this script waits for the result instead of relying on a
run landing at the right minute. It ends:
  found=true     the feed has a draw newer than the published data that passes update_live's
                 checks: the workflow then starts the deploy workflow to publish it
  handover=true  this run's time is nearly used up before tonight's result: the workflow starts
                 a fresh run to keep watching (GitHub stops jobs after 6 hours)
  (neither)      nothing to wait for: not a draw day, tonight's draw is already published, or
                 no result by 10.30pm
It checks the feed's branch head with git ls-remote every 60 seconds and reads the file at
that exact commit, because raw.githubusercontent.com caches the branch URL for minutes.

  python3 scripts/watch_live.py            watch (writes found/handover to $GITHUB_OUTPUT)
  WATCH_BUDGET_MIN=330                     minutes this run may use (default 330)
"""
import datetime, json, os, pathlib, sys, time

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'scripts'))
from update_data import CROSSCHECK, DATA, fetch, parse, pinned, warn  # noqa: E402
from update_data import load_disputes  # noqa: E402
from update_live import LIVE, SGT, provisional  # noqa: E402

DRAW_DAYS = {2, 5, 6}  # Wednesday, Saturday, Sunday
OPEN = datetime.time(18, 35)   # the draw is at 6.30pm; results usually appear 20 to 30 minutes later
CLOSE = datetime.time(22, 30)
POLL_S = 60
HANDOVER_MARGIN = datetime.timedelta(minutes=10)


def now():
    return datetime.datetime.now(SGT)


def output(**kv):
    print(' '.join(f'{k}={v}' for k, v in kv.items()))
    if os.environ.get('GITHUB_OUTPUT'):
        with open(os.environ['GITHUB_OUTPUT'], 'a') as f:
            for k, v in kv.items():
                f.write(f'{k}={v}\n')


def published():
    archive = parse(DATA.read_text())
    live = json.loads(LIVE.read_text())['draws'] if LIVE.exists() else []
    dates = {archive[max(archive)]['date']} | {d['date'] for d in live}
    return archive, max([max(archive)] + [d['draw'] for d in live]), dates


def read_feed():
    return json.loads(fetch(CROSSCHECK))


def main():
    start = now()
    end_of_run = start + datetime.timedelta(minutes=int(os.environ.get('WATCH_BUDGET_MIN', '330')))
    archive, newest, dates = published()
    today = start.date()
    opens = datetime.datetime.combine(today, OPEN, SGT)
    closes = datetime.datetime.combine(today, CLOSE, SGT)

    feed = None
    try:
        feed = read_feed()
    except Exception as e:
        warn(f'fast feed unavailable at start ({e}); will keep trying')
    upcoming = ((feed or {}).get('upcoming') or {}).get('fourD') or {}
    if today.weekday() not in DRAW_DAYS and upcoming.get('drawDate') != today.isoformat():
        print(f'{today} is not a draw day')
        return output(found='false', handover='false')
    if today.strftime('%Y/%m/%d') in dates:
        print(f"tonight's draw ({today}) is already published")
        return output(found='false', handover='false')

    # A run that starts early cannot last until the evening is over: sleep, then hand over just
    # before the window opens, so a fresh run covers the whole evening.
    if start < opens and end_of_run < closes:
        until = min(end_of_run, opens - HANDOVER_MARGIN)
        print(f'sleeping until {until:%H:%M} SGT, then handing over to a fresh run')
        time.sleep(max(0, (until - now()).total_seconds()))
        return output(found='false', handover='true')
    if now() < opens:
        print(f'waiting until {opens:%H:%M} SGT')
        time.sleep(max(0, (opens - now()).total_seconds()))

    last_url = None
    while True:
        t = now()
        if t > closes:
            warn(f'no result in the fast feed by {CLOSE:%H:%M} SGT; the archive will have it tomorrow')
            return output(found='false', handover='false')
        if t + datetime.timedelta(seconds=POLL_S) > end_of_run - HANDOVER_MARGIN:
            print('time is nearly up; handing over to a fresh run')
            return output(found='false', handover='true')
        url = pinned(CROSSCHECK)
        if url != last_url or url == CROSSCHECK:  # new commit (or ls-remote failed: just re-read)
            last_url = url
            try:
                draws = provisional(read_feed()['fourD'], archive, set(load_disputes()['draws']))
            except Exception as e:
                warn(f'could not read the fast feed ({e})')
                draws = []
            fresh = [d['draw'] for d in draws if d['draw'] > newest]
            if fresh:
                print(f'{t:%H:%M:%S} SGT: draw {fresh[-1]} is in the fast feed')
                return output(found='true', handover='false')
        time.sleep(POLL_S)


if __name__ == '__main__':
    main()
