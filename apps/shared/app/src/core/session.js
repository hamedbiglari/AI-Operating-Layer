// Authentication state (ADR-137 §auth). Server-authoritative: the client holds tokens, never decisions.
//
//   signed_out ──sign-in──▶ signed_in ──refresh fails / sign-out──▶ signed_out
//        ▲                       │
//        └──── restore() ◀───────┘ (on launch: refresh secret from the OS vault)
//
// * Access token: memory only. Refresh secret: OS secure storage via the bridge, never localStorage, never a URL,
//   never logged.
// * Refresh is single-flight: concurrent 401s share one rotation, because the server treats a second use of a
//   rotated secret as theft and revokes the session.
// * Sign-out revokes on the server first (best effort), then always clears local state. It never deletes
//   server-side conversations.

const VAULT_KEY = 'aiol.refresh';

export class Session {
  constructor({ bridge, http, now = () => Date.now() }) {
    this.bridge = bridge;
    this.http = http;
    this.now = now;
    this.state = 'signed_out';
    this.accessToken = null;
    this.expiresAt = 0;
    this.user = null;
    this.organization = null;
    this.listeners = new Set();
    this.inflight = null;
  }

  on(fn) { this.listeners.add(fn); return () => this.listeners.delete(fn); }
  #emit() { for (const fn of this.listeners) fn(this); }

  token() {
    return this.accessToken;
  }

  async #accept(data) {
    this.accessToken = data.access_token;
    this.expiresAt = this.now() + data.expires_in_minutes * 60000;
    await this.bridge.vaultSet(VAULT_KEY, data.refresh_token);
  }

  async #loadMe() {
    const me = await this.http.get('/auth/me');
    this.user = me.user;
    this.organization = me.organization;
  }

  async requestCode(email) {
    return this.http.post('/auth/login-code/request', { email }, { auth: false });
  }

  async signIn({ email, code, password }) {
    const body = code ? { grant: 'login_code', email, code } : { grant: 'password', email, password };
    const data = await this.http.post('/auth/native/session', body, { auth: false });
    await this.#accept(data);
    await this.#loadMe();
    this.state = 'signed_in';
    this.#emit();
    return this.user;
  }

  /** On launch. True when a stored session is still good. */
  async restore() {
    const secret = await this.bridge.vaultGet(VAULT_KEY);
    if (!secret) return false;
    if (!(await this.refresh())) return false;
    await this.#loadMe();
    this.state = 'signed_in';
    this.#emit();
    return true;
  }

  /** Single-flight rotation. Resolves false when the session is gone (and clears it). */
  refresh() {
    if (this.inflight) return this.inflight;
    this.inflight = (async () => {
      const secret = await this.bridge.vaultGet(VAULT_KEY);
      if (!secret) return false;
      try {
        const data = await this.http.post('/auth/native/session/refresh', { refresh_token: secret },
                                          { auth: false, retries: 0 });
        await this.#accept(data);
        return true;
      } catch (err) {
        // A network failure is not a lost session: keep the secret and let the caller retry later.
        if (err.kind === 'network' || err.kind === 'timeout' || err.kind === 'server_retryable') return false;
        await this.#clearLocal();
        return false;
      }
    })().finally(() => { this.inflight = null; });
    return this.inflight;
  }

  /** Renew a minute early so a long screen never meets an expired token mid-action. */
  needsRenewal() {
    return this.state === 'signed_in' && this.expiresAt - this.now() < 60000;
  }

  async #clearLocal() {
    this.accessToken = null;
    this.expiresAt = 0;
    this.user = null;
    this.organization = null;
    await this.bridge.vaultDelete(VAULT_KEY);
    const was = this.state;
    this.state = 'signed_out';
    if (was !== 'signed_out') this.#emit();
  }

  async signOut() {
    const secret = await this.bridge.vaultGet(VAULT_KEY);
    if (secret) {
      try {
        await this.http.post('/auth/native/session/end', { refresh_token: secret }, { auth: false, retries: 1 });
      } catch { /* offline: the server session still expires on its own; local state is cleared regardless */ }
    }
    await this.#clearLocal();
  }

  /** Called by Http when a refresh fails mid-request. */
  async lost() { await this.#clearLocal(); }
}
