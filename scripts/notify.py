"""Result alerts: tell people who turned them on when new 4D results are published.

The update job notes what the live site shows before refreshing the data (so a deploy that
failed is retried, alert included, by the next run), compares afterwards, and sends one web push
through OneSignal for each change worth knowing about:
  - a new draw (up to the three newest, when several arrive together), provisional or confirmed
  - a correction, when the 1st, 2nd or 3rd prize of a draw changes (the confirmed archive differs
    from the provisional result, the fast feed corrected itself, or data/corrections.json)

  python3 scripts/notify.py --snapshot FILE   save the top three prizes of the draws the live site
                                              shows (its latest.json), or of the repo's data if the
                                              site cannot be reached
  python3 scripts/notify.py --diff FILE       compare with FILE; writes notify=<json> to $GITHUB_OUTPUT
  python3 scripts/notify.py --describe        one line about the published results, for commit messages
  python3 scripts/notify.py --send            send $NOTIFY (from --diff) to subscribers; needs
                                              ONESIGNAL_APP_ID and ONESIGNAL_REST_API_KEY, and does
                                              nothing without them. ONESIGNAL_SEGMENT picks who gets
                                              it (default "All": everyone subscribed)
"""
import hashlib, json, os, pathlib, sys, time, urllib.error, urllib.request, uuid

ROOT = pathlib.Path(__file__).resolve().parent.parent
SITE_URL = 'https://reddotkopi.github.io/heng-ong-huat/'
API = 'https://api.onesignal.com/notifications'
NO_SUBSCRIBERS = 'All included players are not subscribed'
KEEP = 10  # recent draws compared between snapshots


def published(first=None):
    """{draw: {'date', 'top', 'confirmed'}} for the newest archive draws (from `first`, if that is
    earlier, so a snapshot's provisional draws are all compared) plus provisional ones."""
    sys.path.insert(0, str(ROOT / 'scripts'))
    from encode_history import read_draws
    archive = read_draws(ROOT / 'data' / 'sp_4d_prizes.csv')
    last = max(archive)
    lo = max(1, min(last - KEEP + 1, first or last))
    out = {k: {'date': archive[k]['date'], 'top': archive[k]['nums'][:3], 'confirmed': True}
           for k in range(lo, last + 1)}
    live = ROOT / 'data' / 'live.json'
    for d in (json.loads(live.read_text())['draws'] if live.exists() else []):
        if d['draw'] > last:
            out[d['draw']] = {'date': d['date'], 'top': d['numbers'][:3], 'confirmed': False}
    return out


def served(url=None, tries=4):
    """The same shape as published(), from the live site's latest.json, including any older draws
    it shows corrected."""
    for i in range(tries):
        try:
            u = (url or os.environ.get('SITE_URL') or SITE_URL).rstrip('/') + f'/latest.json?t={int(time.time())}'
            with urllib.request.urlopen(urllib.request.Request(u, headers={'Cache-Control': 'no-cache'}), timeout=30) as r:
                j = json.loads(r.read())
            break
        except Exception:
            if i == tries - 1:
                raise
            time.sleep(2 ** (i + 1))
    out = {d['draw']: {'date': d['date'], 'top': d['numbers'][:3], 'confirmed': bool(d.get('confirmed', True))} for d in j['draws']}
    for k, v in (j.get('corrected') or {}).items():
        out.setdefault(int(k), {'date': v['date'], 'top': v['top'], 'confirmed': True})
    return out


def changes(before, after):
    msgs = []
    newest = max(before) if before else 0
    for k in sorted(k for k in after if k > newest)[-3:]:
        msgs.append(dict(after[k], kind='new', draw=k))
    fixed = [k for k in sorted(set(before) & set(after)) if before[k]['top'] != after[k]['top']]
    for k in fixed[-3:]:
        msgs.append(dict(after[k], kind='correction', draw=k, was=before[k]['top'], was_confirmed=before[k]['confirmed']))
    return msgs


def message(m):
    top = f"1st {m['top'][0]} · 2nd {m['top'][1]} · 3rd {m['top'][2]}"
    if m['kind'] == 'correction':
        return (f"Correction: 4D Draw {m['draw']}",
                f"{'Confirmed' if m['confirmed'] else 'Corrected'} results: {top}. The results sent earlier were wrong.")
    if m['confirmed']:
        return (f"4D Draw {m['draw']} results", f"{top}. Tap to check your numbers.")
    return (f"4D Draw {m['draw']} results (provisional)",
            f"{top}. Tap to check your numbers, and confirm with Singapore Pools.")


def key_for(m):
    """The same draw and result always gets the same key, so a re-run never sends it twice.
    A UUID with version-4 bits, which is what OneSignal asks for, derived from the content."""
    # A 'new' alert also carries the data's update stamp: re-runs of the same update are not sent
    # twice, but a later update that publishes the draw again (say, after it was missing) is.
    name = f"heng-ong-huat/{m['kind']}/{m['draw']}/{''.join(m['top'])}" + ('/confirmed' if m['confirmed'] else '')
    if m['kind'] == 'new':
        name += '/' + m.get('stamp', '')
    elif m['kind'] == 'correction':  # and what it replaces, so undoing a correction is sent too
        name += '/was/' + ''.join(m.get('was', [])) + ('/confirmed' if m.get('was_confirmed') else '')
    return str(uuid.UUID(bytes=hashlib.sha256(name.encode()).digest()[:16], version=4))


