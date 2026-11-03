#!/usr/bin/env node
/*
 * Browser checks for the auth screens (Step 12A).
 *   Sample: Google buttons and their dividers hidden as debt (CLIENT-oidc);
 *           the sign-up website field (V5-signup-website-field) and the
 *           product-updates opt-in (V5-signup-marketing-optin) show; with no
 *           AI Core set, the login is the fixture (no request; 12345678 works;
 *           a wrong code says so, and nothing locks: SEC-login-code-lockout).
 *   Live:   with <html data-core-url>, Send login code is one POST
 *           /auth/login-code/request {email}; the code step names the email
 *           and counts down the server's resend window; verify is one POST
 *           /auth/login-code/verify {email, challenge, code} with the
 *           challenge of the latest request: 401 says the code is wrong or
 *           expired and three in a row lock nothing; success connects AI Core
 *           with the returned token and opens the Dashboard; the per-address
 *           cap (429) stays on the login page with its own message; 503 too;
 *           Resend is one more request and its challenge replaces the old one.
 *           Sign-up: one POST /auth/signup/request with the website (null
 *           when empty) and marketing_optin (the opt-in box, false unless
 *           ticked); a website not starting with https:// is refused first.
 *           Persian: static text, live messages and the split "we sent to"
 *           sentence; a sign-up validation message.
 * Runs on file:// with AI Core mocked in the page and every request
 * recorded. Persian expectations are built from code points, so this file
 * stays ASCII and no rendering can reverse them.
 *
 * Usage: node visual-harness/e2e/auth.js
 *   PLAYWRIGHT_CORE, PW_EXE as in knowledge-quickfix.js
 * Exit: 0 all pass, 1 a check failed, 2 the run itself failed.
 */
const path = require('path');
const url = require('url');
const { chromium } = require(process.env.PLAYWRIGHT_CORE || 'playwright-core');

