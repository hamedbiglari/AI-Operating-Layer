import { test } from 'node:test';
import assert from 'node:assert/strict';
import { Http } from '../app/src/core/http.js';
import { Session } from '../app/src/core/session.js';
import { DeviceIntelligence, DeviceStatus } from '../app/src/core/device.js';
import { fakeFetch, MemoryBridge, MemoryStorage, noSleep } from './helpers.js';

const TOKENS = (n) => ({ access_token: `a${n}`, token_type: 'bearer', expires_in_minutes: 15,
                         refresh_token: `sid.secret${n}`, refresh_expires_at: '2030-01-01T00:00:00Z' });
const ME = { user: { id: 'u1', email: 'a@b.dev', name: 'A', role: 'owner' }, organization: { id: 'o1', name: 'Org' } };

function setup(handler) {
  const bridge = new MemoryBridge();
  let session;
  const f = fakeFetch(handler);
  const http = new Http({ baseUrl: 'https://a.test/api/v1', token: () => session.token(), refresh: () => session.refresh(),
                          fetch: f, sleep: noSleep });
  session = new Session({ bridge, http });
  return { bridge, http, session, f };
}

test('sign-in keeps the access token in memory and the refresh secret only in the vault', async () => {
  const { bridge, session, f } = setup((req) => (req.url.endsWith('/auth/native/session') ? { body: TOKENS(1) } : { body: ME }));
  await session.signIn({ email: 'a@b.dev', code: '123456' });
  assert.equal(session.state, 'signed_in');
  assert.equal(session.token(), 'a1');
  assert.equal(await bridge.vaultGet('aiol.refresh'), 'sid.secret1');
  assert.deepEqual(f.calls[0].body, { grant: 'login_code', email: 'a@b.dev', code: '123456' });
  assert.ok(!f.calls[0].url.includes('secret'), 'no secret in a URL');
});

test('concurrent refreshes share one rotation (a second rotation would look like theft)', async () => {
  let n = 0;
  const { bridge, session, f } = setup(async (req) => {
    if (req.url.endsWith('/refresh')) { n++; await new Promise((r) => setTimeout(r, 5)); return { body: TOKENS(2) }; }
    return { body: ME };
  });
  await bridge.vaultSet('aiol.refresh', 'sid.secret1');
  const [a, b, c] = await Promise.all([session.refresh(), session.refresh(), session.refresh()]);
  assert.ok(a && b && c);
  assert.equal(n, 1);
  assert.equal(f.calls.filter((x) => x.url.endsWith('/refresh')).length, 1);
});

test('a refused refresh clears the session; a network failure keeps it', async () => {
  const s1 = setup(() => ({ status: 401, body: { error: { message: 'gone' } } }));
  await s1.bridge.vaultSet('aiol.refresh', 'sid.x');
  assert.equal(await s1.session.refresh(), false);
  assert.equal(await s1.bridge.vaultGet('aiol.refresh'), null);

  const s2 = setup(() => new TypeError('offline'));
  await s2.bridge.vaultSet('aiol.refresh', 'sid.x');
  assert.equal(await s2.session.refresh(), false);
  assert.equal(await s2.bridge.vaultGet('aiol.refresh'), 'sid.x', 'offline is not a lost session');
});

test('sign-out revokes on the server, then clears local state even when offline', async () => {
  const { bridge, session, f } = setup((req) => (req.url.endsWith('/auth/native/session') ? { body: TOKENS(1) }
    : req.url.endsWith('/end') ? new TypeError('offline') : { body: ME }));
  await session.signIn({ email: 'a@b.dev', password: 'pw' });
  const events = [];
  session.on((s) => events.push(s.state));
  await session.signOut();
  assert.ok(f.calls.some((c) => c.url.endsWith('/auth/native/session/end') && c.body.refresh_token === 'sid.secret1'));
  assert.equal(session.token(), null);
  assert.equal(session.user, null);
  assert.equal(await bridge.vaultGet('aiol.refresh'), null);
  assert.deepEqual(events, ['signed_out']);
  assert.ok(!f.calls.some((c) => c.method === 'DELETE' && c.url.includes('/chat/')), 'sign-out never deletes chats');
});

