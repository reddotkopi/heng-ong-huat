"""Refresh data/sp_4d_prizes.csv from the community archive of Singapore Pools 4D results.

The new file replaces the old one only if it passes every check:
  - the same header, every number is four digits, draw numbers run 1..N with no gaps,
    one date per draw and dates never go backwards
  - every draw since 6 Apr 1991 has exactly 23 numbers
  - it is not shorter than the old file and every old draw is unchanged
Otherwise the old file is kept and a warning is printed, so the site still builds.

The archive is the confirmed source. If its 1st, 2nd or 3rd prize for a new draw differs from the
fast feed's, its result is still used (and the app and the alerts correct the provisional one),
but the draw is reported with ::error:: and as `disagree=` in $GITHUB_OUTPUT, so the workflow run
fails and the owner is emailed to check it. If the archive turns out to be wrong, put the right
top three in data/corrections.json (see encode_history.py).

  python3 scripts/update_data.py          refresh (exit 0 even when the source is unusable)
  python3 scripts/update_data.py --last   print the latest draw in the current file
"""
import csv, datetime, io, json, os, pathlib, re, subprocess, sys, time, urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
DATA = ROOT / 'data' / 'sp_4d_prizes.csv'
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


def crosscheck(draws, stored):
    """Compare the top three prizes and the date of each draw with the fast feed. Returns the new
    draws (not stored yet) the two disagree on; a stored draw the feed changed later only warns."""
    try:
        feed = json.loads(fetch(CROSSCHECK))['fourD']
    except Exception as e:
        warn(f'cross-check feed unavailable ({e}); skipping it')
        return []
    differ, checked = [], 0
    for e in feed:
        n = e.get('draw_no')
        if not isinstance(n, int) or n not in draws:
            continue
        ours, theirs = draws[n]['nums'][:3], [e.get('first'), e.get('second'), e.get('third')]
        if ours == theirs and draws[n]['date'].replace('/', '-') == e.get('draw_date'):
            checked += 1
            continue
        what = f"draw {n}: the archive has {draws[n]['date']} {ours}, the fast feed {e.get('draw_date')} {theirs}"
        if n <= stored:
            warn(f'{what}; the stored result is kept')
        else:
            differ.append(n)
            print(f"::error::{what}; the archive's result is used. Check it on Singapore Pools (see README)")
    print(f'cross-checked the top three prizes of {checked} draws')
    return differ


def last(draws):
    k = max(draws)
    return k, draws[k]['date']


def main():
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
        differ = crosscheck(new, max(old))
    except Exception as e:
        warn(f'kept the existing results: {e}')
        return
    if max(new) == max(old):
        print(f'no new draws; latest is {last(old)[0]} ({last(old)[1]})')
        return
    DATA.write_text(text if text.endswith('\n') else text + '\n')
    stamp()
    if differ and os.environ.get('GITHUB_OUTPUT'):
        with open(os.environ['GITHUB_OUTPUT'], 'a') as f:
            f.write(f"disagree={' '.join(map(str, differ))}\n")
    print(f'added draws {max(old) + 1} to {max(new)}; latest is {last(new)[1]}')


if __name__ == '__main__':
    main()
