"""Refresh data/sp_4d_prizes.csv from the community archive of Singapore Pools 4D results.

The new file replaces the old one only if it passes every check:
  - the same header, every number is four digits, draw numbers run 1..N with no gaps,
    one date per draw and dates never go backwards
  - every draw since 6 Apr 1991 has exactly 23 numbers
  - it is not shorter than the old file and every old draw is unchanged
  - its 1st, 2nd and 3rd prizes agree with a second, independent feed wherever both have the draw
Otherwise the old file is kept and a warning is printed, so the site still builds.

When the two sources disagree on a draw not yet stored, nobody can tell which is right, so the
draw is recorded in data/disputed.json and held back: update_live.py withdraws it from the site,
an alert says so, and the workflow run fails so the maintainer hears about it. It stays held while
the fast feed cannot be read. It clears by itself if either source changes to agree. Otherwise,
after checking Singapore Pools, add the draw number to "use_archive" (the archive is right) or to
"use_feed" (the fast feed is right: the archive then stays where it is and new draws keep coming
from the fast feed, as provisional, until the archive is fixed). Leave the number there: the fast
feed keeps each draw for about a year.

  python3 scripts/update_data.py          refresh (exit 0 even when the source is unusable)
  python3 scripts/update_data.py --last   print the latest draw in the current file
  python3 scripts/update_data.py --disputed   print the draws held back because the sources disagree
"""
import csv, datetime, io, json, pathlib, re, subprocess, sys, time, urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
DATA = ROOT / 'data' / 'sp_4d_prizes.csv'
DISPUTES = ROOT / 'data' / 'disputed.json'
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


def load_disputes():
    """data/disputed.json. A hand edit that does not parse stops the run, rather than silently
    clearing the disputes and republishing the draws in doubt."""
    try:
        d = json.loads(DISPUTES.read_text())
    except FileNotFoundError:
        return {'draws': {}, 'use_archive': [], 'use_feed': []}
    except ValueError as e:
        raise SystemExit(f'::error::data/disputed.json is not valid JSON ({e}); fix the edit')
    try:
        return {'draws': {int(k): v for k, v in d.get('draws', {}).items()},
                'use_archive': [int(x) for x in d.get('use_archive', [])],
                'use_feed': [int(x) for x in d.get('use_feed', [])]}
    except (AttributeError, TypeError, ValueError) as e:
        raise SystemExit(f'::error::data/disputed.json is not in the expected form ({e}); fix the edit')


def save_disputes(d):
    text = json.dumps({'draws': {str(k): v for k, v in sorted(d['draws'].items())},
                       'use_archive': sorted(d['use_archive']), 'use_feed': sorted(d['use_feed'])}, indent=1) + '\n'
    if not DISPUTES.exists() or DISPUTES.read_text() != text:
        DISPUTES.write_text(text)


def stamp():
    """Record when the published results last changed (the app ignores older copies)."""
    UPDATED.write_text(datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ') + '\n')


def crosscheck(draws, stored):
    disputes = load_disputes()
    settled = set(disputes['use_archive']) | set(disputes['use_feed'])
    try:
        feed = json.loads(fetch(CROSSCHECK))['fourD']
    except Exception as e:
        held = sorted(n for n in disputes['draws'] if n > stored and n not in settled)
        if held:  # without the feed nothing can vouch for a disputed draw: keep holding it
            raise ValueError(f'cross-check feed unavailable ({e}) while draw {held} is disputed; still held back')
        warn(f'cross-check feed unavailable ({e}); skipping it')
        return
    # a dispute stays open while the feed (or this copy of it) does not list the draw
    listed = {e.get('draw_no') for e in feed}
    found = {n: v for n, v in disputes['draws'].items() if n > stored and n not in listed and n not in settled}
    wrong_archive = []
    checked = 0
    for e in feed:
        n = e.get('draw_no')
        if n is None or n not in draws:
            continue
        ours = draws[n]['nums'][:3]
        theirs = [e['first'], e['second'], e['third']]
        if ours != theirs:
            if n in disputes['use_archive']:  # stays listed while the feed still has the draw (about a year)
                warn(f"draw {n}: the archive's top three {ours} differ from the fast feed's {theirs}; using the archive, as data/disputed.json says")
            elif n in disputes['use_feed']:
                wrong_archive.append(n)
            elif n <= stored:
                raise ValueError(f'draw {n}: top three {ours} disagree with the cross-check feed {theirs}')
            else:
                found[n] = {'archive': ours, 'feed': theirs}
            continue
        if draws[n]['date'].replace('/', '-') != e['draw_date']:
            raise ValueError(f"draw {n}: date {draws[n]['date']} disagrees with the cross-check feed {e['draw_date']}")
        checked += 1
    disputes['draws'] = found
    save_disputes(disputes)
    if found:
        raise ValueError('the archive and the fast feed disagree on the top three of draw '
                         + ', '.join(f"{n} (archive {v['archive']}, feed {v['feed']})" for n, v in sorted(found.items()))
                         + '; held back until they agree (see data/disputed.json)')
    if wrong_archive:
        raise ValueError(f"the archive has draw {', '.join(map(str, wrong_archive))} wrong (use_feed in data/disputed.json); "
                         "keeping the stored results, and the fast feed's draws stay provisional")
    print(f'cross-checked the top three prizes of {checked} draws')


def last(draws):
    k = max(draws)
    return k, draws[k]['date']


def main():
    if '--disputed' in sys.argv:
        print(' '.join(map(str, sorted(load_disputes()['draws']))))
        return
    old = parse(DATA.read_text())
    if '--last' in sys.argv:
        k, d = last(old)
        print(f'{k} ({d})')
        return
    try:
        text = fetch(SOURCE)
        new = parse(text)
        if max(new) < max(old):
            raise ValueError(f'source has {max(new)} draws, fewer than the {max(old)} already stored')
        for k, d in old.items():
            if new[k] != d:
                raise ValueError(f'source changed the already-stored draw {k}')
        crosscheck(new, max(old))
    except Exception as e:
        warn(f'kept the existing results: {e}')
        return
    if max(new) == max(old):
        print(f'no new draws; latest is {last(old)[0]} ({last(old)[1]})')
        return
    DATA.write_text(text if text.endswith('\n') else text + '\n')
    stamp()
    print(f'added draws {max(old) + 1} to {max(new)}; latest is {last(new)[1]}')


if __name__ == '__main__':
    main()
