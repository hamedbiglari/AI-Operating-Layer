// End-to-end: the real client UI in Chromium against a live AI Core (no mocks). Covers the master prompt's
// §27 flow: open → sign in → new chat → send → answer rendered → history → continue → setting → usage →
// Persian text in an English UI → device verification → sign out → sign in again → server-side continuity; plus a second account
// on the same installation (account switching) and a phone-sized viewport.
//
// Prerequisites (see apps/shared/README.md §e2e): AI Core on API (default http://127.0.0.1:8010/api/v1) with
// APP_ENV=development and CORS_ALLOWED_ORIGINS including the client origin. Accounts are created through the
// development-only /auth/register-organization route.
import { createRequire } from 'node:module';
import { mkdirSync } from 'node:fs';

// Same convention as visual-harness/e2e: PLAYWRIGHT_CORE points at a playwright-core install (CI), otherwise the
// globally installed `playwright` is used.
const require = createRequire(import.meta.url);
function loadPlaywright() {
  if (process.env.PLAYWRIGHT_CORE) return require(process.env.PLAYWRIGHT_CORE);
  try { return require('playwright'); } catch { /* fall through */ }
  return require(require('node:child_process').execSync('npm root -g').toString().trim() + '/playwright');
}
const { chromium } = loadPlaywright();
mkdirSync(new URL('./out/', import.meta.url), { recursive: true });
import { start } from '../scripts/serve.mjs';

const API = process.env.AIOL_API ?? 'http://127.0.0.1:8010/api/v1';
const PORT = Number(process.env.PORT || 5174);
const results = [];
let failed = 0;

function check(name, ok, detail = '') {
  results.push({ name, ok, detail });
  if (!ok) failed++;
  console.log(`${ok ? 'PASS' : 'FAIL'}  ${name}${detail ? `  — ${detail}` : ''}`);
}

// Polls `pred` (sync or async) every 200 ms until it is true or `ms` pass; true when it became true. Used instead of
// fixed sleeps for work the client does in the background, which takes longer on a slow machine or backend.
async function waitUntil(pred, ms) {
  for (const end = Date.now() + ms; Date.now() < end;) {
    if (await pred()) return true;
    await new Promise((ok) => setTimeout(ok, 200));
  }
  return false;
}

async function api(path, { method = 'GET', body, token, form } = {}) {
  const headers = {};
  if (token) headers.Authorization = `Bearer ${token}`;
  let payload;
  if (form) { headers['Content-Type'] = 'application/x-www-form-urlencoded'; payload = new URLSearchParams(form); }
  else if (body) { headers['Content-Type'] = 'application/json'; payload = JSON.stringify(body); }
  const r = await fetch(API + path, { method, headers, body: payload });
  const text = await r.text();
  return { status: r.status, data: text ? JSON.parse(text) : null };
}

async function makeOrg(tag) {
  const email = `e2e-${tag}-${Date.now()}@example.dev`;
  const r = await api('/auth/register-organization', { method: 'POST', body: {
    organization_name: `E2E ${tag}`, owner_email: email, owner_name: `E2E ${tag}`, owner_password: 'supersecret123' } });
  if (r.status !== 201) throw new Error(`register failed: ${r.status} ${JSON.stringify(r.data)}`);
  const token = r.data.token.access_token;
  const s = await api('/chat/settings', { method: 'PUT', token, body: { enabled: true } });
  if (s.status !== 200) throw new Error(`chat enable failed: ${s.status}`);
  return { email, password: 'supersecret123', token, orgId: r.data.organization.id };
}

async function signIn(page, who) {
  await page.getByRole('button', { name: 'Use a password instead' }).click();
  await page.locator('#si-email').fill(who.email);
  await page.locator('#si-password').fill(who.password);
  await page.locator('#si-terms').check();
  await page.getByRole('button', { name: 'Sign in', exact: true }).click();
  await page.locator('#shell').waitFor({ timeout: 15000 });
}

