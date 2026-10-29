"""Encode the Singapore Pools 4D history CSV into a compact string the page embeds.

Format: draws joined by ';' in draw-number order (draw n is index n-1). Each draw is
'<days since the previous draw>,<winning numbers as one run of digits, 4 per number>'.
Draw 1's day delta counts from 31 May 1986 (so it is 0). Numbers keep the source order:
1st, 2nd, 3rd, then the Starter prizes, then the Consolation prizes.
"""
import collections, csv, datetime, json, pathlib, sys

EPOCH = datetime.date(1986, 5, 31)


def read_draws(path, corrections=True):
    draws = collections.OrderedDict()
    with open(path, newline='') as f:
        for r in csv.DictReader(f):
            d = draws.setdefault(int(r['draw_number']), {'date': r['date'], 'nums': []})
            if d['date'] != r['date']:
                raise ValueError(f"draw {r['draw_number']} has two dates")
            if not (len(r['number']) == 4 and r['number'].isdigit()):
                raise ValueError(f"draw {r['draw_number']} has a bad number {r['number']!r}")
            d['nums'].append(r['number'])
    if corrections:
        apply_corrections(draws, pathlib.Path(path).with_name('corrections.json'))
    return draws


def apply_corrections(draws, path):
    """data/corrections.json, if present, overrides the archive's 1st, 2nd and 3rd prizes and/or the
    date of a draw found to be wrong (checked against Singapore Pools), for example
        {"5555": {"top": ["1234", "5678", "9012"], "date": "2026/10/31", "note": "1st and 2nd were swapped"}}
    """
    if not path.exists():
        return
    try:
        fixes = json.loads(path.read_text())
        for k, v in fixes.items():
            n, top, date = int(k), v.get('top'), v.get('date')
            if n not in draws or (top is None and date is None):
                raise ValueError(f'draw {k}: needs a stored draw and a "top" or a "date"')
            if top is not None:
                if len(top) != 3 or not all(isinstance(x, str) and len(x) == 4 and x.isdigit() for x in top):
                    raise ValueError(f'draw {k}: "top" needs three four-digit numbers')
                draws[n]['nums'][:3] = top
            if date is not None:
                datetime.datetime.strptime(date, '%Y/%m/%d')
                draws[n]['date'] = date
    except (ValueError, KeyError, TypeError, AttributeError) as e:
        raise SystemExit(f'::error::data/corrections.json is not valid ({e}); fix the edit')


def encode(path):
    draws = read_draws(path)
    keys = list(draws)
    if keys != list(range(1, len(keys) + 1)):
        raise ValueError('draw numbers must run 1..N without gaps')
    prev, parts = EPOCH, []
    for k in keys:
        day = datetime.date(*map(int, draws[k]['date'].split('/')))
        delta = (day - prev).days
        if delta < 0:
            raise ValueError(f'draw {k} is dated before the draw before it')
        parts.append(f"{delta},{''.join(draws[k]['nums'])}")
        prev = day
    meta = {'draws': keys[-1], 'last_date': prev.isoformat(), 'numbers': sum(len(d['nums']) for d in draws.values())}
    return ';'.join(parts), meta


if __name__ == '__main__':
    enc, meta = encode(sys.argv[1])
    if len(sys.argv) > 2:
        open(sys.argv[2], 'w').write(enc)
    print(json.dumps(meta))
