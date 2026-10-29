"""Publish same-evening 4D results, marked provisional, before the main archive has them.

Takes draws newer than data/sp_4d_prizes.csv from the fast feed and keeps only those that
look cleanly parsed:
  - draw numbers follow on from the archive with no gaps, and dates move forward
  - 1st, 2nd and 3rd, 10 Starter and 10 Consolation prizes, all four-digit numbers
  - the Starter and Consolation lists are each in ascending order (the feed sorts them; a
    number out of order means a parsing slip, as happened when a number won two prizes)
  - the draw is not dated in the future (Singapore time)
The result goes to data/live.json. A draw already published stays until the archive has it,
even if a stale copy of the feed no longer lists it; if the feed changes a draw's result, the
new one is used. Once the archive has a draw, it drops out of live.json and the archive's
version is used, so provisional results are always replaced by confirmed ones.

  python3 scripts/update_live.py            refresh data/live.json; prints new draw numbers
  python3 scripts/update_live.py --check F  validate a saved feed file instead of fetching
Writes `new_draws=5555 5556` to $GITHUB_OUTPUT when draws are added.
"""
import datetime, json, os, pathlib, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'scripts'))
from update_data import DATA, CROSSCHECK, fetch, parse, stamp, warn  # noqa: E402

LIVE = ROOT / 'data' / 'live.json'
SGT = datetime.timezone(datetime.timedelta(hours=8))


def is4(x):
    return isinstance(x, str) and len(x) == 4 and x.isdigit()


def provisional(feed, archive):
    last = max(archive)
    last_date = archive[last]['date'].replace('/', '-')
    today = datetime.datetime.now(SGT).date().isoformat()
    rows = sorted((e for e in feed if isinstance(e.get('draw_no'), int) and e['draw_no'] > last), key=lambda e: e['draw_no'])
    out, expect, prev = [], last + 1, last_date
    for e in rows:
        n = e['draw_no']
        if n != expect:
            warn(f'feed skips from draw {expect - 1} to {n}; stopping there')
            break
        date, top = e.get('draw_date', ''), [e.get('first'), e.get('second'), e.get('third')]
        st, co = e.get('starters') or [], e.get('consolations') or []
        problem = None
        try:
            datetime.date.fromisoformat(date)
        except ValueError:
            problem = f'bad date {date!r}'
        if not problem and not (prev < date <= today):
            problem = f'date {date} is not after {prev} or is in the future'
        elif not problem and not all(is4(x) for x in top + st + co):
            problem = 'a prize is not a four-digit number'
        elif not problem and (len(st) != 10 or len(co) != 10):
            problem = f'{len(st)} Starter and {len(co)} Consolation prizes, expected 10 each'
        elif not problem and (st != sorted(st) or co != sorted(co)):
            problem = 'Starter or Consolation prizes out of order (likely a parsing slip)'
        if problem:
            warn(f'draw {n} from the fast feed not used: {problem}')
            break
        out.append({'draw': n, 'date': date.replace('-', '/'), 'numbers': top + st + co})
        expect, prev = n + 1, date
    return out


def merge(old, fresh, last):
    byno = {d['draw']: d for d in old if d['draw'] > last}
    for d in fresh:
        had = byno.get(d['draw'])
        if had and had['numbers'] != d['numbers']:
            warn(f"the fast feed changed its result for draw {d['draw']}; publishing the new one")
        byno[d['draw']] = d
    out, n = [], last + 1
    while n in byno:
        out.append(byno[n])
        n += 1
    return out


def main():
    archive = parse(DATA.read_text())
    if '--check' in sys.argv:
        feed = json.loads(pathlib.Path(sys.argv[sys.argv.index('--check') + 1]).read_text())['fourD']
        print(json.dumps(provisional(feed, archive)))
        return
    old = json.loads(LIVE.read_text()) if LIVE.exists() else {'draws': []}
    try:
        fresh = provisional(json.loads(fetch(CROSSCHECK))['fourD'], archive)
    except Exception as e:
        warn(f'fast feed unavailable ({e}); keeping the provisional draws already published')
        fresh = []
    draws = merge(old['draws'], fresh, max(archive))
    # Draws the archive now has are dropped. Flag any provisional result it contradicts.
    for d in old['draws']:
        if d['draw'] in archive and archive[d['draw']]['nums'][:3] != d['numbers'][:3]:
            warn(f"provisional draw {d['draw']} differed from the archive; the archive's result is used")
    new = {'draws': draws}
    if new != old:
        LIVE.write_text(json.dumps(new, indent=1) + '\n')
        stamp()
    added = [d['draw'] for d in draws if d['draw'] not in {x['draw'] for x in old['draws']}]
    print(f"provisional draws: {[d['draw'] for d in draws] or 'none'}; new: {added or 'none'}")
    if added and os.environ.get('GITHUB_OUTPUT'):
        with open(os.environ['GITHUB_OUTPUT'], 'a') as f:
            f.write(f"new_draws={' '.join(map(str, added))}\n")


if __name__ == '__main__':
    main()
