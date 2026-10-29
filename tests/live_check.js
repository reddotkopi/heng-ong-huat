// Usage: python3 scripts/build.py && node tests/live_check.js
// Same-evening results: serve a copy of site/ with a provisional draw in latest.json, then check
// the app picks it up, labels it, tells a journal holder they won, and accepts the confirmed version.
const { chromium, devices } = require('playwright');
const http = require('http'), fs = require('fs'), path = require('path');
const root = path.resolve(__dirname, '..', 'site');
let latest = JSON.parse(fs.readFileSync(path.join(root, 'latest.json'), 'utf8'));
const nums = ['1234', '5678', '9012', '0767', '1111', '2222', '3333', '4444', '5555', '6666', '7777', '8888', '9999', '0001', '0002', '0003', '0004', '0005', '0006', '0007', '0008', '0009', '7307'];
const prov = { draw: 5555, date: '2026/10/31', numbers: nums, confirmed: false };
const types = { '.html': 'text/html', '.js': 'text/javascript', '.png': 'image/png', '.json': 'application/json', '.webmanifest': 'application/manifest+json' };
const server = http.createServer((req, res) => {
  let p = decodeURIComponent(new URL(req.url, 'http://x').pathname);
  if (p.endsWith('/')) p += 'index.html';
  if (p === '/latest.json') { res.writeHead(200, { 'content-type': 'application/json' }); res.end(JSON.stringify(latest)); return; }
  const f = path.join(root, p);
  if (!fs.existsSync(f)) { res.writeHead(404); res.end(); return; }
  res.writeHead(200, { 'content-type': types[path.extname(f)] || 'application/octet-stream' }); fs.createReadStream(f).pipe(res);
});
const fails = []; const check = (ok, m) => { if (!ok) fails.push(m); console.log((ok ? 'PASS ' : 'FAIL ') + m); };
server.listen(0, async () => {
  const url = `http://localhost:${server.address().port}/`;
  const b = await chromium.launch(); const ctx = await b.newContext({ ...devices['iPhone 13'] }); const p = await ctx.newPage();
  const errs = []; p.on('pageerror', (e) => errs.push(e.message));
  await p.addInitScript(() => localStorage.setItem('hoh:journal', JSON.stringify([{ id: 2, number: '1234', deity: 'tpk', need: 1, at: Date.parse('2026-10-31T11:00:00Z'), log: [] }, { id: 1, number: '7307', deity: 'ancestors', need: 1, at: Date.parse('2026-10-30T02:00:00Z'), log: [] }])));
  await p.goto(url); await p.waitForTimeout(1200);
  check(await p.evaluate(() => window.__HOH.H.n) === 5554, 'no provisional draws at first');
  latest = { ...latest, draws: [...latest.draws, prov] };
  await p.evaluate(() => { Object.defineProperty(document, 'hidden', { configurable: true, get: () => false }); document.dispatchEvent(new Event('visibilitychange')); });
  await p.evaluate(() => window.__HOH.applyLive && null);
  // force a fetch (the visibility handler waits 10 minutes between fetches outside draw evenings)
  await p.evaluate(async () => { const r = await fetch('latest.json?t=' + Date.now()); window.__HOH.applyLive((await r.json()).draws, true); });
  await p.waitForTimeout(400);
  const st = await p.evaluate(() => ({ n: window.__HOH.H.n, conf: window.__HOH.H.confirmed, toast: document.querySelector('#toast').textContent, next: document.querySelector('#nextDraw').textContent }));
  check(st.n === 5555 && st.conf === 5554, `provisional draw appended (n ${st.n}, confirmed ${st.conf})`);
  check(/Your number 7307 came up: Consolation in Draw 5555 \(provisional\)/.test(st.toast), `journal holder told their number came up: "${st.toast}"`);
  check(/provisional/.test(st.next), `header says provisional: "${st.next}"`);
  await p.click('.rail a[data-view="history"]'); await p.waitForTimeout(200);
  check(/Provisional/.test(await p.textContent('#drawBody')), 'draw card shows the Provisional badge');
  await p.screenshot({ path: path.join(__dirname, 'shots', 'live-provisional.png') });
  await p.click('.rail a[data-view="journal"]'); await p.waitForTimeout(200);
  check(/drawn since: Consolation/.test(await p.textContent('#journalList')), 'journal shows the number drawn since it was received');
  // the archive confirms draw 5555 with a different consolation list: confirmed replaces provisional
  const conf = { ...prov, numbers: [...nums.slice(0, 22), '7308'], confirmed: true };
  await p.evaluate((d) => window.__HOH.applyLive([d], true), conf);
  const st2 = await p.evaluate(() => ({ n: window.__HOH.H.n, conf: window.__HOH.H.confirmed, has: window.__HOH.numberStats('7307').occ.length, has2: window.__HOH.numberStats('7308').occ.length }));
  check(st2.n === 5555 && st2.conf === 5555, `confirmed draw replaces provisional (confirmed ${st2.conf})`);
  check(st2.has2 > 0, 'confirmed numbers used after replacement');
  // bad data is ignored
  const before = await p.evaluate(() => window.__HOH.H.n);
  await p.evaluate(() => window.__HOH.applyLive([{ draw: 5556, date: '2026/11/01', numbers: ['12'], confirmed: false }, { draw: 5558, date: '2026/11/04', numbers: Array(23).fill('0000') }], true));
  check(await p.evaluate(() => window.__HOH.H.n) === before, 'malformed or gapped draws ignored');
  check(errs.length === 0, 'no page errors: ' + errs.join(' | '));
  await b.close(); server.close();
  console.log(fails.length ? `\n${fails.length} FAILED` : '\nALL PASSED'); process.exit(fails.length ? 1 : 0);
});
