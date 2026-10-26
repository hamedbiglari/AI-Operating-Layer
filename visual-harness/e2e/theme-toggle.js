#!/usr/bin/env node
/*
 * Browser checks for the topbar theme toggle (V5-theme-toggle-ui).
 *   Sample: a click flips data-theme, aria-pressed, the label and the icon,
 *           and saves nothing, since nothing is connected.
 *   Live:   a click sends PUT /users/me/preferences {theme}; the saved theme
 *           comes back after a reload; a preferences reply that arrives after
 *           a click does not undo it. Persian labels, across a language switch.
 * Runs on file:// with /users/me/preferences mocked. The mock's state is kept
 * in this process, so it survives a reload. Persian expectations are built
 * from code points, so this file stays ASCII and no rendering can reverse them.
 *
 * Usage: node visual-harness/e2e/theme-toggle.js
 *   PLAYWRIGHT_CORE, PW_EXE as in knowledge-quickfix.js
 * Exit: 0 all pass, 1 a check failed, 2 the run itself failed.
 */
const path = require('path');
const url = require('url');
const { chromium } = require(process.env.PLAYWRIGHT_CORE || 'playwright-core');

const pageUrl = url.pathToFileURL(path.join(__dirname, '..', 'index.html')).href + '#screen-dashboard';
const fa = (...codes) => String.fromCharCode(...codes);
const SWITCH_TO_THEME = [0x62A, 0x63A, 0x6CC, 0x6CC, 0x631, 0x20, 0x628, 0x647, 0x20, 0x62A, 0x645, 0x20];
const FA = {
  darkTheme: fa(0x62A, 0x645, 0x20, 0x62A, 0x627, 0x631, 0x6CC, 0x6A9),
  switchToDark: fa(...SWITCH_TO_THEME, 0x62A, 0x627, 0x631, 0x6CC, 0x6A9),
  switchToLight: fa(...SWITCH_TO_THEME, 0x631, 0x648, 0x634, 0x646),
};

let failures = 0;
function check(name, got, want) {
  const ok = JSON.stringify(got) === JSON.stringify(want);
  if (!ok) failures++;
  console.log((ok ? 'PASS ' : 'FAIL ') + name + (ok ? '' : '\n     got  ' + JSON.stringify(got) + '\n     want ' + JSON.stringify(want)));
}

// The preferences "server". GET answers with the state as it was when the
// request arrived, after server.delay ms, like a slow network.
const server = { theme: 'light', delay: 0, gets: 0, answered: 0, puts: [] };
async function prefs(method, body) {
  if (method === 'PUT') { const b = JSON.parse(body); server.puts.push(b); Object.assign(server, b.theme ? { theme: b.theme } : {}); }
  else server.gets++;
  const reply = JSON.stringify({ language: 'en', theme: server.theme, notifications: {}, persisted: true, updated_at: '2026-10-26T10:00:00Z' });
  if (method !== 'PUT') { await new Promise((ok) => setTimeout(ok, server.delay)); server.answered++; }
  return reply;
}
// Runs in the page on every load: preferences go to the server above,
// anything else Cloud Core is asked for is a 404.
function mockFetch() {
  window.fetch = (u, opts) => {
    opts = opts || {};
    if (String(u).endsWith('/users/me/preferences')) {
      return window.__prefs(opts.method || 'GET', opts.body || null).then((b) => new Response(b, { status: 200 }));
    }
    return Promise.resolve(new Response('{}', { status: 404 }));
  };
}

(async () => {
  const browser = await chromium.launch(process.env.PW_EXE ? { executablePath: process.env.PW_EXE } : {});
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 }, colorScheme: 'light' });
  await page.exposeFunction('__prefs', prefs);
  await page.addInitScript(mockFetch);
  await page.goto(pageUrl);

  const state = () => page.evaluate(() => {
    const b = document.getElementById('topbar-theme'), moon = b.querySelector('[data-theme-icon="moon"]');
    return { theme: document.documentElement.getAttribute('data-theme'), pressed: b.getAttribute('aria-pressed'),
      label: b.getAttribute('aria-label'), title: b.getAttribute('title'),
      icon: !moon ? 'none' : getComputedStyle(moon).display === 'none' ? 'sun' : 'moon',
      icons: b.querySelectorAll('svg:not([hidden])').length };
  });
  // Toggle-button pattern: a fixed name, the state in aria-pressed, the next action in the tooltip.
  const light = { theme: 'light', pressed: 'false', label: 'Dark theme', title: 'Switch to dark theme', icon: 'moon', icons: 1 };
  const dark = { theme: 'dark', pressed: 'true', label: 'Dark theme', title: 'Switch to light theme', icon: 'sun', icons: 1 };
  const click = () => page.click('#topbar-theme');
  const until = async (test) => { for (let i = 0; i < 150 && !test(); i++) await page.waitForTimeout(20); };
  // The page applies a reply a moment after the mock has sent it.
  const answered = async () => { await until(() => server.answered === server.gets); await page.waitForTimeout(100); };
  const connect = async () => {
    const asked = server.gets;
    await page.evaluate(() => window.AIOL_LIVE_CONNECT('http://core.test', 'tok'));
    await until(() => server.gets > asked);
  };

  // Sample mode
  check('first load follows the system scheme: light, not pressed, offers dark', await state(), Object.assign({}, light, { theme: null }));
  await click();
  check('a click turns the theme dark and the button pressed', await state(), dark);
  await click();
  check('a second click turns it back to light', await state(), light);
  check('not connected: nothing is saved', server.puts.length, 0);

  // Live: the click is saved
  await connect(); await answered();
  check('connected: the saved light theme is kept', await state(), light);
  await click();
  check('live click: dark', await state(), dark);
  await until(() => server.puts.length > 0);
  check('live click sends PUT {theme: dark}', server.puts, [{ theme: 'dark' }]);

  // Reload: the saved theme comes back
  await page.reload(); await connect(); await answered();
  check('after a reload the saved dark theme is applied', await state(), dark);

  // Race: the reply to GET arrives after the user has clicked
  server.theme = 'light'; server.delay = 600; server.puts = [];
  await page.reload(); await connect();
  check('the preferences reply is still pending', server.answered < server.gets, true);
  await click();
  await answered();
  check('a late reply (light) does not undo the click (dark)', await state(), dark);
  check('the click was saved', server.puts, [{ theme: 'dark' }]);
  server.delay = 0;

  // Persian: the labels follow the state and the language
  await page.selectOption('#pick-lang', 'fa');
  check('fa: fixed name, dark state tooltip offers the light theme', [(await state()).label, (await state()).title], [FA.darkTheme, FA.switchToLight]);
  await click();
  check('fa: after a click the name stays, the tooltip offers the dark theme', [(await state()).label, (await state()).title], [FA.darkTheme, FA.switchToDark]);
  await page.selectOption('#pick-lang', 'en');
  check('back to English: the current label is English again', await state(), light);

  await browser.close();
  console.log(failures ? failures + ' FAILED' : 'ALL PASSED');
  process.exit(failures ? 1 : 0);
})().catch((e) => { console.error(e); process.exit(2); });