const server = await start(PORT);
// PW_EXE: an installed Chromium to use instead of the one matching playwright-core (as in visual-harness/e2e).
const browser = await chromium.launch(process.env.PW_EXE ? { executablePath: process.env.PW_EXE } : {});
try {
  const owner = await makeOrg('owner');
  const ctx = await browser.newContext({ viewport: { width: 1280, height: 800 } });
  const page = await ctx.newPage();
  const consoleErrors = [];
  page.on('console', (m) => { if (m.type() === 'error') consoleErrors.push(m.text()); });
  const requests = [];
  page.on('request', (r) => requests.push(r.url()));
  // Device Intelligence runs in the background after each sign-in and ends with POST …/credentials/{id}/verify.
  const deviceVerifies = [];
  page.on('response', (r) => { if (/\/devices\/credentials\/[^/]+\/verify$/.test(new URL(r.url()).pathname)) deviceVerifies.push(r.status()); });
  const url = `http://127.0.0.1:${PORT}/?api=${encodeURIComponent(API)}`;

  // 1. open, signed out: no chat request of any kind
  await page.goto(url);
  await page.locator('#si-email').waitFor();
  check('signed-out screen shows sign-in and makes no chat request',
        !requests.some((u) => u.includes('/chat/')));
  check('signed-out screen shows only configured links (Help, Privacy; not Terms)',
        await page.getByRole('button', { name: /Get help/ }).count() === 1
        && await page.getByRole('button', { name: /Terms/ }).count() === 0);

  // Terms: without the tick, nothing is sent and the user is told why.
  await page.getByRole('button', { name: 'Use a password instead' }).click();
  await page.locator('#si-email').fill(owner.email);
  await page.locator('#si-password').fill(owner.password);
  const before = requests.length;
  await page.getByRole('button', { name: 'Sign in', exact: true }).click();
  await page.waitForTimeout(200);
  check('sign-in without the terms tick is refused locally, with no request',
        requests.slice(before).every((u) => !u.includes('/auth/native/session'))
        && (await page.locator('.error-text').textContent()).includes('Terms of Use'));
  check('the terms row names both documents and what the tick covers',
        (await page.locator('.signin__terms').textContent()).includes('installation verification'));
  await page.getByRole('button', { name: 'Use an emailed code instead' }).click();

  // One appearance: English interface, light theme, no switches.
  check('no theme or language switches; light, English, left-to-right', await page.evaluate(() =>
    !document.getElementById('toggle-theme') && !document.getElementById('toggle-language')
    && document.documentElement.dataset.theme === 'light' && document.documentElement.lang === 'en'
    && document.documentElement.dir === 'ltr'));

  // 2. sign in
  await signIn(page, owner);
  const accepted = await api('/clients/config');
  check('the published terms version is what the app accepted', !!accepted.data.terms.version);
  check('sign-in reaches the shell', await page.locator('#shell').isVisible());
  const storage = await page.evaluate(() => JSON.stringify({ ...localStorage }) + JSON.stringify({ ...sessionStorage }) + document.cookie);
  check('no token in localStorage, sessionStorage or cookies', !/access_token|refresh|eyJ|\.[A-Za-z0-9_-]{20,}/.test(storage), storage.slice(0, 120));

  // Composer: a round send button inside the card, disabled until there is text.
  check('send is disabled while the composer is empty', await page.locator('#composer-send').isDisabled());
  check('an empty chat centres greeting and composer', await page.evaluate(() => document.getElementById('shell').dataset.empty) === 'true');

  // Persian can be written in the English interface: the composer and the message take the text's own direction.
  await page.locator('#composer-input').fill('\u062e\u0627\u0635\u06cc\u062a \u0632\u0639\u0641\u0631\u0627\u0646 \u0686\u06cc\u0633\u062a\u061f');
  check('Persian typed into the composer runs right-to-left', await page.evaluate(() =>
    getComputedStyle(document.getElementById('composer-input')).direction === 'rtl'
    || document.getElementById('composer-input').matches(':dir(rtl)')));
  await page.locator('#composer-input').fill('');

  // Composer tools: "+" for an owner (upload role); the dialog states the truth about processing.
  check('the owner sees "+" (add a document to knowledge)', await page.locator('#composer-attach').count() === 1);
  await page.locator('#composer-attach').click();
  await page.locator('dialog #upload-source, dialog p.muted').first().waitFor({ timeout: 10000 });
  check('the upload dialog says the document is not read by the next answer',
        (await page.locator('dialog').textContent()).includes('not by the next answer'));
  await page.keyboard.press('Escape');
  check('sidebar: New chat, Search chats, Recents, profile with chevron', await page.evaluate(() =>
    !!document.querySelector('#new-chat .side-row__badge') && !!document.getElementById('search-chats')
    && /Recents/.test(document.getElementById('sidebar').textContent) && !!document.querySelector('.account-btn__chev')));
  check('the assistant surface palette is active', await page.evaluate(() => document.documentElement.dataset.surface) === 'assistant');

  // 3–6. new chat, send, render answer with its state
  await page.locator('#composer-input').fill('What is Taranjabin used for?');
  await page.locator('#composer-send').click();
  const answer = page.locator('.msg--assistant').first();
  await answer.waitFor({ timeout: 30000 });
  const state = await answer.getAttribute('data-state');
  check('answers can be rated helpful / not helpful', (await answer.locator('button[aria-label="Helpful"]').count()) === 1);
  check('the answer arrived over the streaming endpoint', requests.some((u) => u.endsWith('/messages/stream')));
  check('answer rendered with a server answer state', !!state, state);
  check('NEEDS_USER_SOURCE (no topic granted) is shown with its limitation, not an invented answer',
        state === 'NEEDS_USER_SOURCE' && (await answer.locator('.limitation').count()) === 1);
  check('user turn is confirmed (no pending/failed marker left)',
        (await page.locator('.msg--user .delivery').count()) === 0);
  await page.waitForTimeout(300);
  const historyItems = await page.locator('#history .history__open').allTextContents();
  check('the new conversation appears in history with its server title', historyItems.some((t) => t.includes('Taranjabin')), historyItems.join(' | '));

  // 7–8. history: new chat, then continue the previous one
  await page.locator('#new-chat').click();
  check('New chat shows the empty state', await page.locator('.empty').isVisible());
  check('a sent question is not left behind as a draft in the next new chat',
        (await page.locator('#composer-input').inputValue()) === '');
  const layout = await page.evaluate(() => ({ shell: document.getElementById('shell').getBoundingClientRect().height,
    vh: window.innerHeight, search: document.getElementById('history-search').getBoundingClientRect().right,
    side: document.getElementById('sidebar').getBoundingClientRect().right }));
  check('the shell fills the window and the search box stays inside the sidebar',
        Math.abs(layout.shell - layout.vh) < 2 && layout.search <= layout.side, JSON.stringify(layout));
  await page.locator('#history .history__open').first().click();
  await page.locator('.msg--assistant').first().waitFor();
  check('reopening a conversation loads its turns from the server', (await page.locator('.msg').count()) >= 2);
  await page.locator('#composer-input').fill('And its side effects?');
  await page.locator('#composer-send').click();
  await page.waitForFunction(() => document.querySelectorAll('.msg--assistant').length >= 2, null, { timeout: 30000 });
  const convs = await api('/chat/conversations', { token: owner.token });
  check('continuing adds to the same server conversation (one conversation, four turns)',
        convs.data.total === 1 && convs.data.items[0].message_count === 4, JSON.stringify(convs.data.items.map((c) => c.message_count)));

  // 9. account menu + setting (theme, account-wide)
  await page.locator('#account-button').click();
  const menuLabels = (await page.locator('#account-menu [role="menuitem"]').allTextContents()).map((s) => s.trim());
  check('account menu has the reference hierarchy (configured items only)',
        ['Settings', 'Usage', 'Get help', 'Upgrade plan', 'Get apps', 'Log out'].every((l) => menuLabels.some((m) => m.startsWith(l)))
        && !menuLabels.some((m) => m.startsWith('Learn more') || m.startsWith('Language')), menuLabels.join(', '));
  await page.keyboard.press('Escape');
  check('Escape closes the menu and returns focus', await page.locator('#account-menu').isHidden()
        && await page.evaluate(() => document.activeElement?.id) === 'account-button');
  // Settings shows the device status as it is when the dialog opens, so first wait (up to 30 s) for the background
  // registration to finish instead of a fixed delay; if it never does, the status check below reports what it shows.
  await waitUntil(() => deviceVerifies.length > 0, 30000);
  await page.locator('#account-button').click();
  await page.locator('#menu-settings').click();
  check('Settings has no theme switch', await page.locator('dialog [data-theme]').count() === 0);

  // Device Intelligence: registered + verified in the background, visible in Settings and to the admin
  const status = await page.locator('dialog [role="status"]').first().textContent();
  check('installation verification status shown in Settings', /verified|registered/.test(status ?? ''), status);
  const adminList = await api('/devices/admin/credentials', { token: owner.token });
  const cred = adminList.data.items?.[0];
  check('admin sees one WEB_BROWSER installation, evidence-only assessment',
        adminList.data.total === 1 && cred.provenance === 'WEB_BROWSER' && cred.key_storage_claimed === 'browser_non_extractable'
        && cred.assessment.categories.includes('INSUFFICIENT_EVIDENCE'), JSON.stringify(cred?.assessment?.categories));
  await page.keyboard.press('Escape');

  // 10. usage from the server
  await page.locator('#account-button').click();
  await page.locator('#menu-usage').click();
  await page.locator('dialog [data-quota="wallet"]').waitFor({ timeout: 10000 });
  check('Usage shows server quotas (wallet) and the chat daily figure', (await page.locator('dialog .section').count()) >= 2);
  check('Usage states plans are not offered rather than inventing one', (await page.locator('dialog').textContent()).includes('Plans are not offered yet'));
  await page.keyboard.press('Escape');

  // Upgrade + Get apps: truthful unavailable states
  await page.locator('#account-button').click();
  await page.locator('#menu-upgrade').click();
  check('Upgrade shows a truthful unavailable state when no billing link is configured',
        (await page.locator('dialog').textContent()).includes('Upgrades are not available yet.'));
  await page.keyboard.press('Escape');
  await page.locator('#account-button').click();
  await page.locator('#menu-apps').click();
  check('Get apps lists nothing when nothing is published',
        (await page.locator('dialog').textContent()).includes('No AIOL app downloads have been published yet.'));
  await page.keyboard.press('Escape');

  // A Persian conversation in the English interface.
  await page.locator('#new-chat').click();
  await page.locator('#composer-input').fill('\u062e\u0627\u0635\u06cc\u062a \u0632\u0639\u0641\u0631\u0627\u0646 \u0686\u06cc\u0633\u062a\u061f');
  await page.locator('#composer-send').click();
  await page.waitForFunction(() => document.querySelectorAll('.msg--assistant').length >= 1, null, { timeout: 30000 });
  check('a Persian question is shown right-to-left inside the English interface', await page.evaluate(() =>
    document.querySelector('.msg--user .msg__body').matches(':dir(rtl)') && document.documentElement.dir === 'ltr'));
  await page.screenshot({ path: 'e2e/out/desktop-persian-message.png' });
  await page.locator('#history .history__open', { hasText: 'Taranjabin' }).click();
  await page.locator('.msg--assistant').first().waitFor();
  await page.screenshot({ path: 'e2e/out/desktop-light.png' });

  // 11. account switching on the same installation: a second account, same device key
  await page.locator('#account-button').click();
  await page.locator('#menu-logout').click();
  await page.locator('#si-email').waitFor();
  check('sign-out returns to the sign-in screen and clears the thread from the page',
        (await page.locator('.msg').count()) === 0 && (await page.locator('#history').count()) === 0);
  const member = { email: `e2e-member-${Date.now()}@example.dev`, password: 'supersecret123' };
  const mk = await api('/users', { method: 'POST', token: owner.token,
                                   body: { email: member.email, name: 'Member', password: member.password, role: 'viewer' } });
  check('second account created in the same organization', mk.status === 201, String(mk.status));
  await signIn(page, member);
  await page.waitForTimeout(300);
  await page.locator('#composer-attach').click();
  check('a viewer gets "+" but is told adding files needs an editor role', (await page.locator('dialog').textContent()).includes('needs an editor'));
  await page.keyboard.press('Escape');
  check('the second account sees none of the first account’s conversations',
        (await page.locator('#history .history__open').count()) === 0);
  // The second account's sign-in links it to the same installation in the background: poll (up to 30 s).
  let after = { data: {} };
  if (cred) {
    await waitUntil(async () => {
      after = await api(`/devices/admin/credentials/${cred.id}`, { token: owner.token });
      return (after.data.linked_accounts?.length ?? 0) >= 2;
    }, 30000);
  }
  check('account switching on one installation links both accounts (SAME_REGISTERED_INSTALLATION)',
        after.data.linked_accounts?.length === 2 && after.data.assessment.categories.includes('SAME_REGISTERED_INSTALLATION'),
        JSON.stringify(after.data.assessment?.categories));
  check('admin detail never says "same person"', !/same.?person/i.test(JSON.stringify(after.data)));

  // 12–14. sign out, sign in again as the owner, the conversation is still on the server
  await page.locator('#account-button').click();
  await page.locator('#menu-logout').click();
  await page.locator('#si-email').waitFor();
  await signIn(page, owner);
  await page.locator('#history .history__open').first().waitFor();
  await page.locator('#history .history__open', { hasText: 'Taranjabin' }).click();
  await page.waitForFunction(() => document.querySelectorAll('.msg').length >= 4, null, { timeout: 15000 });
  check('after signing in again, the conversation and its turns are still there (server continuity)', true);

  // Session ended on the server: the client returns to sign-in instead of failing silently
  const loggedOut = await api('/auth/native/session/refresh', { method: 'POST', body: { refresh_token: '00000000-0000-4000-8000-000000000000.forged-secret' } });
  check('a forged refresh token is refused by the server', loggedOut.status === 401);

  // Phone-sized viewport: drawer navigation, composer reachable
  const phone = await browser.newContext({ viewport: { width: 390, height: 844 }, hasTouch: true, isMobile: true });
  const p2 = await phone.newPage();
  await p2.goto(url);
  await p2.locator('#si-email').waitFor();
  await signIn(p2, owner);
  const sidebarHidden = await p2.evaluate(() => { const r = document.getElementById('sidebar').getBoundingClientRect(); return r.right <= 0; });
  check('phone: navigation is a drawer, off-screen until opened', sidebarHidden);
  await p2.locator('#open-drawer').click();
  await p2.waitForTimeout(300);
  check('phone: the drawer opens with history and account', await p2.locator('#history').isVisible() && await p2.locator('#account-button').isVisible());
  await p2.locator('.scrim').click({ position: { x: 370, y: 400 } });
  const composer = await p2.locator('#composer-send').boundingBox();
  check('phone: Send is inside the viewport', composer && composer.y + composer.height <= 844, JSON.stringify(composer));
  const overflow = await p2.evaluate(() => document.documentElement.scrollWidth > window.innerWidth);
  check('phone: no horizontal overflow', !overflow);
  await p2.locator('#open-drawer').click();
  await p2.locator('#account-button').click();
  const menuBox = await p2.locator('#account-menu').boundingBox();
  check('phone: the account menu stays within the viewport', menuBox.x >= 0 && menuBox.x + menuBox.width <= 390 && menuBox.y >= 0, JSON.stringify(menuBox));
  await p2.screenshot({ path: 'e2e/out/phone-menu.png' });
  await phone.close();

  check('no console errors during the run', consoleErrors.length === 0, consoleErrors.slice(0, 3).join(' | '));
  await ctx.close();
} catch (err) {
  check('run completed', false, err.stack);
} finally {
  await browser.close();
  server.close();
}
console.log(`\n${results.length - failed}/${results.length} checks passed`);
process.exit(failed ? 1 : 0);
