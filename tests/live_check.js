// Usage: python3 scripts/build.py && node tests/live_check.js
// Same-evening results: serve a copy of site/ with a provisional draw in latest.json, then check
// the app picks it up, labels it, tells a journal holder they won, and accepts the confirmed version.
const { chromium, devices } = require('playwright');
const http = require('http'), fs = require('fs'), path = require('path');
const root = path.resolve(__dirname, '..', 'site');
let latest = JSON.parse(fs.readFileSync(path.join(root, 'latest.json'), 'utf8'));
const original = latest;
const nums = ['1234', '5678', '9012', '0767', '1111', '2222', '3333', '4444', '5555', '6666', '7777', '8888', '9999', '0001', '0002', '0003', '0004', '0005', '0006', '0007', '0008', '0009', '7307'];
const prov = { draw: 5555, date: '2026/10/31', numbers: nums, confirmed: false };
const types = { '.html': 'text/html', '.js': 'text/javascript', '.png': 'image/png', '.json': 'application/json', '.webmanifest': 'application/manifest+json' };
let embedded = null; // when set, the page is served with this as its embedded results (as a later build would be)
const server = http.createServer((req, res) => {
  let p = decodeURIComponent(new URL(req.url, 'http://x').pathname);
  if (p.endsWith('/')) p += 'index.html';
  if (p === '/latest.json') { res.writeHead(200, { 'content-type': 'application/json' }); res.end(JSON.stringify(latest)); return; }
  if (p === '/index.html' && embedded) {
    const html = fs.readFileSync(path.join(root, 'index.html'), 'utf8').replace(/(<script id="live-data" type="application\/json">)[^<]*(<\/script>)/, (m, a, z) => a + JSON.stringify(embedded) + z);
    res.writeHead(200, { 'content-type': 'text/html' }); res.end(html); return;
  }
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
  const st = await p.evaluate(() => ({ n: window.__HOH.H.n, conf: window.__HOH.H.n - window.__HOH.H.prov.size, toast: document.querySelector('#toast').textContent, next: document.querySelector('#nextDraw').textContent }));
  check(st.n === 5555 && st.conf === 5554, `provisional draw appended (n ${st.n}, confirmed ${st.conf})`);
  check(/Your number 7307 came up: Consolation in Draw 5555 \(provisional\)/.test(st.toast), `journal holder told their number came up: "${st.toast}"`);
  check(/provisional/.test(st.next), `header says provisional: "${st.next}"`);
  await p.click('.rail a[data-view="history"]'); await p.waitForTimeout(200);
  check(/Provisional/.test(await p.textContent('#drawBody')), 'draw card shows the Provisional badge');
  await p.screenshot({ path: path.join(__dirname, 'shots', 'live-provisional.png') });
  await p.click('.rail a[data-view="journal"]'); await p.waitForTimeout(200);
  check(/drawn since: Consolation, 31 Oct 2026 \(provisional\)/.test(await p.textContent('#journalList')), 'journal shows the number drawn since it was received, marked provisional');
  // the archive confirms draw 5555 with a different consolation list: confirmed replaces provisional,
  // and the journal holder is told their number is not among the results after all
  const conf = { ...prov, numbers: [...nums.slice(0, 22), '7308'], confirmed: true };
  await p.evaluate(() => { document.querySelector('#toast').textContent = ''; });
  await p.evaluate((d) => window.__HOH.applyLive([d], true), conf);
  const t3 = await p.textContent('#toast');
  check(/Draw 5555 results were corrected: your number 7307 is not among them after all/.test(t3), `correction tells the journal holder: "${t3}"`);
  const st2 = await p.evaluate(() => ({ n: window.__HOH.H.n, conf: window.__HOH.H.n - window.__HOH.H.prov.size, has: window.__HOH.numberStats('7307').occ.length, has2: window.__HOH.numberStats('7308').occ.length }));
  check(st2.n === 5555 && st2.conf === 5555, `confirmed draw replaces provisional (confirmed ${st2.conf})`);
  check(st2.has2 > 0, 'confirmed numbers used after replacement');
  // bad data is ignored
  const before = await p.evaluate(() => window.__HOH.H.n);
  await p.evaluate(() => window.__HOH.applyLive([{ draw: 5556, date: '2026/11/01', numbers: ['12'], confirmed: false }, { draw: 5558, date: '2026/11/04', numbers: Array(23).fill('0000') }], true));
  check(await p.evaluate(() => window.__HOH.H.n) === before, 'malformed or gapped draws ignored');
  check(errs.length === 0, 'no page errors: ' + errs.join(' | '));
  // a provisional draw that disappears from latest.json has been withdrawn (sources disagree)
  {
    const p3 = await ctx.newPage();
    // a fresh phone's record (in this context draw 5555 was already confirmed above)
    await p3.addInitScript(() => { localStorage.removeItem('hoh:provDone'); localStorage.removeItem('hoh:provShown'); });
    latest = { ...original, updated: '2026-10-31T11:00:00Z', draws: [...original.draws, prov] };
    await p3.goto(url); await p3.waitForTimeout(1000);
    check(await p3.evaluate(() => window.__HOH.H.n) === 5555, 'provisional 5555 shown');
    await p3.evaluate(() => { document.querySelector('#toast').textContent = ''; });
    latest = { ...original, updated: '2026-10-31T12:00:00Z' };
    await p3.evaluate(() => window.__HOH.fetchLive());
    await p3.waitForTimeout(300);
    const tw = await p3.textContent('#toast');
    check(await p3.evaluate(() => window.__HOH.H.n) === 5554 && /Draw 5555 results were taken down/.test(tw), `withdrawn draw removed and announced: "${tw}"`);
    // an older copy (say, the offline cache's) does not bring it back
    latest = { ...original, updated: '2026-10-31T11:00:00Z', draws: [...original.draws, prov] };
    await p3.evaluate(() => window.__HOH.fetchLive());
    await p3.waitForTimeout(300);
    check(await p3.evaluate(() => window.__HOH.H.n) === 5554, 'an older latest.json is ignored');
    await p3.close();
  }
  // reopening after results came in (already in the page): told once, then not again
  latest = original; // the site as built: nothing newer to fetch
  const p2 = await ctx.newPage();
  await p2.addInitScript(() => { if (!sessionStorage.getItem('x')) { localStorage.setItem('hoh:seenDraw', '5552'); sessionStorage.setItem('x', '1'); } });
  await p2.goto(url); await p2.waitForTimeout(800);
  const t1 = await p2.textContent('#toast');
  check(/Draw 5554 results are in/.test(t1), `results since the last visit announced on open: "${t1}"`);
  check(await p2.evaluate(() => localStorage.getItem('hoh:seenDraw')) === '5554', 'last seen draw recorded');
  await p2.evaluate(() => { document.querySelector('#toast').textContent = ''; });
  await p2.reload(); await p2.waitForTimeout(800);
  check(!/results are in/.test(await p2.textContent('#toast')), 'not announced again on the next open');
  // Across visits, with the page itself carrying the results (as after an evening deploy)
  {
    const journal = JSON.stringify([{ id: 1, number: '7307', deity: 'ancestors', need: 1, at: Date.parse('2026-10-30T02:00:00Z'), log: [] }]);
    const c2 = await b.newContext({ ...devices['iPhone 13'] });
    await c2.addInitScript((j) => { if (!localStorage.getItem('hoh:journal')) { localStorage.setItem('hoh:journal', j); localStorage.setItem('hoh:seenDraw', '5554'); } }, journal);
    const withProv = { ...original, updated: '2026-10-31T11:00:00Z', draws: [...original.draws, prov] };
    embedded = withProv; latest = withProv;
    const q = await c2.newPage(); await q.goto(url); await q.waitForTimeout(900);
    const a = await q.textContent('#toast');
    check(/Your number 7307 came up: Consolation in Draw 5555 \(provisional\)/.test(a), `opening a page that already has the new draw tells the journal holder: "${a}"`);
    // withdrawn, then back with different numbers: the holder is told it no longer stands
    latest = { ...original, updated: '2026-10-31T12:00:00Z' };
    await q.evaluate(() => { document.querySelector('#toast').textContent = ''; }); await q.evaluate(() => window.__HOH.fetchLive()); await q.waitForTimeout(300);
    check(/Draw 5555 results were taken down/.test(await q.textContent('#toast')), 'withdrawal told');
    latest = { ...original, updated: '2026-11-01T05:00:00Z', draws: [...original.draws, { ...prov, numbers: [...nums.slice(0, 22), '7308'], confirmed: true }] };
    await q.evaluate(() => { document.querySelector('#toast').textContent = ''; }); await q.evaluate(() => window.__HOH.fetchLive()); await q.waitForTimeout(300);
    const r = await q.textContent('#toast');
    check(/Draw 5555 results were corrected: your number 7307 is not among them after all/.test(r), `a withdrawn draw coming back different is told: "${r}"`);
    await q.close();
    // withdrawn while the app is closed, back (same numbers) by the next open: told on open
    const c3 = await b.newContext({ ...devices['iPhone 13'] });
    await c3.addInitScript((j) => { if (!localStorage.getItem('hoh:journal')) { localStorage.setItem('hoh:journal', j); localStorage.setItem('hoh:seenDraw', '5554'); } }, journal);
    embedded = withProv; latest = withProv;
    const r1 = await c3.newPage(); await r1.goto(url); await r1.waitForTimeout(800);
    embedded = { ...original, updated: '2026-10-31T12:00:00Z' }; latest = embedded;
    await r1.reload(); await r1.waitForTimeout(800);
    check(/Draw 5555 results were taken down/.test(await r1.textContent('#toast')), 'a withdrawal while closed is told on the next open');
    embedded = { ...withProv, updated: '2026-10-31T13:00:00Z' }; latest = embedded;
    await r1.evaluate(() => { document.querySelector('#toast').textContent = ''; });
    await r1.reload(); await r1.waitForTimeout(800);
    const r2 = await r1.textContent('#toast');
    check(/Your number 7307 came up: Consolation in Draw 5555/.test(r2), `a draw that comes back while closed is told on open: "${r2}"`);
    await c3.close();
    // a weeks-old page whose provisional draw the current list no longer reaches: kept, nothing said
    const c4 = await b.newContext({ ...devices['iPhone 13'] });
    await c4.addInitScript(() => { if (!localStorage.getItem('hoh:seenDraw')) localStorage.setItem('hoh:seenDraw', '5555'); });
    embedded = withProv;
    const later = Array.from({ length: 6 }, (_, i) => ({ draw: 5558 + i, date: `2026/11/${String(4 + i * 2).padStart(2, '0')}`, numbers: nums.map((x, k) => String((Number(x) + i + k) % 10000).padStart(4, '0')), confirmed: true }));
    latest = { updated: '2026-11-15T05:00:00Z', last_confirmed: 5563, draws: later };
    const o = await c4.newPage(); await o.goto(url); await o.waitForTimeout(1000);
    const ot = await o.textContent('#toast');
    check(await o.evaluate(() => window.__HOH.H.n) === 5555 && !/taken down/.test(ot), `an old page is not told its draw was taken down ("${ot}")`);
    // a list that starts right after the old page's provisional draw: the later draws are confirmed
    latest = { updated: '2026-11-15T05:00:00Z', last_confirmed: 5561, draws: later.map((d, i) => ({ ...d, draw: 5556 + i })) };
    const o2 = await c4.newPage(); await o2.goto(url); await o2.waitForTimeout(1000);
    check(await o2.evaluate(() => window.__HOH.H.n) === 5561 && await o2.evaluate(() => window.__HOH.H.prov.size) === 1, 'only the stale draw is labelled provisional, not the confirmed ones after it');
    await c4.close(); await c2.close();
    // after a correction, an older cached page (with the provisional result) does not repeat it
    const c5 = await b.newContext({ ...devices['iPhone 13'] });
    await c5.addInitScript((j) => { if (!localStorage.getItem('hoh:journal')) { localStorage.setItem('hoh:journal', j); localStorage.setItem('hoh:seenDraw', '5554'); } }, journal);
    embedded = withProv; latest = withProv;
    const s1 = await c5.newPage(); await s1.goto(url); await s1.waitForTimeout(800);
    latest = { ...original, updated: '2026-11-01T05:00:00Z', draws: [...original.draws, { ...prov, numbers: [...nums.slice(0, 22), '7308'], confirmed: true }] };
    await s1.evaluate(() => window.__HOH.fetchLive()); await s1.waitForTimeout(300);
    check(/your number 7307 is not among them after all/.test(await s1.textContent('#toast')), 'correction told once');
    await s1.evaluate(() => { document.querySelector('#toast').textContent = ''; });
    await s1.reload(); await s1.waitForTimeout(900); // the page still embeds the provisional result
    const s2 = await s1.textContent('#toast');
    check(!/corrected|came up/.test(s2), `an older cached page does not repeat it ("${s2}")`);
    await c5.close();
    embedded = null; latest = original;
  }
  await b.close(); server.close();
  console.log(fails.length ? `\n${fails.length} FAILED` : '\nALL PASSED'); process.exit(fails.length ? 1 : 0);
});
