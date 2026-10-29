"""Result alerts: tell people who turned them on when new 4D results are published.

The update job notes what is published before refreshing the data, compares afterwards, and
sends one web push through OneSignal for each change worth knowing about:
  - a new draw (the newest one, when several arrive together), provisional or confirmed
  - a correction, when the confirmed archive differs from the provisional 1st, 2nd or 3rd prize

  python3 scripts/notify.py --snapshot FILE   save the top three prizes of the published draws
  python3 scripts/notify.py --diff FILE       compare with FILE; writes notify=<json> to $GITHUB_OUTPUT
  python3 scripts/notify.py --describe        one line about the published results, for commit messages
  python3 scripts/notify.py --send            send $NOTIFY (from --diff) to subscribers; needs
                                              ONESIGNAL_APP_ID and ONESIGNAL_REST_API_KEY, and does
                                              nothing without them
"""
import json, os, pathlib, sys, time, urllib.error, urllib.request, uuid

ROOT = pathlib.Path(__file__).resolve().parent.parent
SITE_URL = 'https://reddotkopi.github.io/heng-ong-huat/'
API = 'https://api.onesignal.com/notifications?c=push'
KEEP = 10  # recent draws compared between snapshots


def published():
    """{draw: {'date', 'top', 'confirmed'}} for the newest archive draws plus provisional ones."""
    sys.path.insert(0, str(ROOT / 'scripts'))
    from encode_history import read_draws
    archive = read_draws(ROOT / 'data' / 'sp_4d_prizes.csv')
    last = max(archive)
    out = {k: {'date': archive[k]['date'], 'top': archive[k]['nums'][:3], 'confirmed': True}
           for k in range(max(1, last - KEEP + 1), last + 1)}
    live = ROOT / 'data' / 'live.json'
    for d in (json.loads(live.read_text())['draws'] if live.exists() else []):
        if d['draw'] > last:
            out[d['draw']] = {'date': d['date'], 'top': d['numbers'][:3], 'confirmed': False}
    return out


def changes(before, after):
    msgs = []
    newest = max(before) if before else 0
    added = sorted(k for k in after if k > newest)
    if added:
        k = added[-1]
        msgs.append(dict(after[k], kind='new', draw=k, count=len(added)))
    for k in sorted(set(before) & set(after)):
        if not before[k]['confirmed'] and after[k]['confirmed'] and before[k]['top'] != after[k]['top']:
            msgs.append(dict(after[k], kind='correction', draw=k, was=before[k]['top']))
    return msgs


def message(m):
    top = f"1st {m['top'][0]} · 2nd {m['top'][1]} · 3rd {m['top'][2]}"
    if m['kind'] == 'correction':
        return (f"Correction: 4D Draw {m['draw']}",
                f"Confirmed results: {top}. The provisional ones sent earlier were wrong.")
    if m['confirmed']:
        return (f"4D Draw {m['draw']} results", f"{top}. Tap to check your numbers.")
    return (f"4D Draw {m['draw']} results (provisional)",
            f"{top}. Tap to check your numbers, and confirm with Singapore Pools.")


def send(msgs):
    app_id, key = os.environ.get('ONESIGNAL_APP_ID', ''), os.environ.get('ONESIGNAL_REST_API_KEY', '')
    if not app_id or not key:
        print('result alerts are not set up (no ONESIGNAL_APP_ID or ONESIGNAL_REST_API_KEY); nothing sent')
        return
    url = (os.environ.get('SITE_URL') or SITE_URL).rstrip('/') + '/#history'
    failed = 0
    for m in msgs:
        heading, body = message(m)
        payload = {
            'app_id': app_id,
            'target_channel': 'push',
            'included_segments': ['Total Subscriptions'],
            'headings': {'en': heading},
            'contents': {'en': body},
            'url': url,
            # the same draw and result is only ever sent once, even if this job is re-run
            'idempotency_key': str(uuid.uuid5(uuid.NAMESPACE_URL, f"heng-ong-huat/{m['kind']}/{m['draw']}/{''.join(m['top'])}")),
            # a correction replaces the alert for the same draw on the phone
            'web_push_topic': f"draw-{m['draw']}",
            'ttl': 12 * 3600,
        }
        auth = f'Key {key}' if key.startswith('os_v2_') else f'Basic {key}'
        req = urllib.request.Request(API, data=json.dumps(payload).encode(), method='POST',
                                     headers={'Authorization': auth, 'Content-Type': 'application/json'})
        for attempt in range(3):
            try:
                with urllib.request.urlopen(req, timeout=30) as r:
                    res = json.loads(r.read() or b'{}')
                print(f"sent {heading!r}: id {res.get('id') or '(none: no subscribers yet)'}")
                if res.get('errors'):
                    print(f"::warning::OneSignal reported: {res['errors']}")
                break
            except urllib.error.HTTPError as e:
                detail = e.read().decode(errors='replace')[:300]
                if e.code < 500 or attempt == 2:
                    print(f'::error::OneSignal refused {heading!r} (HTTP {e.code}): {detail}')
                    failed += 1
                    break
            except OSError as e:
                if attempt == 2:
                    print(f'::error::could not reach OneSignal for {heading!r}: {e}')
                    failed += 1
            time.sleep(5 * (attempt + 1))
    if failed:
        raise SystemExit(1)


def main():
    args = sys.argv[1:]
    if args[:1] == ['--snapshot']:
        pathlib.Path(args[1]).write_text(json.dumps(published()))
    elif args[:1] == ['--diff']:
        before = {int(k): v for k, v in json.loads(pathlib.Path(args[1]).read_text()).items()}
        msgs = changes(before, published())
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