test('restore() uses the stored secret; none stored means signed out without a request', async () => {
  const empty = setup(() => ({ body: ME }));
  assert.equal(await empty.session.restore(), false);
  assert.equal(empty.f.calls.length, 0);
  const s = setup((req) => (req.url.endsWith('/refresh') ? { body: TOKENS(3) } : { body: ME }));
  await s.bridge.vaultSet('aiol.refresh', 'sid.secret2');
  assert.equal(await s.session.restore(), true);
  assert.equal(s.session.user.email, 'a@b.dev');
});

function deviceSetup(handler) {
  const bridge = new MemoryBridge();
  const f = fakeFetch(handler);
  const http = new Http({ baseUrl: 'https://a.test/api/v1', token: () => 't', fetch: f, sleep: noSleep });
  return { bridge, f, d: new DeviceIntelligence({ bridge, http, prefs: new MemoryStorage() }) };
}

const CH = (p) => ({ challenge_id: `c-${p}`, nonce: 'n'.repeat(43), signing_input: `AIOL-DEVICE-v1\n${p}` });

test('device: register, then verify, signing exactly the server-provided input', async () => {
  const { bridge, f, d } = deviceSetup((req) => {
    if (req.url.endsWith('/devices/challenges')) return { status: 201, body: CH(req.body.purpose) };
    if (req.url.endsWith('/devices/credentials')) return { status: 201, body: { id: 'cred1' } };
    return { body: { id: 'cred1' } };
  });
  assert.equal(await d.ensure(), DeviceStatus.VERIFIED);
  assert.deepEqual(bridge.signed, ['AIOL-DEVICE-v1\nregister', 'AIOL-DEVICE-v1\nverify']);
  const reg = f.calls.find((c) => c.url.endsWith('/devices/credentials'));
  assert.equal(reg.body.public_key, 'PUB');
  assert.equal(reg.body.platform, 'windows');
  assert.ok(!JSON.stringify(f.calls).includes('PRIVATE'), 'no private key material ever leaves the bridge');
  assert.ok(f.calls.some((c) => c.url.endsWith('/devices/credentials/cred1/verify')));
});

test('device: any failure is contained and reported as a status, never thrown', async () => {
  const { d } = deviceSetup(() => ({ status: 500, body: {} }));
  assert.equal(await d.ensure(), DeviceStatus.FAILED);
  const off = deviceSetup(() => new TypeError('offline'));
  assert.equal(await off.d.ensure(), DeviceStatus.FAILED);
});

test('device: a revoked key is forgotten so a fresh one is created next time', async () => {
  const { bridge, d } = deviceSetup((req) => (req.url.endsWith('/challenges') ? { status: 201, body: CH('register') }
    : { status: 409, body: { error: { message: 'revoked', reason: 'credential_revoked' } } }));
  assert.equal(await d.ensure(), DeviceStatus.REVOKED);
  assert.equal(bridge.keyDeleted, 1);
});

test('device: turning it off unlinks on the server, deletes the key, and is remembered', async () => {
  const { bridge, f, d } = deviceSetup((req) => {
    if (req.url.endsWith('/devices/challenges')) return { status: 201, body: CH(req.body.purpose) };
    if (req.method === 'DELETE') return { status: 204 };
    return { status: 201, body: { id: 'cred1' } };
  });
  await d.ensure();
  await d.disable();
  assert.ok(f.calls.some((c) => c.method === 'DELETE' && c.url.endsWith('/devices/credentials/cred1')));
  assert.equal(bridge.keyDeleted, 1);
  const before = f.calls.length;
  assert.equal(await d.ensure(), DeviceStatus.OFF);
  assert.equal(f.calls.length, before, 'off means no device requests at all');
});

test('device: server-disabled means unavailable, with no requests', async () => {
  const { f, d } = deviceSetup(() => ({ body: {} }));
  assert.equal(await d.ensure({ serverEnabled: false }), DeviceStatus.UNAVAILABLE);
  assert.equal(f.calls.length, 0);
});
