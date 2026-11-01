// Error classification shared by every screen (ADR-137 §errors).
//
// Cloud Core answers every failure with {"error": {"code", "message", "reason"?}, "request_id"}. The client turns
// that, or a transport failure, into exactly one ErrorKind. Screens branch on the kind, never on raw text, and
// never show a stack trace or another user's data — only the server's message, which is written for users.

export const ErrorKind = Object.freeze({
  UNAUTHORIZED: 'unauthorized',          // no/invalid credentials: sign in
  SESSION_EXPIRED: 'session_expired',    // refresh failed: sign in again
  FORBIDDEN: 'forbidden',                // signed in, not allowed
  NOT_FOUND: 'not_found',
  RATE_LIMITED: 'rate_limited',          // wait Retry-After
  QUOTA_EXHAUSTED: 'quota_exhausted',    // daily chat limit / insufficient balance
  VALIDATION: 'validation',
  CONFLICT: 'conflict',
  IN_PROGRESS: 'in_progress',            // idempotent replay of a request still being answered
  NETWORK: 'network',                    // never reached the server
  TIMEOUT: 'timeout',
  SERVER_RETRYABLE: 'server_retryable',  // 502/503/504
  SERVER: 'server',                      // 500 and anything else
  ABORTED: 'aborted',                    // the user stopped waiting
});

const RETRYABLE = new Set([ErrorKind.NETWORK, ErrorKind.TIMEOUT, ErrorKind.SERVER_RETRYABLE]);

export class ApiError extends Error {
  /**
   * @param {string} kind     one of ErrorKind
   * @param {string} message  safe to show to the user
   * @param {object} [extra]  {status, reason, requestId, retryAfter}
   */
  constructor(kind, message, extra = {}) {
    super(message);
    this.name = 'ApiError';
    this.kind = kind;
    this.status = extra.status ?? null;
    this.reason = extra.reason ?? null;
    this.requestId = extra.requestId ?? null;
    this.retryAfter = extra.retryAfter ?? null;
  }

  /** Safe to retry automatically? Only transport-level failures, and only for idempotent requests. */
  get retryable() { return RETRYABLE.has(this.kind); }
}

const GENERIC = {
  [ErrorKind.NETWORK]: 'Cannot reach AIOL. Check your connection.',
  [ErrorKind.TIMEOUT]: 'AIOL did not answer in time.',
  [ErrorKind.SERVER_RETRYABLE]: 'AIOL is temporarily unavailable. Try again shortly.',
  [ErrorKind.SERVER]: 'Something went wrong on the server.',
  [ErrorKind.ABORTED]: 'Stopped.',
};

/** Map an HTTP status + parsed envelope to an ApiError. Pure; unit-tested. */
export function fromResponse(status, body, headers = {}) {
  const env = body && typeof body === 'object' ? body.error : null;
  const message = (env && typeof env.message === 'string' && env.message) || GENERIC[ErrorKind.SERVER];
  const reason = env && typeof env.reason === 'string' ? env.reason : null;
  const requestId = body && typeof body.request_id === 'string' ? body.request_id : null;
  const ra = Number.parseInt(headers['retry-after'] ?? '', 10);
  const extra = { status, reason, requestId, retryAfter: Number.isFinite(ra) ? ra : null };
  let kind;
  if (status === 401) kind = ErrorKind.UNAUTHORIZED;
  else if (status === 402) kind = ErrorKind.QUOTA_EXHAUSTED;
  else if (status === 403) kind = ErrorKind.FORBIDDEN;
  else if (status === 404) kind = ErrorKind.NOT_FOUND;
  else if (status === 409) kind = reason === 'request_in_progress' ? ErrorKind.IN_PROGRESS : ErrorKind.CONFLICT;
  else if (status === 422 || status === 400) kind = ErrorKind.VALIDATION;
  else if (status === 429) kind = /limit reached/i.test(message) ? ErrorKind.QUOTA_EXHAUSTED : ErrorKind.RATE_LIMITED;
  else if (status === 502 || status === 503 || status === 504) kind = ErrorKind.SERVER_RETRYABLE;
  else kind = ErrorKind.SERVER;
  const safe = kind === ErrorKind.SERVER || kind === ErrorKind.SERVER_RETRYABLE ? GENERIC[kind] : message;
  return new ApiError(kind, safe, extra);
}

export function networkError(kind = ErrorKind.NETWORK) {
  return new ApiError(kind, GENERIC[kind]);
}
