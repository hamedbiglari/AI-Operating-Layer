// The one HTTP path every screen uses. No screen calls fetch() directly.
//
// * Bearer token from the session; one silent refresh + one retry on 401, then the user signs in again.
// * Timeouts by AbortController; a caller-supplied signal (Stop) aborts too.
// * Automatic retries ONLY for idempotent methods, ONLY for transport failures, bounded, with jittered backoff.
//   A POST is never retried blindly: the chat sends a client_request_id so its own retry is safe.
// * Responses above MAX_BYTES are refused rather than parsed.

import { ApiError, ErrorKind, fromResponse, networkError } from './errors.js';
import { backoffDelays, sleep } from './retry.js';

const MAX_BYTES = 5 * 1024 * 1024;
const IDEMPOTENT = new Set(['GET', 'PUT', 'DELETE']);

export class Http {
  /**
   * @param {object} o
   * @param {string} o.baseUrl         e.g. https://api.example.com/api/v1
   * @param {() => string|null} o.token
   * @param {() => Promise<boolean>} [o.refresh]  renew the access token; false = session gone
   * @param {(err: ApiError) => void} [o.onSessionLost]
   * @param {typeof fetch} [o.fetch]
   */
  constructor(o) {
    this.baseUrl = o.baseUrl.replace(/\/+$/, '');
    this.token = o.token;
    this.refresh = o.refresh ?? (async () => false);
    this.onSessionLost = o.onSessionLost ?? (() => {});
    this.fetch = o.fetch ?? globalThis.fetch.bind(globalThis);
    this.timeoutMs = o.timeoutMs ?? 30000;
    this.sleep = o.sleep ?? sleep;
  }

  async request(method, path, { body, signal, timeoutMs, auth = true, retries } = {}) {
    method = method.toUpperCase();
    const maxRetries = retries ?? (IDEMPOTENT.has(method) ? 2 : 0);
    const delays = backoffDelays(maxRetries);
    let refreshed = false;
    for (let attempt = 0; ; attempt++) {
      try {
        return await this.#once(method, path, { body, signal, timeoutMs, auth });
      } catch (err) {
        if (!(err instanceof ApiError)) throw err;
        if (err.kind === ErrorKind.UNAUTHORIZED && auth && !refreshed) {
          refreshed = true;
          if (await this.refresh()) { attempt--; continue; }
          const lost = new ApiError(ErrorKind.SESSION_EXPIRED, 'Your session has ended. Sign in again.',
                                    { status: 401 });
          this.onSessionLost(lost);
          throw lost;
        }
        if (err.retryable && attempt < maxRetries && !signal?.aborted) {
          await this.sleep(delays[attempt]);
          continue;
        }
        throw err;
      }
    }
  }

  async #once(method, path, { body, signal, timeoutMs, auth }) {
    const ctl = new AbortController();
    const timer = setTimeout(() => ctl.abort('timeout'), timeoutMs ?? this.timeoutMs);
    const onAbort = () => ctl.abort('user');
    signal?.addEventListener('abort', onAbort, { once: true });
    const headers = { Accept: 'application/json' };
    if (body !== undefined) headers['Content-Type'] = 'application/json';
    const tok = auth ? this.token() : null;
    if (auth && !tok) throw new ApiError(ErrorKind.UNAUTHORIZED, 'Sign in to continue.', { status: 401 });
    if (tok) headers.Authorization = `Bearer ${tok}`;
    let res;
    try {
      res = await this.fetch(this.baseUrl + path, {
        method, headers, signal: ctl.signal, credentials: 'omit', cache: 'no-store', redirect: 'error',
        body: body === undefined ? undefined : JSON.stringify(body),
      });
    } catch {
      if (signal?.aborted) throw networkError(ErrorKind.ABORTED);
      if (ctl.signal.aborted) throw networkError(ErrorKind.TIMEOUT);
      throw networkError(ErrorKind.NETWORK);
    } finally {
      clearTimeout(timer);
      signal?.removeEventListener('abort', onAbort);
    }
    const len = Number(res.headers.get('content-length') || 0);
    if (len > MAX_BYTES) throw new ApiError(ErrorKind.SERVER, 'The response was too large.', { status: res.status });
    const text = res.status === 204 ? '' : await res.text();
    if (text.length > MAX_BYTES) throw new ApiError(ErrorKind.SERVER, 'The response was too large.', { status: res.status });
    let data = null;
    if (text) {
      try { data = JSON.parse(text); } catch { data = null; }
    }
    if (!res.ok) {
      throw fromResponse(res.status, data, { 'retry-after': res.headers.get('retry-after') });
    }
    return { status: res.status, data, headers: res.headers };
  }

  get(path, o) { return this.request('GET', path, o).then((r) => r.data); }
  post(path, body, o) { return this.request('POST', path, { ...o, body }).then((r) => r.data); }
  put(path, body, o) { return this.request('PUT', path, { ...o, body }).then((r) => r.data); }
  patch(path, body, o) { return this.request('PATCH', path, { ...o, body }).then((r) => r.data); }
  del(path, o) { return this.request('DELETE', path, o).then((r) => r.data); }
}
