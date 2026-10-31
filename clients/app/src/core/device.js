// Device Intelligence client (ADR-138). Optional by construction:
//
// * Every call is wrapped; no failure here ever reaches sign-in, chat or any screen. The result is a status the
//   Settings screen can show, nothing more.
// * The user can turn it off. Turning it off removes this installation from the account on the server and
//   deletes the local key.
// * The private key never leaves the bridge. JavaScript sees a public key and signatures.

const PREF = 'aiol.device.enabled';
const CRED = 'aiol.device.credential';

export const DeviceStatus = Object.freeze({
  OFF: 'off',                   // the user turned it off
  UNAVAILABLE: 'unavailable',   // no secure key facility, or the server has it disabled
  REGISTERED: 'registered',
  VERIFIED: 'verified',
  REVOKED: 'revoked',           // the server revoked this key; a fresh key is created next time
  FAILED: 'failed',             // could not complete this time; nothing else is affected
});

export class DeviceIntelligence {
  constructor({ bridge, http, prefs = globalThis.localStorage }) {
    this.bridge = bridge;
    this.http = http;
    this.prefs = prefs;
    this.status = DeviceStatus.UNAVAILABLE;
    this.lastError = null;
  }

  // Preference and credential id are not secrets; they are per-installation conveniences.
  #get(k) { try { return this.prefs?.getItem(k) ?? null; } catch { return null; } }
  #set(k, v) { try { if (v == null) this.prefs?.removeItem(k); else this.prefs?.setItem(k, v); } catch { /* */ } }

  get enabled() { return this.#get(PREF) !== 'false'; }

  async #sign(purpose, credentialId) {
    const ch = await this.http.post('/devices/challenges', { purpose, credential_id: credentialId ?? null },
                                    { retries: 0 });
    return { ch, signature: await this.bridge.deviceSign(ch.signing_input) };
  }

  async #register(info) {
    const key = await this.bridge.deviceKey({ create: true });
    if (!key) { this.status = DeviceStatus.UNAVAILABLE; return; }
    const { ch, signature } = await this.#sign('register');
    const cred = await this.http.post('/devices/credentials', {
      challenge_id: ch.challenge_id, nonce: ch.nonce, public_key: key.publicKey, signature,
      platform: info.platform, key_storage: key.storage, app_version: info.version,
      os_family: info.osFamily, os_version: info.osVersion,
    }, { retries: 0 });
    this.#set(CRED, cred.id);
    this.status = DeviceStatus.REGISTERED;
  }

  /**
   * After sign-in. Registers this installation for the signed-in account (idempotent: the same key and account
   * is a no-op, a second account on the same installation is linked), then proves continuity.
   */
  async ensure({ serverEnabled = true } = {}) {
    this.lastError = null;
    if (!this.enabled) { this.status = DeviceStatus.OFF; return this.status; }
    if (!serverEnabled) { this.status = DeviceStatus.UNAVAILABLE; return this.status; }
    try {
      const info = await this.bridge.appInfo();
      // Register-or-link first: proof of possession is per account, so account switching is handled here.
      await this.#register(info);
      const id = this.#get(CRED);
      const { ch, signature } = await this.#sign('verify', id);
      await this.http.post(`/devices/credentials/${id}/verify`, {
        challenge_id: ch.challenge_id, nonce: ch.nonce, signature, app_version: info.version,
      }, { retries: 0 });
      this.status = DeviceStatus.VERIFIED;
    } catch (err) {
      this.lastError = err?.reason ?? err?.kind ?? 'error';
      if (err?.reason === 'credential_revoked') {
        // Revoked keys never come back. Drop it; the next ensure() creates a new installation key.
        await this.#forgetLocal();
        this.status = DeviceStatus.REVOKED;
      } else if (err?.kind === 'not_found' && err?.reason === 'disabled') {
        this.status = DeviceStatus.UNAVAILABLE;
      } else {
        this.status = DeviceStatus.FAILED;
      }
    }
    return this.status;
  }

  async #forgetLocal() {
    this.#set(CRED, null);
    try { await this.bridge.deviceKeyDelete(); } catch { /* nothing to delete */ }
  }

  /** The user turns it off: unlink on the server (best effort), delete the key, remember the choice. */
  async disable() {
    this.#set(PREF, 'false');
    const id = this.#get(CRED);
    if (id) {
      try { await this.http.del(`/devices/credentials/${id}`, { retries: 1 }); } catch { /* signed out / offline */ }
    }
    await this.#forgetLocal();
    this.status = DeviceStatus.OFF;
  }

  async enable(opts) {
    this.#set(PREF, 'true');
    return this.ensure(opts);
  }
}
