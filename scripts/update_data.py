"""Refresh data/sp_4d_prizes.csv from the community archive of Singapore Pools 4D results.

The new file replaces the old one only if it passes every check:
  - the same header, every number is four digits, draw numbers run 1..N with no gaps,
    one date per draw and dates never go backwards
  - every draw since 6 Apr 1991 has exactly 23 numbers
  - it is not shorter than the old file and every old draw is unchanged
Otherwise the old file is kept and a warning is printed, so the site still builds.

The archive is the confirmed source. If its 1st, 2nd or 3rd prize or the date of a new draw differs
from the fast feed's (or, when the feed cannot be read, from the provisional result published that
evening), its result is still used (the app and the alerts correct the provisional one), but the
draw is reported with ::error:: and as `disagree=` in $GITHUB_OUTPUT, so the workflow run fails and
the owner is emailed to check it. If the archive turns out to be wrong, put the right result in
data/corrections.json (see encode_history.py).

A stored draw may change only when the archive puts right its own mistake: the new version agrees
with the fast feed, or its top three are the ones in data/corrections.json and nothing else
changed. Any other change, or a file that fails the checks above, keeps the stored results and is
reported as `stalled=` so the run fails: confirmed results stop until it is looked into.

  python3 scripts/update_data.py          refresh (exit 0 even when the source is unusable)
  python3 scripts/update_data.py --last   print the latest draw in the current file
"""
import csv, datetime, hashlib, io, json, os, pathlib, re, subprocess, sys, time, urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
DATA = ROOT / 'data' / 'sp_4d_prizes.csv'
CORRECTIONS = ROOT / 'data' / 'corrections.json'
CORRECTIONS_SEEN = ROOT / 'data' / 'corrections.sha'
UPDATED = ROOT / 'data' / 'updated.txt'
SOURCE = 'https://raw.githubusercontent.com/playingmeow/SingaporePools/main/4d_prizes.csv'
CROSSCHECK = 'https://raw.githubusercontent.com/darrentan90/hobeh-draws/main/latest.json'
HEADER = ['draw_number', 'number', 'date']
ELECTRONIC_ERA = '1991/04/06'


def warn(msg):
    print(f'::warning::{msg}')


def pinned(url):
    """The same raw.githubusercontent.com file at the branch's current commit. The CDN caches the
    branch URL for up to 5 minutes (query strings do not help), but a commit URL is always fresh."""
    m = re.fullmatch(r'https://raw\.githubusercontent\.com/([^/]+)/([^/]+)/main/(.+)', url)
    if not m:
        return url
    owner, repo, path = m.groups()
    try:
        out = subprocess.run(['git', 'ls-remote', f'https://github.com/{owner}/{repo}', 'refs/heads/main'],
                             capture_output=True, text=True, timeout=30, check=True).stdout.split()
        if out and re.fullmatch(r'[0-9a-f]{40}', out[0]):
            return f'https://raw.githubusercontent.com/{owner}/{repo}/{out[0]}/{path}'
    except (OSError, subprocess.SubprocessError):
        pass
    return url


def fetch(url, tries=4):
    url = pinned(url)
    for i in range(tries):
        try:
            with urllib.request.urlopen(url, timeout=30) as r:
                return r.read().decode('utf-8')
        except Exception as e:  # network hiccup: back off and retry
            if i == tries - 1:
                raise
            time.sleep(2 ** (i + 1))


def parse(text):
    rows = list(csv.reader(io.StringIO(text)))
    if not rows or rows[0] != HEADER:
        raise ValueError(f'unexpected header {rows[:1]}')
    draws = {}
    for line, r in enumerate(rows[1:], start=2):
        if len(r) != 3:
            raise ValueError(f'line {line}: expected 3 fields')
        n, num, date = int(r[0]), r[1], r[2]
        if not (len(num) == 4 and num.isdigit()):
            raise ValueError(f'line {line}: bad number {num!r}')
        datetime.datetime.strptime(date, '%Y/%m/%d')
        d = draws.setdefault(n, {'date': date, 'nums': []})
        if d['date'] != date:
            raise ValueError(f'draw {n} has two dates')
        d['nums'].append(num)
    keys = sorted(draws)
    if keys != list(range(1, len(keys) + 1)):
        raise ValueError('draw numbers do not run 1..N without gaps')
    for a, b in zip(keys, keys[1:]):
        if draws[b]['date'] < draws[a]['date']:
            raise ValueError(f'draw {b} is dated before draw {a}')
    for k in keys:
        if draws[k]['date'] >= ELECTRONIC_ERA and len(draws[k]['nums']) != 23:
            raise ValueError(f"draw {k} ({draws[k]['date']}) has {len(draws[k]['nums'])} numbers, expected 23")
    return draws


