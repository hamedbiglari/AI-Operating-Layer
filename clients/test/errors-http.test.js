import { test } from 'node:test';
import assert from 'node:assert/strict';
import { ErrorKind, fromResponse } from '../app/src/core/errors.js';
import { Http } from '../app/src/core/http.js';
import { backoffDelays, newRequestId } from '../app/src/core/retry.js';
import { fakeFetch, noSleep } from './helpers.js';

test('status codes map to one kind each, and server errors never leak their text', () => {
  const env = (m, reason) => ({ error: { code: 'X', message: m, reason }, request_id: 'r1' });
  assert.equal(fromResponse(401, env('no')).kind, ErrorKind.UNAUTHORIZED);
  assert.equal(fromResponse(403, env('no')).kind, ErrorKind.FORBIDDEN);
  assert.equal(fromResponse(402, env('pay')).kind, ErrorKind.QUOTA_EXHAUSTED);
  assert.equal(fromResponse(429, env('Daily chat limit reached (5 answers in 24 hours).')).kind, ErrorKind.QUOTA_EXHAUSTED);
  assert.equal(fromResponse(429, env('Too many requests.'), { 'retry-after': '7' }).retryAfter, 7);
  assert.equal(fromResponse(409, env('busy', 'request_in_progress')).kind, ErrorKind.IN_PROGRESS);
  assert.equal(fromResponse(409, env('x', 'challenge_replayed')).reason, 'challenge_replayed');
  assert.equal(fromResponse(422, env('bad')).kind, ErrorKind.VALIDATION);
  assert.equal(fromResponse(503, env('db down at 10.0.0.3')).kind, ErrorKind.SERVER_RETRYABLE);
  const e500 = fromResponse(500, env('Traceback (most recent call last): secret'));
  assert.equal(e500.kind, ErrorKind.SERVER);
  assert.ok(!e500.message.includes('Traceback'), 'a stack trace is never shown');
  assert.equal(fromResponse(500, 'not json').kind, ErrorKind.SERVER);
});

test('GET retries transport failures with backoff, a POST is never retried blindly', async () => {
  let n = 0;
  const f = fakeFetch(() => (++n < 3 ? new TypeError('offline') : { body: { ok: 1 } }));
  const http = new Http({ baseUrl: 'https://a.test/api/v1', token: () => 't', fetch: f, sleep: noSleep });
  assert.deepEqual(await http.get('/x'), { ok: 1 });
  assert.equal(f.calls.length, 3);

  const g = fakeFetch(() => new TypeError('offline'));
  const http2 = new Http({ baseUrl: 'https://a.test/api/v1', token: () => 't', fetch: g, sleep: noSleep });
  await assert.rejects(http2.post('/chat', {}), (e) => e.kind === ErrorKind.NETWORK);
  assert.equal(g.calls.length, 1, 'non-idempotent request must not be repeated');
});

test('a 401 triggers exactly one refresh and one retry; a failed refresh loses the session', async () => {
  let token = 'old';
  const f = fakeFetch((req) => (req.headers.Authorization === 'Bearer new' ? { body: { ok: true } } : { status: 401, body: {} }));
  let refreshes = 0;
  const http = new Http({ baseUrl: 'https://a.test', token: () => token, fetch: f, sleep: noSleep,
                          refresh: async () => { refreshes++; token = 'new'; return true; } });
  assert.deepEqual(await http.get('/me'), { ok: true });
  assert.equal(refreshes, 1);

  let lost = 0;
  const http2 = new Http({ baseUrl: 'https://a.test', token: () => 'x', fetch: fakeFetch(() => ({ status: 401 })),
                           refresh: async () => false, onSessionLost: () => lost++, sleep: noSleep });
  await assert.rejects(http2.get('/me'), (e) => e.kind === ErrorKind.SESSION_EXPIRED);
  assert.equal(lost, 1);
});

test('requests never send cookies and never follow redirects', async () => {
  let init;
  const http = new Http({ baseUrl: 'https://a.test', token: () => 't',
                          fetch: async (u, i) => { init = i; return { ok: true, status: 204, headers: { get: () => null }, text: async () => '' }; } });
  await http.del('/x');
  assert.equal(init.credentials, 'omit');
  assert.equal(init.redirect, 'error');
});

test('an authenticated call without a token fails locally without touching the network', async () => {
  const f = fakeFetch(() => ({ body: {} }));
  const http = new Http({ baseUrl: 'https://a.test', token: () => null, fetch: f, sleep: noSleep });
  await assert.rejects(http.get('/me', { retries: 0 }), (e) => e.kind === ErrorKind.SESSION_EXPIRED);
  assert.equal(f.calls.length, 0);
});

test('backoff is bounded and jittered; request ids match the server pattern', () => {
  const d = backoffDelays(5, { random: () => 1 });
  assert.equal(d.length, 5);
  assert.ok(d.every((x) => x <= 8000));
  assert.ok(backoffDelays(3, { random: () => 0 }).every((x, i) => x === Math.min(8000, 500 * 2 ** i) / 2));
  const id = newRequestId();
  assert.match(id, /^[A-Za-z0-9_-]{8,64}$/);
  assert.notEqual(id, newRequestId());
});