const pageUrl = url.pathToFileURL(path.join(__dirname, '..', 'index.html')).href + '#screen-login';
const fa = (...codes) => String.fromCharCode(...codes);
const EM = fa(0x2014), ELL = fa(0x2026), iso = (s) => fa(0x2068) + s + fa(0x2069);
const FA = {
  welcome: [0x62E, 0x648, 0x634, 0x20, 0x622, 0x645, 0x62F, 0x6CC, 0x62F],
  delivery: [0x627, 0x631, 0x633, 0x627, 0x644, 0x20, 0x627, 0x6CC, 0x645, 0x6CC, 0x644, 0x20, 0x62F, 0x631, 0x20, 0x62F, 0x633, 0x62A, 0x631, 0x633, 0x20, 0x646, 0x6CC, 0x633, 0x62A, 0x61B, 0x20, 0x647, 0x6CC, 0x686, 0x20, 0x6A9, 0x62F, 0x6CC, 0x20, 0x641, 0x631, 0x633, 0x62A, 0x627, 0x62F, 0x647, 0x20, 0x646, 0x634, 0x62F, 0x2E],
  sentTo: [0x6A9, 0x62F, 0x20, 0x6F8, 0x20, 0x631, 0x642, 0x645, 0x6CC, 0x20, 0x641, 0x631, 0x633, 0x62A, 0x627, 0x62F, 0x647, 0x200C, 0x634, 0x62F, 0x647, 0x20, 0x628, 0x647, 0x20, 0x627, 0x6CC, 0x646, 0x20, 0x646, 0x634, 0x627, 0x646, 0x6CC, 0x20, 0x631, 0x627, 0x20, 0x648, 0x627, 0x631, 0x62F, 0x20, 0x6A9, 0x646, 0x6CC, 0x62F, 0x3A],
  wrongCode: [0x627, 0x6CC, 0x646, 0x20, 0x6A9, 0x62F, 0x20, 0x646, 0x627, 0x62F, 0x631, 0x633, 0x62A, 0x20, 0x627, 0x633, 0x62A, 0x20, 0x6CC, 0x627, 0x20, 0x645, 0x646, 0x642, 0x636, 0x6CC, 0x20, 0x634, 0x62F, 0x647, 0x20, 0x627, 0x633, 0x62A, 0x2E, 0x20, 0x622, 0x62E, 0x631, 0x6CC, 0x646, 0x20, 0x627, 0x6CC, 0x645, 0x6CC, 0x644, 0x20, 0x631, 0x627, 0x20, 0x628, 0x631, 0x631, 0x633, 0x6CC, 0x20, 0x6A9, 0x646, 0x6CC, 0x62F, 0x20, 0x648, 0x20, 0x62F, 0x648, 0x628, 0x627, 0x631, 0x647, 0x20, 0x62A, 0x644, 0x627, 0x634, 0x20, 0x6A9, 0x646, 0x6CC, 0x62F, 0x2E],
  companySite: [0x648, 0x628, 0x200C, 0x633, 0x627, 0x6CC, 0x62A, 0x20, 0x634, 0x631, 0x6A9, 0x62A],
  optional: [0x28, 0x627, 0x62E, 0x62A, 0x6CC, 0x627, 0x631, 0x6CC, 0x29],
  updates: [0x6AF, 0x627, 0x647, 0x6CC, 0x20, 0x62E, 0x628, 0x631, 0x647, 0x627, 0x6CC, 0x20, 0x62A, 0x627, 0x632, 0x647, 0x654, 0x20, 0x645, 0x62D, 0x635, 0x648, 0x644,
    0x20, 0x631, 0x627, 0x20, 0x628, 0x631, 0x627, 0x6CC, 0x645, 0x20, 0x628, 0x641, 0x631, 0x633, 0x62A, 0x6CC, 0x62F, 0x20, 0x28, 0x627, 0x62E, 0x62A, 0x6CC, 0x627, 0x631, 0x6CC, 0x29, 0x2E],
  capped: [0x628, 0x631, 0x627, 0x6CC, 0x20, 0x627, 0x6CC, 0x646, 0x20, 0x627, 0x6CC, 0x645, 0x6CC, 0x644, 0x20, 0x6A9, 0x62F, 0x647, 0x627, 0x6CC, 0x20, 0x632, 0x6CC, 0x627, 0x62F, 0x6CC, 0x20, 0x62F, 0x631, 0x62E, 0x648, 0x627, 0x633, 0x62A, 0x20, 0x634, 0x62F, 0x647, 0x20, 0x627, 0x633, 0x62A, 0x2E, 0x20, 0x628, 0x639, 0x62F, 0x627, 0x64B, 0x20, 0x62F, 0x648, 0x628, 0x627, 0x631, 0x647, 0x20, 0x62A, 0x644, 0x627, 0x634, 0x20, 0x6A9, 0x646, 0x6CC, 0x62F, 0x2E],
  fullName: [0x646, 0x627, 0x645, 0x20, 0x6A9, 0x627, 0x645, 0x644, 0x20, 0x62E, 0x648, 0x62F, 0x20, 0x631, 0x627, 0x20, 0x648, 0x627, 0x631, 0x62F, 0x20, 0x6A9, 0x646, 0x6CC, 0x62F, 0x2E],
};
const F = (k) => String.fromCharCode(...FA[k]);

let failures = 0;
function check(name, got, want) {
  const ok = JSON.stringify(got) === JSON.stringify(want);
  if (!ok) failures++;
  console.log((ok ? 'PASS ' : 'FAIL ') + name + (ok ? '' : '\n     got  ' + JSON.stringify(got) + '\n     want ' + JSON.stringify(want)));
}

