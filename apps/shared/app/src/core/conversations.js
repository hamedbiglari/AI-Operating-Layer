// Conversation state (ADR-137 §chat). The server is the record; this is a view of it plus the honest state of
// whatever has not been confirmed yet.
//
// Message delivery states (never shown as "saved" until the server says so):
//   pending      sent, waiting for the server's answer
//   confirmed    the server returned it (has a server id)
//   failed       the request failed; Retry re-sends with the SAME client_request_id, so the server answers
//                with the stored turn if it already got the question — never a duplicate question or charge
//   unknown      the user pressed Stop or the connection dropped mid-answer; the server may still have saved
//                it. Reloading the conversation resolves it.
//
// Nothing is written to disk. Lists, messages and drafts live in memory and are dropped on sign-out and on
// account switch, so one account's conversations can never appear under another.

import { ErrorKind } from './errors.js';
import { newRequestId } from './retry.js';

const PAGE = 50;

export class Conversations {
  constructor({ http }) {
    this.http = http;
    this.reset();
  }

  reset() {
    this.items = [];
    this.total = 0;
    this.query = '';
    this.threads = new Map();   // conversationId -> {messages, total, loadedAll}
    this.drafts = new Map();    // conversationId|'new' -> text
    this.listeners = new Set();
  }

  on(fn) { this.listeners.add(fn); return () => this.listeners.delete(fn); }
  emit() { for (const fn of this.listeners) fn(this); }

  async loadList({ query = this.query, offset = 0 } = {}) {
    this.query = query;
    const q = new URLSearchParams({ limit: String(PAGE), offset: String(offset), state: 'active',
                                    sort_by: 'last_message_at', sort_dir: 'desc' });
    if (query.trim()) q.set('q', query.trim());
    const page = await this.http.get(`/chat/conversations?${q}`);
    this.items = offset ? [...this.items, ...page.items] : page.items;
    this.total = page.total;
    this.emit();
    return page;
  }

  get hasMore() { return this.items.length < this.total; }

  async create() {
    const c = await this.http.post('/chat/conversations', {}, { retries: 0 });
    this.items = [c, ...this.items];
    this.total += 1;
    this.emit();
    return c;
  }

  async rename(id, title) {
    const c = await this.http.patch(`/chat/conversations/${id}`, { title });
    this.items = this.items.map((x) => (x.id === id ? { ...x, ...c } : x));
    this.emit();
  }

  async archive(id) {
    await this.http.post(`/chat/conversations/${id}/archive`, {}, { retries: 1 });
    this.#drop(id);
  }

  async remove(id) {
    await this.http.del(`/chat/conversations/${id}`);
    this.#drop(id);
  }

  #drop(id) {
    this.items = this.items.filter((x) => x.id !== id);
    this.total = Math.max(0, this.total - 1);
    this.threads.delete(id);
    this.drafts.delete(id);
    this.emit();
  }

  thread(id) {
    if (!this.threads.has(id)) this.threads.set(id, { messages: [], total: 0, loadedAll: false });
    return this.threads.get(id);
  }

  /** Loads the newest page; older pages on demand. Server order (position) is the only order. */
  async loadThread(id, { older = false } = {}) {
    const t = this.thread(id);
    const confirmed = t.messages.filter((m) => m.delivery === 'confirmed');
    const offset = older ? confirmed.length : 0;
    const q = new URLSearchParams({ limit: String(PAGE), offset: String(offset), sort_by: 'position',
                                    sort_dir: 'desc' });
    const page = await this.http.get(`/chat/conversations/${id}/messages?${q}`);
    const fresh = page.items.map((m) => ({ ...m, delivery: 'confirmed' }));
    const local = t.messages.filter((m) => m.delivery !== 'confirmed');
    const byId = new Map((older ? [...confirmed, ...fresh] : fresh).map((m) => [m.id, m]));
    t.messages = mergeOrdered([...byId.values()], older ? local : this.#unresolved(local, fresh));
    t.total = page.total;
    t.loadedAll = confirmed.length + fresh.length >= page.total;
    this.emit();
    return t;
  }

  /** Local turns the server has now confirmed are dropped; the rest keep their honest state. */
  #unresolved(local, fresh) {
    const ids = new Set(fresh.map((m) => m.client_request_id).filter(Boolean));
    const answered = new Set(fresh.filter((m) => m.role === 'user').map((m) => m.text));
    return local.filter((m) => !(ids.has(m.clientRequestId) || (m.delivery === 'unknown' && answered.has(m.text))));
  }

  /**
   * Ask a question. Returns the assistant turn. The user turn is shown immediately as `pending`; it becomes
   * `confirmed` only when the server's answer arrives (the answer proves the question was stored).
   */
  async ask(id, question, { signal, retryOf } = {}) {
    const t = this.thread(id);
    const local = retryOf ?? { localId: newRequestId(), clientRequestId: newRequestId(), role: 'user', text: question,
                               created_at: new Date().toISOString() };
    local.delivery = 'pending';
    local.error = null;
    if (!retryOf) t.messages = [...t.messages, local];
    this.drafts.delete(id);
    this.emit();
    try {
      const answer = await this.http.post(`/chat/conversations/${id}/messages`,
                                          { question: local.text, client_request_id: local.clientRequestId },
                                          { signal, timeoutMs: 180000, retries: 0 });
      t.messages = t.messages.filter((m) => m !== local);
      // The answer carries answers_message_id; the user turn itself comes back with the next thread load.
      t.messages = mergeOrdered(t.messages.filter((m) => m.delivery === 'confirmed').concat(
        [{ ...answer, delivery: 'confirmed' }]), t.messages.filter((m) => m.delivery !== 'confirmed'));
      this.emit();
      // Reload so the confirmed user turn and its position come from the server, not from us.
      await this.loadThread(id).catch(() => {});
      this.#touch(id);
      return answer;
    } catch (err) {
      if (err.kind === ErrorKind.ABORTED || err.kind === ErrorKind.TIMEOUT || err.kind === ErrorKind.IN_PROGRESS) {
        local.delivery = 'unknown';
      } else {
        local.delivery = 'failed';
      }
      local.error = err;
      this.emit();
      throw err;
    }
  }

  /** Retry a failed or unknown turn with the same idempotency key. */
  retry(id, local, opts) {
    return this.ask(id, local.text, { ...opts, retryOf: local });
  }

  /** Server-side retry of an answered question (a new assistant turn; the server decides the cost). */
  async regenerate(id, messageId) {
    const m = await this.http.post(`/chat/messages/${messageId}/retry`, {}, { retries: 0, timeoutMs: 180000 });
    await this.loadThread(id).catch(() => {});
    return m;
  }

  async feedback(messageId, rating) {
    return this.http.post(`/chat/messages/${messageId}/feedback`, { rating }, { retries: 0 });
  }

  #touch(id) {
    const c = this.items.find((x) => x.id === id);
    if (c && !c.title) this.loadList().catch(() => {});
  }

  setDraft(id, text) { if (text) this.drafts.set(id ?? 'new', text); else this.drafts.delete(id ?? 'new'); }
  draft(id) { return this.drafts.get(id ?? 'new') ?? ''; }
}

/** Confirmed messages by server position, then local unconfirmed ones in the order they were sent. */
export function mergeOrdered(confirmed, local) {
  const sorted = [...confirmed].sort((a, b) => a.position - b.position);
  return [...sorted, ...local];
}