def stamp():
    """Record when the published results last changed (the app ignores older copies)."""
    UPDATED.write_text(datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ') + '\n')


def output(key, values):
    if values and os.environ.get('GITHUB_OUTPUT'):
        with open(os.environ['GITHUB_OUTPUT'], 'a') as f:
            f.write(f"{key}={' '.join(map(str, values))}\n")


def read_feed():
    """The fast feed's draws, or None when it cannot be read."""
    try:
        return json.loads(fetch(CROSSCHECK))['fourD']
    except Exception as e:
        warn(f'fast feed unavailable ({e})')
        return None


def feed_view(feed):
    """{draw: (date, top three, sorted Starters, sorted Consolations)} from the fast feed or, when it
    cannot be read, from the provisional results already published (its word from that evening)."""
    if feed is None:
        live = ROOT / 'data' / 'live.json'
        draws = json.loads(live.read_text())['draws'] if live.exists() else []
        return {d['draw']: (d['date'].replace('/', '-'), d['numbers'][:3], sorted(d['numbers'][3:13]), sorted(d['numbers'][13:]))
                for d in draws}
    return {e['draw_no']: (e.get('draw_date'), [e.get('first'), e.get('second'), e.get('third')],
                           sorted(e.get('starters') or []), sorted(e.get('consolations') or []))
            for e in feed if isinstance(e.get('draw_no'), int)}


def as_view(d):
    n = d['nums']
    return (d['date'].replace('/', '-'), n[:3], sorted(n[3:13]), sorted(n[13:]))


def check_stored(old, new, view):
    """Stored draws the new file changes. Only the archive putting right its own mistake is let
    through (see above); anything else raises."""
    try:
        fixes = json.loads(CORRECTIONS.read_text()) if CORRECTIONS.exists() else {}
    except ValueError:
        fixes = {}
    fixed = []
    for k, d in old.items():
        n = new[k]
        if n == d:
            continue
        fix = fixes.get(str(k)) if isinstance(fixes, dict) else None
        if view.get(k) == as_view(n) or (isinstance(fix, dict) and n['date'] == d['date'] and n['nums'][3:] == d['nums'][3:] and n['nums'][:3] == fix.get('top')):
            fixed.append(k)
            continue
        raise ValueError(f'the archive changed the already-stored draw {k} ({d["date"]} {d["nums"][:3]} to {n["date"]} {n["nums"][:3]}), '
                         'and the fast feed does not confirm the change')
    return fixed


def crosscheck(draws, stored, view):
    """New draws (not stored yet) whose top three or date differ from the fast feed's."""
    differ, checked = [], 0
    for n in sorted(k for k in view if stored < k <= max(draws)):
        mine, theirs = as_view(draws[n]), view[n]
        if mine[:2] == theirs[:2]:
            checked += 1
            continue
        differ.append(n)
        print(f"::error::draw {n}: the archive has {draws[n]['date']} {mine[1]}, the fast feed {theirs[0]} {theirs[1]}; "
              "the archive's result is used. Check it on Singapore Pools (see README)")
    print(f'cross-checked the top three prizes and date of {checked} new draws')
    return differ


def note_corrections():
    """Moves the results stamp when data/corrections.json changes, so the app takes the corrected
    results as newer than any copy it already has."""
    h = hashlib.sha256(CORRECTIONS.read_bytes()).hexdigest()[:16] if CORRECTIONS.exists() else ''
    if h != (CORRECTIONS_SEEN.read_text().strip() if CORRECTIONS_SEEN.exists() else ''):
        CORRECTIONS_SEEN.write_text(h + '\n')
        stamp()


def last(draws):
    k = max(draws)
    return k, draws[k]['date']


def main():
    old = parse(DATA.read_text())
    if '--last' in sys.argv:
        k, d = last(old)
        print(f'{k} ({d})')
        return
    note_corrections()
    try:
        text = fetch(SOURCE)
    except Exception as e:
        warn(f'archive unavailable ({e}); kept the existing results')
        return
    view = feed_view(read_feed())
    try:
        new = parse(text)
        if max(new) < max(old):
            raise ValueError(f'source has {max(new)} draws, fewer than the {max(old)} already stored')
        fixed = check_stored(old, new, view)
    except Exception as e:
        print(f'::error::kept the existing results: {e}. Confirmed results stop until this is looked into (see README)')
        output('stalled', [max(old)])
        return
    differ = crosscheck(new, max(old), view)
    if new == old:
        print(f'no new draws; latest is {last(old)[0]} ({last(old)[1]})')
        return
    DATA.write_text(text if text.endswith('\n') else text + '\n')
    stamp()
    if fixed:
        print(f"::notice::the archive corrected stored draw {', '.join(map(str, fixed))}; "
              'a data/corrections.json entry for it is no longer needed')
    output('disagree', differ)
    print(f'archive now to draw {max(new)} ({last(new)[1]})')


if __name__ == '__main__':
    main()