function installMock() {
  window.__requests = []; window.__reqMode = 'ok'; window.__issued = 0;
  const reply = (body, status, headers) => Promise.resolve(new Response(JSON.stringify(body), { status: status || 200, headers: headers || {} }));
  window.fetch = (u, opt) => {
    u = String(u); const p = u.slice(u.indexOf('/api/v1') + 7), method = (opt && opt.method) || 'GET';
    window.__requests.push([method, p, opt && opt.body ? JSON.parse(opt.body) : null]);
    if (p === '/auth/login-code/request') {
      if (window.__reqMode === 'capped') return reply({ error: { code: 'HTTP_ERROR', message: 'Too many codes were requested for this email. Try again later.' } }, 429, { 'Retry-After': '3600' });
      if (window.__reqMode === 'nodelivery') return reply({ error: { message: 'Email delivery is not available; no code was sent.' } }, 503);
      window.__issued += 1;
      return reply({ status: 'code_sent_if_account_exists', challenge: 'ch-' + window.__issued, expires_in_seconds: 300 }, 202);
    }
    if (p === '/auth/login-code/verify') {
      const b = JSON.parse(opt.body);
      // Like the server: the code works only with the challenge of the request that sent it (the latest here).
      if (b.code === '65432187' && b.challenge === 'ch-' + window.__issued) return reply({ access_token: 'tok-1', token_type: 'bearer', expires_in_minutes: 60 });
      return reply({ error: { message: 'Invalid or expired code.' } }, 401);
    }
    if (p === '/auth/signup/request') return reply({ status: 'code_sent', resend_available_in_seconds: 60, expires_in_seconds: 300 }, 202);
    return reply({ detail: 'Not found' }, 404);
  };
}

