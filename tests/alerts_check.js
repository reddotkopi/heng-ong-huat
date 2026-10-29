// Usage: ONESIGNAL_APP_ID=12345678-abcd-4ef0-9abc-1234567890ab python3 scripts/build.py && node tests/alerts_check.js
// Result alerts: the card's states and the opt-in / opt-out flow, with OneSignal's SDK replaced by a stub.
const { chromium, devices } = require('playwright');
const http = require('http'), fs = require('fs'), path = require('path');
const root = path.resolve(__dirname, '..', 'site');
const types = { '.html': 'text/html', '.js': 'text/javascript', '.png': 'image/png', '.json': 'application/json', '.webmanifest': 'application/manifest+json' };
const server = http.createServer((req, res) => {
  let p = decodeURIComponent(new URL(req.url, 'http://x').pathname);
  if (p.endsWith('/')) p += 'index.html';
  const f = path.join(root, p.replace(/^\/heng-ong-huat/, ''));
  if (!fs.existsSync(f)) { res.writeHead(404); res.end(); return; }
  res.writeHead(200, { 'content-type': types[path.extname(f)] || 'application/octet-stream' }); fs.createReadStream(f).pipe(res);
});
const STUB = `window.__os = { optedIn: false, inits: [], calls: [] };
const OneSignal = { init: async (o) => { __os.inits.push(o); }, User: { PushSubscription: {
  optIn: async () => { __os.calls.push('in'); __os.optedIn = true; }, optOut: async () => { __os.calls.push('out'); __os.optedIn = false; } } } };
const q = window.OneSignalDeferred || []; window.OneSignalDeferred = { push: (f) => f(OneSignal) }; q.forEach((f) => f(OneSignal));`;
const NOTIF = (answer) => `(() => { let perm = localStorage.getItem('perm') || 'default'; Object.defineProperty(Notification, 'permission', { get: () => perm }); Notification.requestPermission = () => { perm = '${answer}'; localStorage.setItem('perm', perm); return Promise.resolve(perm); }; })()`;
const fails = []; const check = (ok, m) => { if (!ok) fails.push(m); console.log((ok ? 'PASS ' : 'FAIL ') + m); };
server.listen(0, async () => {
  const url = `http://localhost:${server.address().port}/heng-ong-huat/#history`;
  const b = await chromium.launch();
  let sdkLoads = 0;
  const open = async (opts, init) => {
    const ctx = await b.newContext(opts);
    await ctx.route('https://cdn.onesignal.com/**', (r) => { sdkLoads++; r.fulfill({ contentType: 'text/javascript', body: STUB }); });
    await ctx.route('https://fonts.googleapis.com/**', (r) => r.fulfill({ contentType: 'text/css', body: '' }));
    const p = await ctx.newPage(); const errs = []; p.on('pageerror', (e) => errs.push(e.message));
    if (init) await p.addInitScript(init);
    await p.goto(url); await p.waitForTimeout(800);
    return { ctx, p, errs };
  };
  // 1. Android/desktop Chrome, permission granted on request
  {
    const { ctx, p, errs } = await open({ ...devices['Pixel 7'] }, NOTIF('granted'));
    check(await p.isVisible('#alertsCard'), 'alerts card shown on the website');
    check(sdkLoads === 0, 'OneSignal not loaded before the user opts in');
    check(/Alerts are off/.test(await p.textContent('#alertsState')) && (await p.textContent('#alertsBtn')) === 'Turn on alerts', 'starts off with a Turn on button');
    await p.click('#alertsBtn'); await p.waitForTimeout(400);
    const st = await p.evaluate(() => ({ os: window.__os, stored: localStorage.getItem('hoh:alerts') }));
    check(sdkLoads === 1 && st.os && st.os.optedIn && st.stored === 'true', 'tap: SDK loaded, subscribed, remembered');
    const init = st.os.inits[0] || {};
    check(init.appId === '12345678-abcd-4ef0-9abc-1234567890ab' && init.serviceWorkerPath === 'heng-ong-huat/push/OneSignalSDKWorker.js' && init.serviceWorkerParam.scope === '/heng-ong-huat/push/', `init options ${JSON.stringify(init)}`);
    check(/Alerts are on/.test(await p.textContent('#alertsState')) && (await p.textContent('#alertsBtn')) === 'Turn off alerts', 'shows on, with Turn off');
    await p.locator('#alertsCard').screenshot({ path: path.join(__dirname, 'shots', 'alerts-on.png') });
    // reload: still on, SDK loads to keep the subscription in step
    sdkLoads = 0; await p.reload(); await p.waitForTimeout(800);
    check(sdkLoads === 1 && /Alerts are on/.test(await p.textContent('#alertsState')), 'after reload: still on, SDK reloaded');
    await p.click('#alertsBtn'); await p.waitForTimeout(400);
    check(await p.evaluate(() => window.__os.calls.join(',')) === 'out' && await p.evaluate(() => localStorage.getItem('hoh:alerts')) === 'false', 'turn off: unsubscribed and remembered');
    sdkLoads = 0; await p.reload(); await p.waitForTimeout(800);
    check(sdkLoads === 0, 'after turning off, OneSignal is not loaded again');
    check(!(await fetch(`http://localhost:${server.address().port}/heng-ong-huat/push/OneSignalSDKWorker.js`).then((r) => r.text())).indexOf('importScripts'), 'OneSignal worker file published under push/');
    check(errs.length === 0, 'no page errors ' + errs.join('|'));
    await ctx.close();
  }
  // 2. Permission refused at the prompt
  {
    const { ctx, p, errs } = await open({ ...devices['Pixel 7'] }, NOTIF('denied'));
    sdkLoads = 0;
    await p.click('#alertsBtn'); await p.waitForTimeout(300);
    check(sdkLoads === 0 && /blocked/.test(await p.textContent('#alertsState')) && await p.isHidden('#alertsActions'), 'refused: nothing loaded, explains how to allow');
    check(errs.length === 0, 'no page errors ' + errs.join('|'));
    await ctx.close();
  }
  // 3. iPhone Safari tab (no PushManager outside the home-screen app)
  {
    const { ctx, p, errs } = await open({ ...devices['iPhone 13'] }, () => { delete window.PushManager; delete window.Notification; });
    const t = await p.textContent('#alertsState');
    check(/Add to Home Screen/.test(t) && await p.isHidden('#alertsActions'), 'iPhone in Safari: told to add to home screen');
    await p.locator('#alertsCard').screenshot({ path: path.join(__dirname, 'shots', 'alerts-ios-tab.png') });
    check(errs.length === 0, 'no page errors ' + errs.join('|'));
    await ctx.close();
  }
  // 4. SDK fails to load (offline / blocked)
  {
    const ctx = await b.newContext({ ...devices['Pixel 7'] });
    await ctx.addInitScript(NOTIF('granted'));
    await ctx.route('https://cdn.onesignal.com/**', (r) => r.abort());
    await ctx.route('https://fonts.googleapis.com/**', (r) => r.fulfill({ contentType: 'text/css', body: '' }));
    const p = await ctx.newPage(); const errs = []; p.on('pageerror', (e) => errs.push(e.message));
    await p.goto(url); await p.waitForTimeout(800);
    await p.click('#alertsBtn'); await p.waitForTimeout(800);
    check(/Could not turn alerts on/.test(await p.textContent('#alertsState')) && await p.isEnabled('#alertsBtn') && await p.evaluate(() => localStorage.getItem('hoh:alerts')) === null, 'SDK unreachable: says so, can retry, not marked on');
    check(errs.length === 0, 'no page errors ' + errs.join('|'));
    await ctx.close();
  }
  await b.close(); server.close();
  console.log(fails.length ? `\n${fails.length} FAILED` : '\nALL PASSED'); process.exit(fails.length ? 1 : 0);
});
