// The only place the UI touches the operating system (ADR-137 §platform).
//
// TauriBridge  — Windows, macOS, Android, iOS. Secrets and the device private key live in Rust behind four
//                narrow commands (src-tauri/src/lib.rs); the private key never crosses into JavaScript.
// WebBridge    — a plain browser (development, end-to-end tests). The refresh token is kept in memory only,
//                so a reload signs you out; the device key is a NON-EXTRACTABLE WebCrypto key in IndexedDB.
//
// Both expose the same surface, so no screen knows which one it has.

const DB = 'aiol-device';
const STORE = 'keys';
const KEY_ID = 'installation-es256';

function b64(bytes) {
  let s = '';
  for (const b of new Uint8Array(bytes)) s += String.fromCharCode(b);
  return btoa(s);
}

/** URLs the app may hand to the system browser: https always, http only to loopback in development. */
export function isSafeExternalUrl(raw, { allowHttpLoopback = false } = {}) {
  let u;
  try { u = new URL(raw); } catch { return false; }
  if (u.username || u.password) return false;
  if (u.protocol === 'https:') return Boolean(u.hostname);
  if (u.protocol === 'mailto:') return /^[^@\s]+@[^@\s]+$/.test(u.pathname);
  if (allowHttpLoopback && u.protocol === 'http:') return ['localhost', '127.0.0.1', '[::1]'].includes(u.hostname);
  return false;
}

export class WebBridge {
  constructor({ version = '0.0.0-web', idb = globalThis.indexedDB, subtle = globalThis.crypto?.subtle } = {}) {
    this.kind = 'web';
    this.version = version;
    this.memory = new Map();
    this.idb = idb;
    this.subtle = subtle;
  }

  async vaultGet(k) { return this.memory.get(k) ?? null; }
  async vaultSet(k, v) { this.memory.set(k, v); }
  async vaultDelete(k) { this.memory.delete(k); }

  async appInfo() {
    return { version: this.version, platform: 'web', osFamily: 'browser', osVersion: null };
  }

  async openExternal(url) {
    if (!isSafeExternalUrl(url, { allowHttpLoopback: true })) throw new Error('Refused an unsafe link.');
    window.open(url, '_blank', 'noopener,noreferrer');
  }

  #db() {
    return new Promise((resolve, reject) => {
      const req = this.idb.open(DB, 1);
      req.onupgradeneeded = () => req.result.createObjectStore(STORE);
      req.onsuccess = () => resolve(req.result);
      req.onerror = () => reject(req.error);
    });
  }

  async #idb(mode, fn) {
    const db = await this.#db();
    return new Promise((resolve, reject) => {
      const tx = db.transaction(STORE, mode);
      const req = fn(tx.objectStore(STORE));
      tx.oncomplete = () => { db.close(); resolve(req?.result); };
      tx.onerror = () => { db.close(); reject(tx.error); };
    });
  }

  async #pair(create) {
    if (!this.idb || !this.subtle) return null;
    let pair = await this.#idb('readonly', (s) => s.get(KEY_ID));
    if (!pair && create) {
      // extractable=false: script on this origin can sign with it but can never read the private key out.
      pair = await this.subtle.generateKey({ name: 'ECDSA', namedCurve: 'P-256' }, false, ['sign', 'verify']);
      await this.#idb('readwrite', (s) => s.put(pair, KEY_ID));
    }
    return pair ?? null;
  }

  async deviceKey({ create = true } = {}) {
    const pair = await this.#pair(create);
    if (!pair) return null;
    const spki = await this.subtle.exportKey('spki', pair.publicKey);
    return { publicKey: b64(spki), storage: 'browser_non_extractable' };
  }

  async deviceSign(text) {
    const pair = await this.#pair(false);
    if (!pair) throw new Error('No device key.');
    const sig = await this.subtle.sign({ name: 'ECDSA', hash: 'SHA-256' }, pair.privateKey,
                                       new TextEncoder().encode(text));
    return b64(sig); // IEEE P1363 r||s; the server accepts it
  }

  async deviceKeyDelete() {
    if (this.idb) await this.#idb('readwrite', (s) => s.delete(KEY_ID));
  }
}

export class TauriBridge {
  constructor(invoke) {
    this.invoke = invoke;
    this.kind = 'unknown';
  }

  async init() {
    const info = await this.invoke('app_info');
    this.kind = info.platform;
    this.info = info;
    return this;
  }

  vaultGet(k) { return this.invoke('vault_get', { key: k }); }
  vaultSet(k, v) { return this.invoke('vault_set', { key: k, value: v }); }
  vaultDelete(k) { return this.invoke('vault_delete', { key: k }); }
  async appInfo() {
    const i = this.info;
    return { version: i.version, platform: i.platform, osFamily: i.os_family, osVersion: i.os_version };
  }
  openExternal(url) {
    if (!isSafeExternalUrl(url)) return Promise.reject(new Error('Refused an unsafe link.'));
    return this.invoke('open_external', { url }); // validated again in Rust
  }
  async deviceKey({ create = true } = {}) {
    const r = await this.invoke('device_key_public', { create });
    return r ? { publicKey: r.public_key, storage: r.storage } : null;
  }
  deviceSign(text) { return this.invoke('device_key_sign', { message: text }); }
  deviceKeyDelete() { return this.invoke('device_key_delete'); }
}

export async function detectBridge(opts = {}) {
  const tauri = globalThis.__TAURI__?.core?.invoke;
  if (typeof tauri === 'function') return new TauriBridge(tauri).init();
  return new WebBridge(opts);
}