(async () => {
  const browser = await chromium.launch(process.env.PW_EXE ? { executablePath: process.env.PW_EXE } : {});
  const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
  const errors = [];
  page.on('pageerror', (e) => errors.push(String(e)));
  await page.goto(pageUrl);
  const settle = (ms) => page.waitForTimeout(ms || 150);
  const go = async (hash) => { await page.evaluate((h) => { location.hash = h; }, hash); await settle(); };
  const lang = async (l) => { await page.selectOption('#pick-lang', l); await settle(); };
  const auth = () => page.evaluate(() => (window.__requests || []).filter((r) => r[1].indexOf('/auth/login-code') === 0));
  const login = async (email) => { await go('#screen-login'); await page.fill('#login-email', email);
    await page.evaluate(() => document.querySelector('#screen-login .auth-form').requestSubmit()); await settle(250); };
  // Fill the eight boxes without input events (so the auto-verify does not fire), then press Verify.
  const verify = async (code) => { await page.evaluate((c) => { document.querySelectorAll('#screen-login-code .otp-box').forEach((b, i) => { b.value = c[i]; });
    document.getElementById('otp-verify-btn').click(); }, code); await settle(250); };
  const view = () => page.evaluate(() => ({ hash: location.hash, email: document.getElementById('login-code-email').textContent,
    msg: document.getElementById('otp-message').textContent, resend: document.getElementById('otp-resend-btn').textContent,
    locked: document.querySelector('#screen-login-code .otp-box').disabled, loginError: document.getElementById('login-error').textContent,
    boxes: Array.from(document.querySelectorAll('#screen-login-code .otp-box')).map((b) => b.value).join('') }));
  const hidden = (sel) => page.evaluate((s) => Array.from(document.querySelectorAll(s)).map((e) => getComputedStyle(e).display === 'none'), sel);

  // Sample mode.
  check('sample: both Google buttons and both dividers hidden as CLIENT-oidc', await hidden('[data-debt-hidden="CLIENT-oidc"]'), [true, true, true, true]);
  check('sample: the website field and the product-updates opt-in show (no debt left on sign-up but CLIENT-oidc)', await page.evaluate(() =>
    ['signup-site', 'signup-updates'].map((id) => !document.getElementById(id).closest('[data-debt-hidden]'))
      .concat([document.querySelector('label[for="signup-site"]').textContent, document.getElementById('signup-updates').closest('label').textContent.trim(),
        Array.from(document.querySelectorAll('#screen-signup [data-debt-hidden]')).map((e) => e.getAttribute('data-debt-hidden'))])),
    [true, true, 'Company website (optional)', 'Send me occasional product updates (optional).', ['CLIENT-oidc', 'CLIENT-oidc']]);
  await page.evaluate(() => { window.__sampleRequests = []; const f = window.fetch; window.fetch = (u, o) => { window.__sampleRequests.push(String(u)); return f(u, o); }; });
  await login('sample@shop.test');
  let v = await view();
  check('sample login: the code step, the email, no login-code request', [v.hash, v.email,
    await page.evaluate(() => window.__sampleRequests.filter((u) => u.indexOf('login-code') !== -1).length)], ['#screen-login-code', 'sample@shop.test', 0]);
  check('sample: eight boxes, each named', await page.evaluate(() => Array.from(document.querySelectorAll('#screen-login-code .otp-box'))
    .map((b) => b.getAttribute('aria-label'))), [1, 2, 3, 4, 5, 6, 7, 8].map((n) => 'Digit ' + n + ' of 8'));
  for (const c of ['00000000', '00000001', '00000002']) await verify(c);
  v = await view();
  check('sample: three wrong codes say so; the boxes stay open (nothing locks)', [v.msg, v.locked], ['That code is wrong or has expired. Check the latest email and try again.', false]);
  await verify('12345678');
  check('sample: the fixture code signs in', (await view()).msg, 'Verified ' + EM + ' signing you in' + ELL);
  await settle(600);

  // Live: the page names its AI Core.
  await page.evaluate(installMock);
  await page.evaluate(() => document.documentElement.setAttribute('data-core-url', 'http://core.test/'));
  await login('owner@shop.test');
  v = await view();
  check('Send login code: one POST with the email; the code step', [await auth(), v.hash, v.email, [iso('5:00'), iso('4:59')].map((x) => 'Resend code (' + x + ')').indexOf(v.resend) !== -1],
    [[['POST', '/auth/login-code/request', { email: 'owner@shop.test' }]], '#screen-login-code', 'owner@shop.test', true]);
  await verify('11111111');
  v = await view();
  check('401: the verify carries the challenge; wrong or expired; the boxes are cleared', [(await auth()).slice(-1)[0], v.msg, v.boxes, v.locked],
    [['POST', '/auth/login-code/verify', { email: 'owner@shop.test', challenge: 'ch-1', code: '11111111' }],
      'That code is wrong or has expired. Check the latest email and try again.', '', false]);
  await verify('22222222'); await verify('33333333');
  v = await view();
  check('three wrong codes in a row: the same 401 message; the boxes stay open (SEC-login-code-lockout)', [v.msg, v.locked], ['That code is wrong or has expired. Check the latest email and try again.', false]);
  await page.evaluate(() => { document.getElementById('otp-resend-btn').disabled = false; });
  let before = (await auth()).length;
  await login('owner@shop.test');
  await page.evaluate(() => { document.getElementById('otp-resend-btn').disabled = false; document.getElementById('otp-resend-btn').click(); }); await settle(250);
  check('Resend: one more request; a new code was sent', [(await auth()).slice(before).map((r) => r[1]), (await view()).msg],
    [['/auth/login-code/request', '/auth/login-code/request'], 'A new code was sent.']);
  await verify('65432187');
  check('success: the verify used the newest challenge (the resend replaced it)', (await auth()).slice(-1)[0],
    ['POST', '/auth/login-code/verify', { email: 'owner@shop.test', challenge: 'ch-3', code: '65432187' }]);
  check('success: AI Core connected with the returned token', await page.evaluate(() => window.AIOL_LIVE_STATE()), { base: 'http://core.test', token: 'tok-1' });
  await settle(700);
  check('success: the Dashboard opens', (await view()).hash, '#screen-dashboard');

  await page.evaluate(() => { window.__reqMode = 'capped'; });
  await login('owner@shop.test');
  v = await view();
  check('429 at the per-address cap: stays on the login page with its own message (no code step without a challenge)',
    [v.hash, v.loginError], ['#screen-login', 'Too many codes were requested for this email. Try again later.']);
  await lang('fa');
  check('fa: the per-address cap message', await page.evaluate(() => document.getElementById('login-error').textContent), F('capped'));
  await lang('en');
  await page.evaluate(() => { window.__reqMode = 'nodelivery'; });
  await login('owner@shop.test');
  v = await view();
  check('503: stays on the login page with its own message', [v.hash, v.loginError], ['#screen-login', 'Email delivery is not available; no code was sent.']);


  // Persian.
  await lang('fa');
  check('fa: login title and the delivery message', await page.evaluate(() => [document.getElementById('h-login').textContent,
    document.getElementById('login-error').textContent]), [F('welcome'), F('delivery')]);
  await page.evaluate(() => { window.__reqMode = 'ok'; });
  await login('owner@shop.test');
  await verify('11111111');
  check('fa: the code page sentence around the email, and the wrong-code message', await page.evaluate(() => [
    document.querySelector('#screen-login-code .auth-card__sub').firstChild.nodeValue.trim(), document.getElementById('otp-message').textContent]),
    [F('sentTo'), F('wrongCode')]);
  await go('#screen-signup');
  await page.evaluate(() => document.querySelector('#screen-signup .auth-form').requestSubmit()); await settle();
  check('fa: a sign-up validation message', await page.evaluate(() => document.getElementById('signup-error').textContent), F('fullName'));
  check('fa: the website label', await page.evaluate(() => { const l = document.querySelector('label[for="signup-site"]');
    return [l.firstChild.nodeValue.trim(), l.querySelector('.auth-optional').textContent]; }), [F('companySite'), F('optional')]);
  check('fa: the product-updates opt-in', await page.evaluate(() => document.getElementById('signup-updates').closest('label').textContent.trim()), F('updates'));
  await lang('en');
  check('back to English', await page.evaluate(() => document.getElementById('h-login').textContent), 'Welcome back');

  // Sign-up (V5-signup-website-field): the website goes with the request.
  const signups = () => page.evaluate(() => (window.__requests || []).filter((r) => r[1] === '/auth/signup/request').map((r) => r[2]));
  const signup = async (site) => { await go('#screen-signup'); await page.fill('#signup-name', 'Marzieh'); await page.fill('#signup-email', 'new@shop.test');
    await page.fill('#signup-company', 'Toranj'); await page.fill('#signup-site', site); await page.check('#signup-terms');
    await page.evaluate(() => document.querySelector('#screen-signup .auth-form').requestSubmit()); await settle(250); };
  await page.evaluate(() => { window.__reqMode = 'ok'; });
  await signup('http://toranj.test');
  check('sign-up: a website not starting with https:// is refused before sending', [await page.evaluate(() => document.getElementById('signup-error').textContent),
    (await signups()).length], ['The website must start with https://', 0]);
  await signup('  https://toranj.test  ');
  check('sign-up: one POST with the website (trimmed); the code step follows', [await signups(), (await view()).hash],
    [[{ organization_name: 'Toranj', owner_email: 'new@shop.test', owner_name: 'Marzieh', website: 'https://toranj.test', marketing_optin: false }], '#screen-login-code']);
  await signup('');
  check('sign-up: no website is sent as null', (await signups()).slice(-1)[0].website, null);
  await go('#screen-signup'); await page.check('#signup-updates');
  await page.evaluate(() => document.querySelector('#screen-signup .auth-form').requestSubmit()); await settle(250);
  check('sign-up: the ticked opt-in is sent as marketing_optin true', (await signups()).slice(-1)[0].marketing_optin, true);
  await page.evaluate(() => { window.AIOL_SIGNUP_EMAIL = null; document.querySelector('#screen-signup .auth-form').reset(); });   // back to the login flow
  check('no page errors', errors, []);

  await browser.close();
  console.log(failures ? failures + ' FAILED' : 'ALL PASSED');
  process.exit(failures ? 1 : 0);
})().catch((e) => { console.error(e); process.exit(2); });
