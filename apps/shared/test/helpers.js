// A fake fetch that answers from a script of handlers, recording every request. No network.
export function fakeFetch(handler) {
  const calls = [];
  const fn = async (url, init = {}) => {
    const req = { url, method: init.method ?? 'GET', headers: init.headers ?? {},
                  body: init.body ? JSON.parse(init.body) : undefined, signal: init.signal };
    calls.push(req);
    const out = await handler(req, calls.length);
    if (out instanceof Error) throw out;
    const { status = 200, body = null, headers = {}, raw } = out;
    const text = raw ?? (body == null ? '' : JSON.stringify(body));
    const bytes = new TextEncoder().encode(text);
    return {
      ok: status >= 200 && status < 300, status,
      headers: { get: (k) => ({ 'content-length': String(text.length), ...headers })[k.toLowerCase()] ?? null },
      text: async () => text,
      // A body delivered in small chunks, so the SSE parser sees events split across reads.
      body: { getReader() { let i = 0; return { read: async () => (i >= bytes.length ? { done: true }
        : { done: false, value: bytes.slice(i, (i += 7)) }) }; } },
    };
  };
  fn.calls = calls;
  return fn;
}

export class MemoryBridge {
  constructor() { this.kind = 'web'; this.vault = new Map(); this.signed = []; this.keyDeleted = 0; }
  async vaultGet(k) { return this.vault.get(k) ?? null; }
  async vaultSet(k, v) { this.vault.set(k, v); }
  async vaultDelete(k) { this.vault.delete(k); }
  async appInfo() { return { version: '0.1.0', platform: 'windows', osFamily: 'windows', osVersion: '11' }; }
  async deviceKey() { return { publicKey: 'PUB', storage: 'os_keystore' }; }
  async deviceSign(text) { this.signed.push(text); return 'SIG'; }
  async deviceKeyDelete() { this.keyDeleted++; }
  async platformSignals() { return this.signals ?? {}; }
}

export class MemoryStorage {
  constructor() { this.m = new Map(); }
  getItem(k) { return this.m.has(k) ? this.m.get(k) : null; }
  setItem(k, v) { this.m.set(k, String(v)); }
  removeItem(k) { this.m.delete(k); }
}

export const noSleep = async () => {};

/** Server-Sent Events text for a list of [name, data] pairs. */
export function sse(events) {
  return events.map(([n, d]) => `event: ${n}\ndata: ${JSON.stringify(d)}\n\n`).join('') ;
}
