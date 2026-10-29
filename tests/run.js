// Functional + visual test of the Heng Ong Huat page.
// Usage: node tests/run.js site/index.html tests/shots
const { chromium, devices } = require('playwright');
const fs = require('fs');
const path = require('path');

const file = path.resolve(process.argv[2]);
const shots = path.resolve(process.argv[3] || 'tests/shots');
const gt = JSON.parse(fs.readFileSync(path.join(__dirname, 'ground_truth.json'), 'utf8'));
const fails = [];
const check = (ok, msg) => { if (!ok) fails.push(msg); console.log((ok ? 'PASS ' : 'FAIL ') + msg); };

(async () => {
  const browser = await chromium.launch();
  const ctx = await browser.newContext({ ...devices['iPhone 13'], reducedMotion: 'no-preference' });
  const page = await ctx.newPage();
  const errors = [];
  page.on('pageerror', (e) => errors.push('pageerror: ' + e.message));
  page.on('console', (m) => { if (m.type() === 'error') errors.push('console: ' + m.text()); });
  await page.goto('file://' + file);
  await page.waitForTimeout(1500);
  await page.screenshot({ path: `${shots}/01-intro.png`, fullPage: true });

  // ---- history engine vs CSV ground truth ----
  const res = await page.evaluate((nums) => nums.map((n) => {
    const st = window.__HOH.numberStats(n);
    const H = window.__HOH.H;
    return { n, total: st.occ.length, tiers: st.byTier, last: st.occ.length ? H.drawOf[st.occ[0]] + 1 : null };
  }), Object.keys(gt));
  for (const r of res) {
    const g = gt[r.n];
    const tiers = Object.fromEntries(Object.entries(r.tiers).filter(([, v]) => v));
    check(r.total === g.total && r.last === g.last && JSON.stringify(Object.keys(tiers).sort().map((k) => [k, tiers[k]])) === JSON.stringify(Object.keys(g.tiers).sort().map((k) => [k, g.tiers[k]])), `history ${r.n}: app ${JSON.stringify(tiers)} last ${r.last} vs csv ${JSON.stringify(g.tiers)} last ${g.last}`);
  }
  const meta = await page.evaluate(() => ({ n: window.__HOH.H.n, total: window.__HOH.H.total }));
  check(meta.n === 5554 && meta.total === 127476, `dataset size ${JSON.stringify(meta)}`);

  // ---- randomness sanity: uniform digits ----
  const dist = await page.evaluate(() => { const c = new Array(10).fill(0); for (let i = 0; i < 200000; i++) c[window.__HOH.rand.int(10)]++; return c; });
  const chi = dist.reduce((a, o) => a + (o - 20000) ** 2 / 20000, 0);
  check(chi < 27.88, `digit chi-square ${chi.toFixed(2)} (df 9, p>0.001 threshold 27.88) ${dist.join(',')}`);

  // ---- touch ritual end to end ----
  check(await page.$eval('[data-act="begin"]', (b) => b.disabled), 'Begin needs the 18+ confirmation');
  await page.check('#age18');
  await page.click('[data-act="begin"]');
  await page.waitForFunction(() => window.__HOH.R.state === 'prepare', null, { timeout: 4000 }).catch(() => {});
  check(await page.evaluate(() => document.querySelectorAll('#stage .sheet.mini').length) === 10, 'prepare shows ten slips');
  await page.waitForTimeout(1800);
  await page.screenshot({ path: `${shots}/01b-writing.png` });
  await page.waitForFunction(() => window.__HOH.R.state === 'pray', null, { timeout: 12000 }).catch(() => {});
  check(await page.evaluate(() => window.__HOH.R.state) === 'pray', 'begin -> pray');
  let shot = 0;
  let guard = 0;
  while (guard++ < 400) {
    const st = await page.evaluate(() => ({ s: window.__HOH.R.state, busy: window.__HOH.R.busy, pos: window.__HOH.R.pos }));
    if (st.s === 'complete') break;
    if (st.busy || st.s === 'throwing') { await page.waitForTimeout(150); continue; }
    if (st.s === 'pray') { await page.click('[data-act="bow"]'); await page.waitForTimeout(700); }
    else if (st.s === 'fallen') { if (shot === 0) { await page.screenshot({ path: `${shots}/02-fallen.png` }); } await page.click('#slip'); await page.waitForTimeout(700); }
    else if (st.s === 'unfolded') { if (shot === 0) { await page.screenshot({ path: `${shots}/03-unfolded.png` }); shot = 1; } await page.click('[data-act="throw"]'); await page.waitForTimeout(1400); }
    else if (st.s === 'landed') {
      if (shot === 1) { await page.screenshot({ path: `${shots}/04-landed.png` }); shot = 2; }
      const btn = await page.$('[data-act="throw"]');
      if (btn) { await btn.click(); await page.waitForTimeout(1400); } else await page.waitForTimeout(400);
    }
    else await page.waitForTimeout(200);
  }
  const fin = await page.evaluate(() => ({ s: window.__HOH.R.state, digits: window.__HOH.R.digits, log: window.__HOH.R.log }));
  check(fin.s === 'complete' && fin.digits.length === 4 && fin.digits.every((d) => d >= 0 && d <= 9), `touch ritual completes: ${fin.digits.join('')}`);
  check(fin.log.every((p, i) => p.length && p[p.length - 1].kept && p[p.length - 1].digit === fin.digits[i] && p[p.length - 1].throws.slice(-1)[0] === 'sheng'), 'ritual log: each kept digit ends on a 圣杯');
  check(fin.log.every((p) => p.every((t, k) => k === p.length - 1 || t.throws.slice(-1)[0] === 'yin')), 'ritual log: rejected slips ended on 阴杯');
  await page.waitForTimeout(600);
  await page.screenshot({ path: `${shots}/05-complete.png`, fullPage: true });

  // journal saved
  const j = await page.evaluate(() => JSON.parse(localStorage.getItem('hoh:journal') || '[]'));
  check(j.length === 1 && j[0].number === fin.digits.join(''), 'journal saved');

  // ---- views ----
  await page.click('.rail a[data-view="history"]');
  await page.fill('#lookupInput', '5150');
  await page.click('#lookupForm button[type="submit"]');
  await page.waitForTimeout(300);
  const lk = await page.textContent('#lookupResult');
  check(/20×/.test(lk) && /5150 won 1st Prize/.test(lk), 'lookup 5150 shows 20 wins and the latest-draw match');
  await page.screenshot({ path: `${shots}/06-history.png`, fullPage: true });
  await page.fill('#memDate', '2025-08-23');
  await page.dispatchEvent('#memDate', 'change');
  const mem = await page.textContent('#memBody');
  check(/Draw 5369/.test(mem) && /2308/.test(mem), 'dates card finds Draw 5369 and offers 2308');
  await page.click('#memBody [data-draw]');
  check(await page.inputValue('#drawNo') === '5369', 'dates card jumps the draw browser');
  await page.fill('#memDate', '2026-12-25');
  await page.dispatchEvent('#memDate', 'change');
  check(/after the latest draw/.test(await page.textContent('#memBody')), 'future date handled');
  const news = await page.$$eval('#newsList li', (l) => l.map((x) => x.textContent));
  check(news.length === 4 && /1st Prize/.test(news[0]) && /2nd Prize/.test(news[1]) && /15 times across all of 2021. That year/.test(news[2]) && /Not drawn/.test(news[3]), 'news card checked against data: ' + news.map((x) => x.replace(/\s+/g, ' ').slice(0, 60)).join(' | '));
  check(/consistent with an even draw/.test(await page.textContent('#heatNote')), 'fairness note');
  await page.click('.rail a[data-view="journal"]');
  await page.screenshot({ path: `${shots}/07-journal.png`, fullPage: true });
  await page.click('.rail a[data-view="about"]');
  await page.screenshot({ path: `${shots}/08-about.png`, fullPage: true });

  // ---- overflow check ----
  for (const v of ['seek', 'history', 'journal', 'about']) {
    await page.click(`.rail a[data-view="${v}"]`);
    const ov = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    check(ov <= 0, `no horizontal overflow on ${v} (${ov}px)`);
  }

  // ---- motion mode with synthetic sensor events ----
  const mctx = await browser.newContext({ ...devices['iPhone 13'] });
  await mctx.grantPermissions(['accelerometer', 'gyroscope']);
  const mpage = await mctx.newPage();
  mpage.on('pageerror', (e) => errors.push('motion pageerror: ' + e.message));
  await mpage.goto('file://' + file + '#seek');
  await mpage.waitForTimeout(800);
  await mpage.evaluate(() => {
    // emulate a phone held flat in the palms: gravity on z, small noise, 60 Hz
    window.__sensor = { gx: 0, gy: 0.4, gz: 9.8, ax: 0, ay: 0, az: 0, rot: 0 };
    setInterval(() => {
      const s = window.__sensor;
      const n = () => (Math.random() - 0.5) * 0.08;
      window.dispatchEvent(new DeviceMotionEvent('devicemotion', {
        accelerationIncludingGravity: { x: s.gx + n(), y: s.gy + n(), z: s.gz + n() },
        acceleration: { x: s.ax + n(), y: s.ay + n(), z: s.az + n() },
        rotationRate: { alpha: s.rot, beta: 0, gamma: 0 }, interval: 16,
      }));
    }, 16);
  });
  await mpage.check('#age18');
  await mpage.click('[data-act="begin"]');
  await mpage.waitForFunction(() => window.__HOH.R.state === 'prepare', null, { timeout: 4000 }).catch(() => {});
  const mode = await mpage.evaluate(() => window.__HOH.R.inputMode);
  check(mode === 'motion', `motion mode detected (${mode})`);
  // no sensor listener while the slips are being written (nothing is listening)
  await mpage.click('[data-act="skip-prep"]');
  await mpage.waitForFunction(() => window.__HOH.R.state === 'pray', null, { timeout: 4000 }).catch(() => {});
  check(await mpage.evaluate(() => document.querySelectorAll('#stage .sheet').length) === 0, 'skip removes the prepare slips');
  // moving the phone while another tab is showing must not advance the ritual
  await mpage.click('.rail a[data-view="history"]');
  for (let k = 0; k < 4; k++) { await mpage.evaluate(() => { window.__sensor.gy = 9.81 * Math.sin(0.5); window.__sensor.gz = 9.81 * Math.cos(0.5); }); await mpage.waitForTimeout(400); await mpage.evaluate(() => { window.__sensor.gy = 0.4; window.__sensor.gz = 9.8; }); await mpage.waitForTimeout(500); }
  check(await mpage.evaluate(() => window.__HOH.R.bows) === 0, 'no bows counted while History is showing');
  await mpage.click('.rail a[data-view="seek"]');
  await mpage.waitForTimeout(600);
  const tilt = async (deg, ms) => {
    const steps = Math.round(ms / 16);
    const from = await mpage.evaluate(() => Math.atan2(window.__sensor.gy, window.__sensor.gz) * 57.2958);
    for (let i = 1; i <= steps; i++) {
      const a = (from + (deg - from) * (i / steps)) / 57.2958;
      await mpage.evaluate((a) => { window.__sensor.gy = 9.81 * Math.sin(a); window.__sensor.gz = 9.81 * Math.cos(a); }, a);
      await mpage.waitForTimeout(16);
    }
  };
  let bows0 = 0;
  for (let b = 0; b < 6; b++) {
    const st = await mpage.evaluate(() => window.__HOH.R.state);
    if (st !== 'pray') break;
    await tilt(30, 350); await tilt(2, 350); await mpage.waitForTimeout(300);
    bows0 = await mpage.evaluate(() => window.__HOH.R.bows);
  }
  const afterBows = await mpage.evaluate(() => ({ s: window.__HOH.R.state, bows: window.__HOH.R.bows }));
  check(['fallen', 'unfolded'].includes(afterBows.s), `tilting bows drop a slip (state ${afterBows.s}, bows ${afterBows.bows})`);
  await mpage.waitForTimeout(2200); // auto-unfold in motion mode
  check(await mpage.evaluate(() => window.__HOH.R.state) === 'unfolded', 'motion mode auto-unfolds');
  // flick: big linear acceleration spike
  await mpage.waitForTimeout(500); // the toss detector arms after the phone is held still
  await mpage.evaluate(() => { window.__sensor.ay = 16; window.__sensor.az = 6; });
  await mpage.waitForTimeout(90);
  await mpage.evaluate(() => { window.__sensor.ay = -9; window.__sensor.az = -3; });
  await mpage.waitForTimeout(70);
  await mpage.evaluate(() => { window.__sensor.ay = 0; window.__sensor.az = 0; });
  await mpage.waitForTimeout(200);
  const ts = await mpage.evaluate(() => window.__HOH.R.state);
  check(['throwing', 'landed', 'pray'].includes(ts), `flick throws the blocks (state ${ts})`);
  // noise must not count as bows
  await mpage.waitForTimeout(3500);
  const quiet = await mpage.evaluate(() => ({ s: window.__HOH.R.state, bows: window.__HOH.R.bows }));
  console.log('after toss', JSON.stringify(quiet));

  check(errors.length === 0, 'no page errors: ' + errors.join(' | '));
  await browser.close();
  console.log(fails.length ? `\n${fails.length} FAILED` : '\nALL PASSED');
  process.exit(fails.length ? 1 : 0);
})();
