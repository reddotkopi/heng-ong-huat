"""Refresh data/sp_4d_prizes.csv from the community archive of Singapore Pools 4D results.

The new file replaces the old one only if it passes every check:
  - the same header, every number is four digits, draw numbers run 1..N with no gaps,
    one date per draw and dates never go backwards
  - every draw since 6 Apr 1991 has exactly 23 numbers
  - it is not shorter than the old file and every old draw is unchanged
  - its 1st, 2nd and 3rd prizes agree with a second, independent feed wherever both have the draw
Otherwise the old file is kept and a warning is printed, so the site still builds.

  python3 scripts/update_data.py          refresh (exit 0 even when the source is unusable)
  python3 scripts/update_data.py --last   print the latest draw in the current file
"""
import csv, datetime, io, json, pathlib, sys, time, urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
DATA = ROOT / 'data' / 'sp_4d_prizes.csv'
SOURCE = 'https://raw.githubusercontent.com/playingmeow/SingaporePools/main/4d_prizes.csv'
CROSSCHECK = 'https://raw.githubusercontent.com/darrentan90/hobeh-draws/main/latest.json'
HEADER = ['draw_number', 'number', 'date']
ELECTRONIC_ERA = '1991/04/06'


def warn(msg):
    print(f'::warning::{msg}')


def fetch(url, tries=4):
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


def crosscheck(draws):
    try:
        feed = json.loads(fetch(CROSSCHECK))['fourD']
    except Exception as e:
        warn(f'cross-check feed unavailable ({e}); skipping it')
        return
    checked = 0
    for e in feed:
        n = e.get('draw_no')
        if n is None or n not in draws:
            continue
        ours = draws[n]['nums'][:3]
        theirs = [e['first'], e['second'], e['third']]
        if ours != theirs:
            raise ValueError(f'draw {n}: top three {ours} disagree with the cross-check feed {theirs}')
        if draws[n]['date'].replace('/', '-') != e['draw_date']:
            raise ValueError(f"draw {n}: date {draws[n]['date']} disagrees with the cross-check feed {e['draw_date']}")
        checked += 1
    print(f'cross-checked the top three prizes of {checked} draws')


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
        crosscheck(new)
    except Exception as e:
        warn(f'kept the existing results: {e}')
        return
    if max(new) == max(old):
        print(f'no new draws; latest is {last(old)[0]} ({last(old)[1]})')
        return
    DATA.write_text(text if text.endswith('\n') else text + '\n')
    print(f'added draws {max(old) + 1} to {max(new)}; latest is {last(new)[1]}')


if __name__ == '__main__':
    main()
