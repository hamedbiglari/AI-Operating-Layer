import { test } from 'node:test';
import assert from 'node:assert/strict';
import { Http } from '../app/src/core/http.js';
import { Conversations, mergeOrdered } from '../app/src/core/conversations.js';
import { fakeFetch, noSleep } from './helpers.js';

function server() {
  const msgs = [];
  let pos = 0;
  const seen = new Map();
  const handler = (req) => {
    if (req.url.includes('/messages?')) {
      const sorted = [...msgs].sort((a, b) => b.position - a.position);
      return { body: { items: sorted, total: msgs.length, limit: 50, offset: 0 } };
    }
    if (req.url.endsWith('/messages') && req.method === 'POST') {
      if (seen.has(req.body.client_request_id)) return { body: seen.get(req.body.client_request_id) };
      const u = { id: `m${++pos}`, position: pos, role: 'user', text: req.body.question, client_request_id: req.body.client_request_id };
      const a = { id: `m${++pos}`, position: pos, role: 'assistant', text: 'answer', answer_state: 'UNKNOWN', answers_message_id: u.id };
      msgs.push(u, a);
      seen.set(req.body.client_request_id, a);
      return { status: 201, body: a };
    }
    if (req.url.includes('/chat/conversations?')) return { body: { items: [{ id: 'c1', title: 'x' }], total: 1 } };
    return { body: {} };
  };
  return { msgs, handler };
}

test('a question is pending until the server answers, then both turns are confirmed in server order', async () => {
  const s = server();
  const store = new Conversations({ http: new Http({ baseUrl: 'https://a.test', token: () => 't', fetch: fakeFetch(s.handler), sleep: noSleep }) });
  const states = [];
  store.on(() => states.push(store.thread('c1').messages.map((m) => m.delivery).join(',')));
  await store.ask('c1', 'hello');
  assert.equal(states[0], 'pending');
  const th = store.thread('c1').messages;
  assert.deepEqual(th.map((m) => [m.role, m.delivery]), [['user', 'confirmed'], ['assistant', 'confirmed']]);
  assert.deepEqual(th.map((m) => m.position), [1, 2]);
});

test('a failed send stays failed (never shown as saved) and Retry reuses the same idempotency key', async () => {
  const s = server();
  let fail = true;
  const f = fakeFetch((req) => (fail && req.method === 'POST' ? new TypeError('offline') : s.handler(req)));
  const store = new Conversations({ http: new Http({ baseUrl: 'https://a.test', token: () => 't', fetch: f, sleep: noSleep }) });
  await assert.rejects(store.ask('c1', 'hello'));
  const local = store.thread('c1').messages[0];
  assert.equal(local.delivery, 'failed');
  const key = local.clientRequestId;
  fail = false;
  await store.retry('c1', local);
  const posts = f.calls.filter((c) => c.method === 'POST');
  assert.equal(posts.length, 2);
  assert.equal(posts[0].body.client_request_id, key);
  assert.equal(posts[1].body.client_request_id, key);
  assert.equal(s.msgs.length, 2, 'the server stored the question once');
});

test('stopping (abort) marks the turn unknown, not failed and not saved', async () => {
  const s = server();
  const f = fakeFetch((req, n) => (req.method === 'POST' ? new Promise((_, rej) => req.signal.addEventListener('abort', () => rej(new Error('aborted')))) : s.handler(req)));
  const store = new Conversations({ http: new Http({ baseUrl: 'https://a.test', token: () => 't', fetch: f, sleep: noSleep }) });
  const ac = new AbortController();
  const p = store.ask('c1', 'slow', { signal: ac.signal });
  ac.abort();
  await assert.rejects(p, (e) => e.kind === 'aborted');
  assert.equal(store.thread('c1').messages[0].delivery, 'unknown');
});

test('reset() drops every list, thread and draft (account switching)', async () => {
  const store = new Conversations({ http: new Http({ baseUrl: 'https://a.test', token: () => 't', fetch: fakeFetch(server().handler) }) });
  await store.loadList();
  store.setDraft('c1', 'unsent');
  store.thread('c1').messages.push({ role: 'user', text: 'x' });
  store.reset();
  assert.equal(store.items.length, 0);
  assert.equal(store.draft('c1'), '');
  assert.equal(store.thread('c1').messages.length, 0);
});

test('mergeOrdered sorts confirmed by server position and keeps local turns last', () => {
  const out = mergeOrdered([{ position: 3 }, { position: 1 }], [{ localId: 'x' }]);
  assert.deepEqual(out.map((m) => m.position ?? m.localId), [1, 3, 'x']);
});