def post(payload, key):
    auth = f'Key {key}' if key.startswith('os_v2_') else f'Basic {key}'  # current keys, legacy keys
    req = urllib.request.Request(API, data=json.dumps(payload).encode(), method='POST',
                                 headers={'Authorization': auth, 'Content-Type': 'application/json'})
    for attempt in range(4):
        wait = 5 * (attempt + 1)
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read() or b'{}')
        except urllib.error.HTTPError as e:
            detail = e.read().decode(errors='replace')[:300]
            if e.code != 429 and e.code < 500 or attempt == 3:
                raise RuntimeError(f'HTTP {e.code}: {detail}') from None
            if (e.headers.get('Retry-After') or '').isdigit():
                wait = min(int(e.headers['Retry-After']), 120)
        except OSError as e:
            if attempt == 3:
                raise RuntimeError(f'could not reach OneSignal: {e}') from None
        time.sleep(wait)  # same idempotency key, so a retry cannot send twice


def send(msgs):
    app_id, key = os.environ.get('ONESIGNAL_APP_ID', ''), os.environ.get('ONESIGNAL_REST_API_KEY', '')
    if not app_id or not key:
        print('result alerts are not set up (no ONESIGNAL_APP_ID or ONESIGNAL_REST_API_KEY); nothing sent')
        return
    site = (os.environ.get('SITE_URL') or SITE_URL).rstrip('/') + '/'
    failed = 0
    for m in msgs:
        heading, body = message(m)
        payload = {
            'app_id': app_id,
            'target_channel': 'push',
            'included_segments': [os.environ.get('ONESIGNAL_SEGMENT') or 'All'],
            'headings': {'en': heading},
            'contents': {'en': body},
            # the app's start address exactly, so tapping the alert brings an open app to the front
            'url': site,
            'chrome_web_icon': site + 'icons/icon-512.png',
            'idempotency_key': key_for(m),
            'web_push_topic': f"draw-{m['draw']}",  # a correction replaces the alert for the same draw
            'ttl': 12 * 3600,
        }
        try:
            res = post(payload, key)
        except RuntimeError as e:
            print(f'::error::alert {heading!r} not sent: {e}')
            failed += 1
            continue
        errors = res.get('errors')
        if res.get('id'):
            print(f"sent {heading!r}: id {res['id']}" + (f' (some recipients skipped: {errors})' if errors else ''))
        elif errors == [NO_SUBSCRIBERS]:
            print(f'{heading!r}: nobody has turned alerts on yet')
        else:
            print(f'::error::alert {heading!r} not sent: {res}')
            failed += 1
    if failed:
        raise SystemExit(1)


def main():
    args = sys.argv[1:]
    if args[:1] == ['--snapshot']:
        try:
            snap = served()
            print(f'live site shows draws up to {max(snap)}')
        except Exception as e:
            print(f'::warning::could not read the live site ({e}); comparing with the repo instead')
            snap = published()
        pathlib.Path(args[1]).write_text(json.dumps(snap))
    elif args[:1] == ['--diff']:
        before = {int(k): v for k, v in json.loads(pathlib.Path(args[1]).read_text()).items()}
        # A draw data/corrections.json changes that the live site does not show corrected yet (it
        # may be older than the snapshot's window) was showing the archive's own result.
        sys.path.insert(0, str(ROOT / 'scripts'))
        from encode_history import read_draws
        fixes = ROOT / 'data' / 'corrections.json'
        if fixes.exists():
            raw = read_draws(ROOT / 'data' / 'sp_4d_prizes.csv', corrections=False)
            for k in map(int, json.loads(fixes.read_text())):
                if k in raw and k not in before:
                    before[k] = {'date': raw[k]['date'], 'top': raw[k]['nums'][:3], 'confirmed': True}
        msgs = changes(before, published(min(before) if before else None))
        updated = ROOT / 'data' / 'updated.txt'
        for m in msgs:
            m['stamp'] = updated.read_text().strip() if updated.exists() else ''
        for m in msgs:
            print(' / '.join(message(m)))
        if msgs and os.environ.get('GITHUB_OUTPUT'):
            with open(os.environ['GITHUB_OUTPUT'], 'a') as f:
                f.write(f'notify={json.dumps(msgs, separators=(",", ":"))}\n')
    elif args[:1] == ['--describe']:
        p = published()
        conf = max(k for k, v in p.items() if v['confirmed'])
        prov = sorted(k for k, v in p.items() if not v['confirmed'])
        print(f'confirmed to draw {conf}' + (f", provisional draw {', '.join(map(str, prov))}" if prov else ''))
    elif args[:1] == ['--send']:
        send(json.loads(os.environ.get('NOTIFY') or '[]'))
    else:
        raise SystemExit(__doc__)


if __name__ == '__main__':
    main()
