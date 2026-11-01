// Bounded exponential backoff with full jitter. Never infinite: the caller passes the count.

export function backoffDelays(count, { baseMs = 500, capMs = 8000, random = Math.random } = {}) {
  const out = [];
  for (let i = 0; i < count; i++) {
    const ceiling = Math.min(capMs, baseMs * 2 ** i);
    out.push(Math.round(ceiling / 2 + random() * (ceiling / 2)));
  }
  return out;
}

export const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

/** A request id the server accepts as client_request_id: [A-Za-z0-9_-]{8,64}. */
export function newRequestId(rand = globalThis.crypto) {
  const bytes = new Uint8Array(16);
  rand.getRandomValues(bytes);
  return 'cr_' + Array.from(bytes, (b) => b.toString(16).padStart(2, '0')).join('');
}
