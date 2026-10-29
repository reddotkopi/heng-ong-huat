"""Build Heng Ong Huat from src/heng-ong-huat.html and data/sp_4d_prizes.csv.

  site/                the installable web app for GitHub Pages: index.html (with the full draw
                       history embedded), manifest.webmanifest, sw.js (offline cache), icons/
  dist/artifact.html   the page body for the claude.ai artifact viewer (no document skeleton,
                       no service worker, since that viewer adds its own skeleton)
"""
import hashlib, json, pathlib, shutil, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'scripts'))
from encode_history import encode  # noqa: E402

DESCRIPTION = ('Ask your ancestors or a deity for a 4D number: write and fold ten slips, pray, throw the '
               'moon blocks, then see the number in every Singapore Pools draw since 1986.')


def main():
    src = (ROOT / 'src' / 'heng-ong-huat.html').read_text()
    data, meta = encode(ROOT / 'data' / 'sp_4d_prizes.csv')
    if src.count('__HISTORY_DATA__') != 1:
        raise SystemExit('src must contain __HISTORY_DATA__ exactly once')
    body = src.replace('__HISTORY_DATA__', data)

    dist = ROOT / 'dist'
    dist.mkdir(exist_ok=True)
    (dist / 'artifact.html').write_text(body)

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
    print(f"built site/ (draws 1-{meta['draws']}, latest {meta['last_date']}, cache {version}) and dist/artifact.html")


if __name__ == '__main__':
    main()
