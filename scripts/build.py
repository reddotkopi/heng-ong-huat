"""Build Heng Ong Huat from src/heng-ong-huat.html and data/sp_4d_prizes.csv.

  site/                the installable web app for GitHub Pages: index.html (with the full draw
                       history embedded), manifest.webmanifest, sw.js (offline cache), icons/
  dist/artifact.html   the page body for the claude.ai artifact viewer (no document skeleton,
                       no service worker, since that viewer adds its own skeleton)
"""
import hashlib, json, os, pathlib, re, shutil, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'scripts'))
from encode_history import encode, read_draws  # noqa: E402

RECENT = 10  # archive draws repeated in latest.json (the same ten the alerts and the app's records cover), so an old or open page can catch up

DESCRIPTION = ('Ask your ancestors or a deity for a 4D number: write and fold ten slips, pray, throw the '
               'moon blocks, then see the number in every Singapore Pools draw since 1986.')


def main():
    src = (ROOT / 'src' / 'heng-ong-huat.html').read_text()
    data, meta = encode(ROOT / 'data' / 'sp_4d_prizes.csv')
    if src.count('__HISTORY_DATA__') != 1:
        raise SystemExit('src must contain __HISTORY_DATA__ exactly once')
    archive = read_draws(ROOT / 'data' / 'sp_4d_prizes.csv')
    live_path = ROOT / 'data' / 'live.json'
    provisional = json.loads(live_path.read_text())['draws'] if live_path.exists() else []
    last = max(archive)
    updated = ROOT / 'data' / 'updated.txt'
    fixes = ROOT / 'data' / 'corrections.json'
    latest = {
        # when the results last changed: the app ignores a copy older than the one it has
        'updated': updated.read_text().strip() if updated.exists() else '',
        # draws data/corrections.json changes, as published (the alert job compares with these)
        'corrected': {k: {'date': archive[int(k)]['date'], 'top': archive[int(k)]['nums'][:3]}
                      for k in (json.loads(fixes.read_text()) if fixes.exists() else {})},
        'last_confirmed': last,
        'draws': [{'draw': k, 'date': archive[k]['date'], 'numbers': archive[k]['nums'], 'confirmed': True}
                  for k in range(max(1, last - RECENT + 1), last + 1)]
                 + [dict(d, confirmed=False) for d in provisional if d['draw'] > last],
    }
    latest_json = json.dumps(latest, separators=(',', ':'))
    if src.count('__LIVE_DATA__') != 1:
        raise SystemExit('src must contain __LIVE_DATA__ exactly once')
    # Result alerts: the OneSignal app ID is public (it is in every page that uses it). Set it as
    # the repository variable ONESIGNAL_APP_ID; without it the app has no alerts.
    push_app = os.environ.get('ONESIGNAL_APP_ID', '').strip()
    if push_app and not re.fullmatch(r'[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}', push_app, re.I):
        print(f'::warning::ONESIGNAL_APP_ID {push_app!r} is not an app ID; building without result alerts')
        push_app = ''
    if src.count('__ONESIGNAL_APP_ID__') != 1:
        raise SystemExit('src must contain __ONESIGNAL_APP_ID__ exactly once')
    body = src.replace('__HISTORY_DATA__', data).replace('__LIVE_DATA__', latest_json)
    artifact = body.replace('__ONESIGNAL_APP_ID__', '')
    body = body.replace('__ONESIGNAL_APP_ID__', push_app)

    dist = ROOT / 'dist'
    dist.mkdir(exist_ok=True)
    (dist / 'artifact.html').write_text(artifact)

    site = ROOT / 'site'
    if site.exists():
        shutil.rmtree(site)
    (site / 'icons').mkdir(parents=True)
    for icon in (ROOT / 'assets' / 'icons').glob('*.png'):
        shutil.copy(icon, site / 'icons' / icon.name)

    head_end = body.index('</style>') + len('</style>')  # the source starts with <title>, metas, fonts and <style>
    head = f'''<!doctype html>
<html lang="en-SG">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="description" content="{DESCRIPTION}">
<meta name="theme-color" content="#1b0f0b">
<meta name="mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<meta name="apple-mobile-web-app-title" content="Heng Ong Huat">
<link rel="manifest" href="manifest.webmanifest">
<link rel="icon" type="image/png" sizes="32x32" href="icons/favicon-32.png">
<link rel="apple-touch-icon" href="icons/apple-touch-icon.png">
<style>:root{{padding-top:env(safe-area-inset-top,0px);padding-bottom:env(safe-area-inset-bottom,0px)}}body{{margin:0}}img{{max-width:100%}}[hidden]{{display:none!important}}</style>
'''
    register = '''<script>
if ('serviceWorker' in navigator && window.self === window.top && (location.protocol === 'https:' || location.hostname === 'localhost')) {
  addEventListener('load', () => navigator.serviceWorker.register('sw.js').catch(() => {}));
}
</script>
'''
    page = head + body[:head_end] + '\n</head>\n<body>\n' + body[head_end:] + '\n' + register + '</body>\n</html>\n'
    (site / 'index.html').write_text(page)

    version = hashlib.sha256(page.encode()).hexdigest()[:12]
    (site / 'sw.js').write_text((ROOT / 'pwa' / 'sw.js').read_text().replace('__VERSION__', version))
    manifest = {
        'name': 'Heng Ong Huat 兴旺发',
        'short_name': 'Heng Ong Huat',
        'description': DESCRIPTION,
        'id': './',
        'start_url': './',
        'scope': './',
        'display': 'standalone',
        'orientation': 'portrait',
        'background_color': '#1b0f0b',
        'theme_color': '#1b0f0b',
        'lang': 'en-SG',
        'categories': ['lifestyle', 'entertainment'],
        'icons': [
            {'src': 'icons/icon-192.png', 'sizes': '192x192', 'type': 'image/png', 'purpose': 'any'},
            {'src': 'icons/icon-512.png', 'sizes': '512x512', 'type': 'image/png', 'purpose': 'any'},
            {'src': 'icons/maskable-512.png', 'sizes': '512x512', 'type': 'image/png', 'purpose': 'maskable'},
        ],
    }
    (site / 'manifest.webmanifest').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
    (site / '.nojekyll').write_text('')
    (site / 'latest.json').write_text(latest_json + '\n')
    if push_app:  # OneSignal's service worker, kept in its own scope apart from sw.js
        (site / 'push').mkdir()
        (site / 'push' / 'OneSignalSDKWorker.js').write_text('importScripts("https://cdn.onesignal.com/sdks/web/v16/OneSignalSDK.sw.js");\n')
    # A fingerprint of everything published; the deploy job compares it with the live site's.
    digest = hashlib.sha256()
    for f in sorted(x for x in site.rglob('*') if x.is_file()):
        digest.update(f.relative_to(site).as_posix().encode() + b'\0' + f.read_bytes() + b'\0')
    (site / 'version.txt').write_text(digest.hexdigest()[:16] + '\n')
    print(f"built site/ (draws 1-{meta['draws']}, latest {meta['last_date']}, {sum(not d['confirmed'] for d in latest['draws'])} provisional, alerts {'on' if push_app else 'off'}, cache {version}) and dist/artifact.html")


if __name__ == '__main__':
    main()
