// PWA checks: serves site/ on localhost, then verifies Chrome sees an installable app,
// the service worker takes control, and the app reloads and runs with the network off.
// Usage: node tests/pwa.js
const { chromium, devices } = require('playwright');
const http = require('http'), fs = require('fs'), path = require('path');
const root = path.resolve(__dirname, '..', 'site');
const types = { '.html': 'text/html', '.js': 'text/javascript', '.png': 'image/png', '.webmanifest': 'application/manifest+json' };
const server = http.createServer((req, res) => {
  let p = decodeURIComponent(new URL(req.url, 'http://x').pathname);
  if (p.endsWith('/')) p += 'index.html';
  const f = path.join(root, p);
  if (!f.startsWith(root) || !fs.existsSync(f)) { res.writeHead(404); res.end(); return; }
  res.writeHead(200, { 'content-type': types[path.extname(f)] || 'application/octet-stream' }); fs.createReadStream(f).pipe(res);
});
const fails = [];
const check = (ok, msg) => { if (!ok) fails.push(msg); console.log((ok ? 'PASS ' : 'FAIL ') + msg); };
server.listen(0, async () => {
  const url = `http://localhost:${server.address().port}/`;
  const b = await chromium.launch();
  const ctx = await b.newContext({ ...devices['Pixel 7'] });
  const p = await ctx.newPage();
  const errs = []; p.on('pageerror', (e) => errs.push(e.message));
  await p.goto(url); await p.waitForTimeout(1500);
  const cdp = await ctx.newCDPSession(p);
  const man = await cdp.send('Page.getAppManifest');
  check(man.errors.length === 0 && /Heng Ong Huat/.test(man.data || ''), `manifest parses (${man.errors.map((e) => e.message).join('; ') || 'no errors'})`);
  const inst = await cdp.send('Page.getInstallabilityErrors');
  check(inst.installabilityErrors.length === 0, `installable (${inst.installabilityErrors.map((e) => e.errorId).join(', ') || 'no errors'})`);
  await p.waitForFunction(() => navigator.serviceWorker && navigator.serviceWorker.controller, null, { timeout: 10000 }).catch(() => {});
  if (!(await p.evaluate(() => !!navigator.serviceWorker.controller))) { await p.reload(); await p.waitForTimeout(1500); }
  check(await p.evaluate(() => !!navigator.serviceWorker.controller), 'service worker controls the page');
  await ctx.setOffline(true);
  await p.reload(); await p.waitForTimeout(1200);
  check(await p.evaluate(() => !!window.__HOH && window.__HOH.H.n > 5000), 'reloads offline with the full draw history');
  await p.check('#age18'); await p.click('[data-act="begin"]');
  await p.waitForFunction(() => ['prepare', 'pray'].includes(window.__HOH.R.state), null, { timeout: 5000 }).catch(() => {});
  if (await p.$('[data-act="skip-prep"]')) await p.click('[data-act="skip-prep"]');
  await p.waitForFunction(() => window.__HOH.R.state === 'pray', null, { timeout: 8000 }).catch(() => {});
  check(await p.evaluate(() => window.__HOH.R.state) === 'pray', 'ritual starts offline');
  check(errs.length === 0, 'no page errors: ' + errs.join(' | '));
  await b.close(); server.close();
  console.log(fails.length ? `\n${fails.length} FAILED` : '\nALL PASSED');
  process.exit(fails.length ? 1 : 0);
});
